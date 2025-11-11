import RPi.GPIO as GPIO
import time

# GPIO PIN Setup
TRIG = 23   # TRIG 핀 번호 (BCM 기준)
ECHO = 24   # ECHO 핀 번호 (BCM 기준)

GPIO.setmode(GPIO.BCM)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

print("HC-SR04P distance test")

try:
    while True:
        # Ensure TRIG is LOW initially
        GPIO.output(TRIG, False)
        time.sleep(0.1)

        # Send a 10us trigger pulse
        GPIO.output(TRIG, True)
        time.sleep(0.00001)  # 10 microseconds
        GPIO.output(TRIG, False)

        # Measure echo pulse duration
        while GPIO.input(ECHO) == 0:
            pulse_start = time.time()

        while GPIO.input(ECHO) == 1:
            pulse_end = time.time()

        pulse_duration = pulse_end - pulse_start

        # Convert to distance in cm
        distance = pulse_duration * 17150
        distance = round(distance, 2)

        print("Distance:", distance, "cm")

except KeyboardInterrupt:
    print("Measurement stopped by User")
    GPIO.cleanup()
