from datetime import datetime
import cv2
import boto3
import threading
from flask import Flask, Response

from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.lang import Builder  # Builder를 계속 사용합니다.
from kivymd.app import MDApp
from kivy.graphics.texture import Texture


LabelBase.register(name='SpoqaSans', fn_regular='fonts/Spoqa Han Sans Regular.ttf')


flask_app = Flask(__name__)
frame_lock = threading.Lock()
kivy_app_instance = None

def generate_frames():
    global kivy_app_instance
    while True:
        with frame_lock:
            if kivy_app_instance is None or not hasattr(kivy_app_instance, 'current_frame'):
                continue
            frame = kivy_app_instance.current_frame.copy()
        ret, buffer = cv2.imencode('.jpg', frame)
        if not ret:
            continue
        frame_bytes = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@flask_app.route('/video_feed')
def video_feed():
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')
# ----------------------------------------------


class DoorLockApp(MDApp):
    def build(self):
        global kivy_app_instance
        kivy_app_instance = self


        self.root = Builder.load_file('doorlock.kv')

        self.rekognition_client = boto3.client('rekognition', region_name='ap-northeast-2')
        self.collection_id = 'family_faces'
        self.is_recognizing = False
        return self.root


    def on_start(self):
        flask_thread = threading.Thread(target=lambda: flask_app.run(host='0.0.0.0', port=5000, threaded=True))
        flask_thread.daemon = True
        flask_thread.start()

        self.capture = cv2.VideoCapture(0)
        Clock.schedule_interval(self.update_time, 1)
        Clock.schedule_interval(self.update_camera_view, 1.0 / 30.0)
        Clock.schedule_interval(self.recognize_face, 2)

    def on_stop(self):
        self.capture.release()

    def update_camera_view(self, dt):
        ret, frame = self.capture.read()
        if ret:
            with frame_lock:
                self.current_frame = frame
            buf = cv2.flip(frame, 0).tobytes()
            texture = Texture.create(size=(frame.shape[1], frame.shape[0]), colorfmt='bgr')
            texture.blit_buffer(buf, colorfmt='bgr', bufferfmt='ubyte')
            self.root.ids.camera_view.texture = texture

    def recognize_face(self, dt):
        if self.is_recognizing or not hasattr(self, 'current_frame'):
            return
        self.is_recognizing = True
        with frame_lock:
            frame = self.current_frame.copy()
        _, image_bytes = cv2.imencode('.jpg', frame)
        image_bytes = image_bytes.tobytes()
        try:
            response = self.rekognition_client.search_faces_by_image(CollectionId=self.collection_id, Image={'Bytes': image_bytes}, FaceMatchThreshold=95, MaxFaces=1)
            status_label = self.root.ids.status_label
            if response['FaceMatches']:
                matched_face = response['FaceMatches'][0]
                external_image_id = matched_face['Face']['ExternalImageId']
                similarity = matched_face['Similarity']
                current_hour = datetime.now().hour
                if external_image_id == 'patient.jpg' and (current_hour >= 20 or current_hour < 8):
                    status_label.text = "지금은 나가실 수 없습니다."
                else:
                    status_label.text = f"인증되었습니다. ({similarity:.1f}%)"
            else:
                status_label.text = "알 수 없는 사용자입니다."
        except Exception as e:
            if "There are no faces in the image" in str(e): self.root.ids.status_label.text = "얼굴을 감지하고 있습니다..."
            else: print(f"인식 중 오류 발생: {e}")
        finally: self.is_recognizing = False

    def update_time(self, *args):
        now = datetime.now()
        self.root.ids.time_label.text = now.strftime("%H:%M")
        date_str = now.strftime("%Y.%m.%d (") + "월화수목금토일"[now.weekday()] + ")"
        self.root.ids.date_label.text = date_str

    def unlock_door(self):
        self.root.ids.status_label.text = '수동으로 문이 열렸습니다.'

    def lock_door(self):
        self.root.ids.status_label.text = '문이 잠겼습니다.'


if __name__ == '__main__':
    DoorLockApp().run()