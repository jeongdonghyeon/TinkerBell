import RPi.GPIO as GPIO
import time

# Constants
ENA_PIN = 25  # GPIO pin connected to the EN1 pin L298N
IN1_PIN = 8  # GPIO pin connected to the IN1 pin L298N
IN2_PIN = 7  # GPIO pin connected to the IN2 pin L298N

# Setup
GPIO.setmode(GPIO.BCM)
GPIO.setup(ENA_PIN, GPIO.OUT)
GPIO.setup(IN1_PIN, GPIO.OUT)
GPIO.setup(IN2_PIN, GPIO.OUT)

# Set ENA_PIN to HIGH to enable the actuator
GPIO.output(ENA_PIN, GPIO.HIGH)

# Main loop
try:
    while True:
        # Extend the actuator
        GPIO.output(IN1_PIN, GPIO.HIGH)
        GPIO.output(IN2_PIN, GPIO.LOW)

        time.sleep(20)  # Actuator will stop extending automatically when reaching the limit

        # Retract the actuator
        GPIO.output(IN1_PIN, GPIO.LOW)
        GPIO.output(IN2_PIN, GPIO.HIGH)

        time.sleep(20)  # Actuator will stop retracting automatically when reaching the limit

except KeyboardInterrupt:
    pass

finally:
    # Cleanup GPIO on program exit
    GPIO.cleanup()