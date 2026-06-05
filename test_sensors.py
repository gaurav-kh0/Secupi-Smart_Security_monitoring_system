import RPi.GPIO as GPIO
import time

PIR_PIN = 17
TRIG = 23
ECHO = 24

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Setup PIR
GPIO.setup(PIR_PIN, GPIO.IN)

# Setup Ultrasonic
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)

print("Calibrating Ultrasonic Sensor...")
GPIO.output(TRIG, False)
time.sleep(2)

print("====================================")
print(" Combined RPi.GPIO Sensor Test")
print("====================================")
print(f"PIR Pin: GPIO {PIR_PIN}")
print(f"Ultrasonic TRIG: GPIO {TRIG}")
print(f"Ultrasonic ECHO: GPIO {ECHO}")
print("Press Ctrl+C to exit.\n")

try:
    while True:
        # --- 1. Read PIR Sensor ---
        if GPIO.input(PIR_PIN):
            pir_status = "DETECTED"
        else:
            pir_status = "Clear"

        # --- 2. Read Ultrasonic Sensor ---
        GPIO.output(TRIG, True)
        time.sleep(0.00001)
        GPIO.output(TRIG, False)

        pulse_start = time.time()
        pulse_end = time.time()

        # Note: Added a 0.1s timeout to the while loops. 
        # Without this, if the ECHO pin wire is loose, the python script will freeze forever.
        timeout = time.time() + 0.1
        while GPIO.input(ECHO) == 0 and time.time() < timeout:
            pulse_start = time.time()

        timeout = time.time() + 0.1
        while GPIO.input(ECHO) == 1 and time.time() < timeout:
            pulse_end = time.time()

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        distance = round(distance, 2)

        print(f"PIR Motion: {pir_status:<10} | Distance: {distance} cm")

        time.sleep(1)

except KeyboardInterrupt:
    print("\nTest stopped. Cleaning up GPIO...")
    GPIO.cleanup()
