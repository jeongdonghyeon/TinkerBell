import RPi.GPIO as GPIO
import time

# GPIO 핀 설정 (BCM 모드)
# === 사용자가 연결한 핀 번호 ===
ROW_PINS = [21, 20, 16, 12] # R1, R2, R3, R4
COL_PINS = [26, 19, 13, 6]  # C1, C2, C3, C4
# ===============================

# 키패드 문자 매핑
KEYPAD = [
    ['1', '2', '3', 'A'],
    ['4', '5', '6', 'B'],
    ['7', '8', '9', 'C'],
    ['*', '0', '#', 'D']
]

def setup_gpio():
    # 핀 번호 체계를 BCM으로 설정
    GPIO.setmode(GPIO.BCM)

    # 열(Column) 핀을 출력(OUT)으로 설정, 초기값은 HIGH
    for pin in COL_PINS:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)

    # 행(Row) 핀을 입력(IN)으로 설정, 내부 풀업 저항 사용
    # (버튼이 안 눌리면 HIGH, 눌리면 LOW)
    for pin in ROW_PINS:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

def read_keypad():
    """키패드를 스캔하여 눌린 키를 반환합니다."""

    # 각 열을 순서대로 스캔
    for j, col_pin in enumerate(COL_PINS):
        # 현재 열(j) 핀만 LOW로 설정
        GPIO.output(col_pin, GPIO.LOW)

        # 모든 행(i)을 확인
        for i, row_pin in enumerate(ROW_PINS):
            # 행 핀이 LOW이면 (버튼이 눌렸으면)
            if GPIO.input(row_pin) == GPIO.LOW:
                # 디바운싱(Debouncing): 버튼 떨림 방지
                time.sleep(0.3)

                # 해당 키 반환
                return KEYPAD[i][j]

        # 다음 열 스캔을 위해 현재 열 핀을 다시 HIGH로 복구
        GPIO.output(col_pin, GPIO.HIGH)

    return None # 아무것도 눌리지 않음

# --- 메인 프로그램 ---
try:
    setup_gpio()
    print("키패드 입력을 기다립니다... (Ctrl+C로 종료)")

    while True:
        key = read_keypad()
        if key:
            print(f"눌린 키: {key}")

        time.sleep(0.1) # CPU 점유율을 낮추기 위한 딜레이

except KeyboardInterrupt:
    print("\n프로그램 종료")
finally:
    GPIO.cleanup() # GPIO 핀 초기화