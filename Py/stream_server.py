from flask import Flask, Response
import cv2

# Flask 앱 객체 생성
app = Flask(__name__)

# 카메라 객체 생성 (0번 카메라)
camera = cv2.VideoCapture(0)

def generate_frames():
    """카메라 프레임을 지속적으로 반환하는 제너레이터 함수"""
    while True:
        # 카메라에서 프레임 읽기
        success, frame = camera.read()
        if not success:
            break
        else:
            # 프레임을 JPEG 형식으로 인코딩
            ret, buffer = cv2.imencode('.jpg', frame)
            frame_bytes = buffer.tobytes()

            # HTTP 스트리밍 형식에 맞춰 프레임 데이터를 yield
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video')
def video_feed():
    """비디오 스트리밍 경로"""
    # generate_frames 함수가 반환하는 프레임들을 이용해 Response 객체를 생성
    return Response(generate_frames(),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == '__main__':
    # host='0.0.0.0'는 모든 IP 주소에서 접속 가능하도록 설정
    # threaded=True는 여러 클라이언트의 동시 접속을 처리하기 위함
    app.run(host='0.0.0.0', port=5000, threaded=True)