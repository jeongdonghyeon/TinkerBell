import threading
import random
import string
import platform
from datetime import datetime
import boto3
import cv2
import numpy as np
import time
import os

from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.lang import Builder
from kivy.graphics.texture import Texture
from kivymd.app import MDApp

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# 라즈베리파이 카메라 모듈3용
from picamera2 import Picamera2

# GPIO
import RPi.GPIO as GPIO

# 폰트 등록
LabelBase.register(name='SpoqaSans', fn_regular='Fonts/Spoqa Han Sans Regular.ttf')


class DoorLockApp(MDApp):

    def build(self):
        self.root = Builder.load_file('doorlock.kv')

        self.rekognition_client = boto3.client('rekognition', region_name='ap-northeast-2')
        self.collection_id = 'family_faces'

        self.is_recognizing = False

        # ✅ 릴레이 GPIO
        self.RELAY_PIN = 17
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.RELAY_PIN, GPIO.OUT)
        GPIO.output(self.RELAY_PIN, GPIO.LOW)

        # Firebase 연결
        try:
            cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred)
            self.db = firestore.client()
        except:
            self.db = None

        # 방문자 저장 폴더
        self.visitor_log_dir = "visitor_logs"
        if not os.path.exists(self.visitor_log_dir):
            os.makedirs(self.visitor_log_dir)

        self.visitor_log_taken = False
        self.frame_lock = threading.Lock()

        return self.root

    def on_start(self):
        try:
            self.picam2 = Picamera2()
            self.picam2.configure(self.picam2.create_preview_configuration())
            self.picam2.start()

            Clock.schedule_interval(self.update_time, 1)
            Clock.schedule_interval(self.update_camera_view, 1/30)
            Clock.schedule_interval(self.recognize_face, 2)

        except Exception as e:
            print(e)
            self.root.ids.status_label.text = "카메라 오류. 재부팅 필요."

    # ✅ 문 열기
    def open_door(self):
        GPIO.output(self.RELAY_PIN, GPIO.HIGH)
        self.root.ids.status_label.text = "문 열림 (10초 후 자동 닫힘)"

        def close_after_delay():
            time.sleep(10)
            GPIO.output(self.RELAY_PIN, GPIO.LOW)
            Clock.schedule_once(lambda dt: self.set_status("문 자동 닫힘"))

        threading.Thread(target=close_after_delay, daemon=True).start()

    def set_status(self, text):
        self.root.ids.status_label.text = text

    # ✅ 카메라 화면 갱신
    def update_camera_view(self, dt):
        try:
            frame = self.picam2.capture_array()
            if frame is None:
                return

            with self.frame_lock:
                self.current_frame = frame.copy()

            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            buf = cv2.flip(frame, 0).tobytes()
            texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt='rgb')
            texture.blit_buffer(buf, colorfmt='rgb', bufferfmt='ubyte')
            self.root.ids.camera_view.texture = texture

        except Exception as e:
            print(e)

    # ✅ 얼굴 인식
    def recognize_face(self, dt):
        if self.is_recognizing or not hasattr(self, 'current_frame'):
            return
        self.is_recognizing = True

        with self.frame_lock:
            frame_copy = self.current_frame.copy()

        _, image_bytes = cv2.imencode('.jpg', frame_copy)
        image_bytes = image_bytes.tobytes()

        try:
            response = self.rekognition_client.search_faces_by_image(
                CollectionId=self.collection_id,
                Image={'Bytes': image_bytes},
                FaceMatchThreshold=95,
                MaxFaces=1
            )

            if response['FaceMatches']:
                similarity = response['FaceMatches'][0]['Similarity']
                self.set_status(f"인증됨 ({similarity:.1f}%) → 문 열림")
                self.open_door()

            else:
                self.set_status("알 수 없는 사용자")

        except Exception as e:
            print(e)

        finally:
            self.is_recognizing = False

    def update_time(self, *args):
        now = datetime.now()
        self.root.ids.time_label.text = now.strftime("%H:%M")
        weekday = "월화수목금토일"[now.weekday()]
        self.root.ids.date_label.text = now.strftime(f"%Y.%m.%d ({weekday})")

    def on_stop(self):
        GPIO.cleanup()
        self.picam2.stop()


if __name__ == '__main__':
    DoorLockApp().run()
