# main.py (최종 수정: 야간에도 얼굴 인식 성공 시 문 열림)
import threading
import random
import string
from datetime import datetime, time as dt_time
import boto3
import cv2
import time
import os
import requests # 이미지 다운로드용

from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.lang import Builder
from kivy.graphics.texture import Texture
from kivymd.app import MDApp

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore, storage

# GPIO & sensors
try:
    import RPi.GPIO as GPIO
except ImportError:
    GPIO = None
    print("GPIO 라이브러리 없음 (테스트 모드)")

# 폰트 등록
LabelBase.register(name='SpoqaSans', fn_regular='Fonts/Spoqa Han Sans Regular.ttf')

class DoorLockApp(MDApp):
    def build(self):
        self.root = Builder.load_file('doorlock.kv')

        # ---------- 설정값 ----------
        # RTSP 주소
        self.rtsp_url = "rtsp://100.122.50.3:8554/mystream"

        # 카메라 옵션
        self.FLIP_HORIZONTAL = False
        self.FLIP_VERTICAL = True

        # Firebase Storage 버킷
        self.storage_bucket = "capstonedesign-89f88.firebasestorage.app"

        # 야간 차단 시간 (이제는 얼굴 인식 차단용이 아니라, 단순 참고용으로만 남음)
        self.LOCK_START = 1  # 20:00
        self.LOCK_END = 7     # 07:00

        # 키패드 코드
        self.ALLOWED_CODES = {"12", "34"}

        # 초음파 임계값
        self.DISTANCE_THRESHOLD_CM = 200

        # 액추에이터 사용 여부
        self.USE_ACTUATOR = True

        # --------------------------------

        # AWS Rekognition
        self.rekognition_client = boto3.client('rekognition', region_name='ap-northeast-2')
        self.collection_id = 'family_faces'

        # 사용자 매핑 테이블 (AWS ID -> 한글 이름)
        self.user_map = {}

        self.is_recognizing = False

        # 도어 작동 중복 방지 플래그
        self.is_door_operating = False

        # GPIO 핀 설정
        self.RELAY_PIN = 17
        self.ENA_PIN = 25
        self.IN1_PIN = 8
        self.IN2_PIN = 7
        self.TRIG = 23
        self.ECHO = 24

        self.ROW_PINS = [21, 20, 16, 12]
        self.COL_PINS = [26, 19, 13, 6]
        self.KEYPAD_MAP = [
            ['1', '2', '3', 'A'],
            ['4', '5', '6', 'B'],
            ['7', '8', '9', 'C'],
            ['*', '0', '#', 'D']
        ]

        # GPIO 초기화
        if GPIO:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(self.RELAY_PIN, GPIO.OUT)
            GPIO.output(self.RELAY_PIN, GPIO.LOW)

            GPIO.setup(self.ENA_PIN, GPIO.OUT)
            GPIO.setup(self.IN1_PIN, GPIO.OUT)
            GPIO.setup(self.IN2_PIN, GPIO.OUT)
            GPIO.output(self.ENA_PIN, GPIO.LOW)
            GPIO.output(self.IN1_PIN, GPIO.LOW)
            GPIO.output(self.IN2_PIN, GPIO.LOW)

            GPIO.setup(self.TRIG, GPIO.OUT)
            GPIO.setup(self.ECHO, GPIO.IN)

            for p in self.COL_PINS:
                GPIO.setup(p, GPIO.OUT)
                GPIO.output(p, GPIO.HIGH)
            for p in self.ROW_PINS:
                GPIO.setup(p, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # 초기 액추에이터 상태 설정 (잠금)
        if GPIO and self.USE_ACTUATOR:
            print("초기화: 액추에이터 잠금 설정")
            try:
                GPIO.output(self.ENA_PIN, GPIO.HIGH)
                GPIO.output(self.IN1_PIN, GPIO.HIGH)
                GPIO.output(self.IN2_PIN, GPIO.LOW)
                time.sleep(1.5)
                GPIO.output(self.IN1_PIN, GPIO.LOW)
                GPIO.output(self.IN2_PIN, GPIO.LOW)
                GPIO.output(self.ENA_PIN, GPIO.LOW)
            except Exception as e:
                print(f"초기 액추에이터 설정 오류: {e}")
                GPIO.output(self.ENA_PIN, GPIO.LOW)

        # Firebase init
        try:
            cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred, {"storageBucket": self.storage_bucket})
            self.db = firestore.client()
            self.bucket = storage.bucket()
            print("Firebase 초기화 성공")

            # 앱 시작 시 '잠금' 상태로 초기화 알림
            self._update_firestore_status(is_locked=True)

        except Exception as e:
            print("Firebase 초기화 실패:", e)
            self.db = None
            self.bucket = None

        self.current_frame = None
        self.frame_lock = threading.Lock()
        self.presence_detected = False
        self.key_buffer = ""
        self.last_key_time = 0

        return self.root

    # ---------------------------------------------------------
    # Firestore 상태 업데이트 (앱으로 상태 전송)
    # ---------------------------------------------------------
    def _update_firestore_status(self, is_locked):
        if not self.db: return
        try:
            self.db.collection("door_control").document("status").set(
                {"isLocked": is_locked}, merge=True
            )
            state_str = "잠김(True)" if is_locked else "열림(False)"
            print(f" >> 상태 동기화: {state_str}")
        except Exception as e:
            print(f" >> 상태 동기화 실패: {e}")

    # -----------------------
    # 앱 시작
    # -----------------------
    def on_start(self):
        # 1. GStreamer 파이프라인 (저지연 모드) 우선 시도
        gst = (
            f'rtspsrc location={self.rtsp_url} latency=0 ! '
            f'rtph264depay ! h264parse ! avdec_h264 ! '
            f'videoconvert ! appsink max-buffers=1 drop=true sync=false'
        )

        print(f"카메라 연결 시도 (GStreamer): {self.rtsp_url}")
        self.cap = cv2.VideoCapture(gst, cv2.CAP_GSTREAMER)

        # 2. GStreamer 실패 시 -> 기본(FFmpeg) 모드로 자동 전환
        if not self.cap.isOpened():
            print(">> GStreamer 연결 실패. 기본 모드로 전환합니다...")
            self.cap = cv2.VideoCapture(self.rtsp_url)

            if self.cap.isOpened():
                # 딜레이를 줄이기 위해 버퍼 크기 제한
                self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                print(">> 기본 모드 연결 성공!")
            else:
                print(">> 카메라 연결 완전 실패. RTSP 주소나 네트워크를 확인하세요.")
                self.root.ids.status_label.text = "카메라 연결 실패"
        else:
            print(">> GStreamer 모드 연결 성공!")

        # 스레드 시작
        self.camera_thread_running = True
        threading.Thread(target=self._camera_reader_thread, daemon=True).start()
        threading.Thread(target=self._distance_monitor_thread, daemon=True).start()
        threading.Thread(target=self._keypad_thread, daemon=True).start()

        # 사용자 정보 동기화 스레드
        threading.Thread(target=self._sync_users_thread, daemon=True).start()

        # 원격 제어 리스너 시작
        self.start_firestore_listener()

        # UI 업데이트
        Clock.schedule_interval(self.update_camera_view, 1/25)
        Clock.schedule_interval(self.recognize_check_trigger, 1.0)
        Clock.schedule_interval(self.update_time, 1)

    # ---------------------------------------------------------
    # Firebase Users -> AWS 동기화
    # ---------------------------------------------------------
    def _sync_users_thread(self):
        if not self.db: return
        Clock.schedule_once(lambda dt: self.set_status("사용자 정보 동기화 중..."))

        try:
            try:
                self.rekognition_client.create_collection(CollectionId=self.collection_id)
            except self.rekognition_client.exceptions.ResourceAlreadyExistsException:
                pass

            registered_ids = set()
            try:
                resp = self.rekognition_client.list_faces(CollectionId=self.collection_id)
                for face in resp.get('Faces', []):
                    registered_ids.add(face['ExternalImageId'])
            except: pass

            users_ref = self.db.collection('users')
            docs = users_ref.stream()

            count = 0
            for doc in docs:
                data = doc.to_dict()
                doc_id = doc.id
                user_name = data.get('name', 'Unknown')
                image_url = data.get('faceImageUrl', '')

                self.user_map[doc_id] = user_name

                if image_url and doc_id not in registered_ids:
                    print(f"동기화: {user_name} 등록 시도")
                    try:
                        img_data = requests.get(image_url).content
                        self.rekognition_client.index_faces(
                            CollectionId=self.collection_id,
                            Image={'Bytes': img_data},
                            ExternalImageId=doc_id,
                            MaxFaces=1,
                            QualityFilter="AUTO",
                            DetectionAttributes=['ALL']
                        )
                        count += 1
                    except Exception as e:
                        print(f" -> 등록 실패: {e}")

            print(f"동기화 완료 ({count}명 추가). 사용자: {self.user_map}")
            Clock.schedule_once(lambda dt: self.set_status("대기 중"))

        except Exception as e:
            print("동기화 오류:", e)

    # ---------------------------------------------------------
    # 원격 제어 리스너
    # ---------------------------------------------------------
    def start_firestore_listener(self):
        if not self.db:
            print("Firestore 미연결: 리스너 실행 불가")
            return
        try:
            doc_ref = self.db.collection("door_control").document("status")

            def on_snapshot(doc_snapshot, changes, read_time):
                for doc in doc_snapshot:
                    data = doc.to_dict() or {}
                    is_locked = data.get("isLocked")

                    if is_locked is True:
                        Clock.schedule_once(lambda d: self.close_door())
                    elif is_locked is False:
                        Clock.schedule_once(lambda d: self.open_door())

            doc_ref.on_snapshot(on_snapshot)
            print("원격 제어 리스너 등록됨")
        except Exception as e:
            print("리스너 등록 오류:", e)

    # -----------------------
    # 스레드들 (카메라, 센서, 키패드)
    # -----------------------
    def _camera_reader_thread(self):
        while getattr(self, "camera_thread_running", False):
            try:
                ret, frame = self.cap.read()
                if not ret or frame is None:
                    time.sleep(0.05)
                    continue
                if self.FLIP_VERTICAL: frame = cv2.flip(frame, 0)
                if self.FLIP_HORIZONTAL: frame = cv2.flip(frame, 1)
                with self.frame_lock:
                    self.current_frame = frame
            except: time.sleep(0.2)

    def _distance_monitor_thread(self):
        if not GPIO: return
        while True:
            try:
                GPIO.output(self.TRIG, False)
                time.sleep(0.05)
                GPIO.output(self.TRIG, True)
                time.sleep(0.00001)
                GPIO.output(self.TRIG, False)

                pulse_start = pulse_end = None
                t0 = time.time()
                while GPIO.input(self.ECHO) == 0 and time.time() - t0 < 0.02:
                    pulse_start = time.time()
                t1 = time.time()
                while GPIO.input(self.ECHO) == 1 and time.time() - t1 < 0.02:
                    pulse_end = time.time()

                if pulse_start and pulse_end:
                    distance = (pulse_end - pulse_start) * 17150
                    self.presence_detected = (distance < self.DISTANCE_THRESHOLD_CM)
                else:
                    self.presence_detected = False
            except: pass
            time.sleep(0.3)

    def _keypad_thread(self):
        if not GPIO: return
        while True:
            key = self._scan_keypad_once()
            if key:
                now = time.time()
                if now - self.last_key_time > 2:
                    self.key_buffer = ""
                self.last_key_time = now

                if key == '*':
                    if self.key_buffer in self.ALLOWED_CODES:
                        Clock.schedule_once(lambda dt: self.set_status("수동 인증 성공"))
                        self.open_door()
                    else:
                        Clock.schedule_once(lambda dt: self.set_status("잘못된 코드"))
                    self.key_buffer = ""
                elif key not in ('#', 'A', 'B', 'C', 'D'):
                    self.key_buffer += key
                    if len(self.key_buffer) > 4:
                        self.key_buffer = self.key_buffer[-4:]
            time.sleep(0.05)

    def _scan_keypad_once(self):
        for j, col_pin in enumerate(self.COL_PINS):
            GPIO.output(col_pin, GPIO.LOW)
            for i, row_pin in enumerate(self.ROW_PINS):
                if GPIO.input(row_pin) == GPIO.LOW:
                    time.sleep(0.03)
                    while GPIO.input(row_pin) == GPIO.LOW: time.sleep(0.01)
                    GPIO.output(col_pin, GPIO.HIGH)
                    return self.KEYPAD_MAP[i][j]
            GPIO.output(col_pin, GPIO.HIGH)
        return None

    def update_camera_view(self, dt):
        if self.current_frame is None: return
        with self.frame_lock: frame = self.current_frame.copy()
        try:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt='rgb')
            texture.blit_buffer(frame_rgb.tobytes(), colorfmt='rgb', bufferfmt='ubyte')
            self.root.ids.camera_view.texture = texture
        except: pass

    # -----------------------
    # 얼굴 인식 트리거 (수정됨: 야간에도 인식 성공 시 문 열림)
    # -----------------------
    def recognize_check_trigger(self, dt):
        if self.is_recognizing: return
        if not self.db: return

        # [수정됨] 야간 시간 체크 로직 제거!
        # (이제 시간과 상관없이 사람이 감지되면 인식을 시도하고, 성공하면 문을 엽니다)

        if not self.presence_detected: return
        if self.current_frame is None: return

        self.is_recognizing = True
        with self.frame_lock: frame = self.current_frame.copy()

        small = cv2.resize(frame, (640, 360))
        _, jpg = cv2.imencode('.jpg', small, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        image_bytes = jpg.tobytes()

        def rek_task():
            image_to_upload = image_bytes
            status = "Unknown"
            similarity = 0
            visitor_name_kr = "Unknown"
            visitor_id = "Unknown"
            open_requested = False
            valid_face_detected = False

            try:
                response = self.rekognition_client.search_faces_by_image(
                    CollectionId=self.collection_id,
                    Image={'Bytes': image_to_upload},
                    FaceMatchThreshold=90,
                    MaxFaces=1
                )

                valid_face_detected = True

                if response.get("FaceMatches"):
                    match = response["FaceMatches"][0]
                    sim = match["Similarity"]
                    face = match.get("Face", {})

                    visitor_id = face.get("ExternalImageId", "Unknown")
                    visitor_name_kr = self.user_map.get(visitor_id, visitor_id)

                    status = "Recognized"
                    similarity = sim
                    open_requested = True # 야간이어도 여기서 True가 되면 문 열림

                    print(f"인식 성공: {visitor_name_kr}")
                    Clock.schedule_once(lambda dt: self.set_status(f"환영합니다, {visitor_name_kr}님"))
                else:
                    status = "Unknown"
                    Clock.schedule_once(lambda dt: self.set_status("등록되지 않은 사용자"))

            except Exception as e:
                valid_face_detected = False

            if valid_face_detected:
                def log_task():
                    try:
                        filename = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{status}.jpg"
                        blob_path = f"visitor_logs/{filename}"
                        blob = self.bucket.blob(blob_path)
                        blob.upload_from_string(image_to_upload, content_type='image/jpeg')

                        self.db.collection("visitor_logs").add({
                            "timestamp": datetime.now().isoformat(),
                            "status": status,
                            "visitor_name": visitor_name_kr,
                            "visitor_id": visitor_id,
                            "similarity": similarity,
                            "image_path": blob.name
                        })
                        print(f"로그 저장 완료: {visitor_name_kr}")
                    except Exception as e:
                        print(f"로그 저장 실패: {e}")

                threading.Thread(target=log_task, daemon=True).start()

            if open_requested:
                # UI 스레드에서 문 열기 호출 (시간 제한 없음)
                Clock.schedule_once(lambda dt: self.open_door())

            self.is_recognizing = False

        threading.Thread(target=rek_task, daemon=True).start()

    def _is_locked_time(self, now_time):
        start = dt_time(self.LOCK_START, 0)
        end = dt_time(self.LOCK_END, 0)
        if self.LOCK_START < self.LOCK_END:
            return start <= now_time < end
        else:
            return (now_time >= start) or (now_time < end)

    # ---------------------------------------------------------
    # 도어 제어 (통합: 스레드 안전 제어 + 상태 알림)
    # ---------------------------------------------------------
    def open_door(self):
        if self.is_door_operating: return
        threading.Thread(target=self._open_door_logic, daemon=True).start()

    def _open_door_logic(self):
        self.is_door_operating = True
        try:
            if GPIO and self.USE_ACTUATOR:
                # 1. 열림 (Retract)
                GPIO.output(self.ENA_PIN, GPIO.HIGH)
                GPIO.output(self.IN1_PIN, GPIO.LOW)
                GPIO.output(self.IN2_PIN, GPIO.HIGH)
                time.sleep(1.5)
                GPIO.output(self.IN1_PIN, GPIO.LOW)
                GPIO.output(self.IN2_PIN, GPIO.LOW)
            elif GPIO:
                GPIO.output(self.RELAY_PIN, GPIO.HIGH)

            # 2. 앱에 '열림' 상태 알림
            self._update_firestore_status(is_locked=False)

            # 3. 대기 (5초)
            time.sleep(3)
            Clock.schedule_once(lambda dt: self.set_status("문 자동 닫힘"))

            # 4. 닫힘 (Extend)
            if GPIO and self.USE_ACTUATOR:
                GPIO.output(self.IN1_PIN, GPIO.HIGH)
                GPIO.output(self.IN2_PIN, GPIO.LOW)
                time.sleep(1.5)
                GPIO.output(self.IN1_PIN, GPIO.LOW)
                GPIO.output(self.IN2_PIN, GPIO.LOW)
                GPIO.output(self.ENA_PIN, GPIO.LOW)
            elif GPIO:
                GPIO.output(self.RELAY_PIN, GPIO.LOW)

            # 5. 앱에 '닫힘' 상태 알림
            self._update_firestore_status(is_locked=True)

        except Exception as e:
            print("도어 제어 오류:", e)
        finally:
            self.is_door_operating = False

    # [추가] 강제 닫기 (원격 제어용)
    def close_door(self):
        if self.is_door_operating: return
        try:
            if GPIO and self.USE_ACTUATOR:
                GPIO.output(self.ENA_PIN, GPIO.HIGH)
                GPIO.output(self.IN1_PIN, GPIO.HIGH)
                GPIO.output(self.IN2_PIN, GPIO.LOW)
                time.sleep(1.5)
                GPIO.output(self.IN1_PIN, GPIO.LOW)
                GPIO.output(self.IN2_PIN, GPIO.LOW)
                GPIO.output(self.ENA_PIN, GPIO.LOW)
            elif GPIO:
                GPIO.output(self.RELAY_PIN, GPIO.LOW)

            Clock.schedule_once(lambda d: self.set_status("문 닫힘 (원격)"))
            self._update_firestore_status(is_locked=True)

        except Exception as e:
            print("강제 닫기 오류:", e)

    # -----------------------
    # 기타
    # -----------------------
    def generate_invite_code(self):
        try:
            code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            if self.db:
                self.db.collection("invites").document().set({
                    "code": code,
                    "created_at": datetime.now().isoformat(),
                    "device": "DoorLock_Unit_1",
                    "used": False
                })
            self.root.ids.code_label.text = code
        except: pass

    def update_time(self, dt):
        now = datetime.now()
        weekday = "월화수목금토일"[now.weekday()]
        self.root.ids.time_label.text = now.strftime("%H:%M")
        self.root.ids.date_label.text = now.strftime(f"%Y.%m.%d ({weekday})")

    def set_status(self, text):
        try: self.root.ids.status_label.text = text
        except: pass

    def on_stop(self):
        self.camera_thread_running = False
        try:
            if GPIO and self.USE_ACTUATOR:
                GPIO.output(self.ENA_PIN, GPIO.HIGH)
                GPIO.output(self.IN1_PIN, GPIO.HIGH)
                GPIO.output(self.IN2_PIN, GPIO.LOW)
                time.sleep(1.5)
            if GPIO: GPIO.cleanup()
        except: pass
        try:
            if hasattr(self, 'cap'): self.cap.release()
        except: pass

if __name__ == "__main__":
    DoorLockApp().run()