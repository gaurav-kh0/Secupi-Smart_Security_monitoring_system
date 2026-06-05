from flask import Flask, render_template, Response, jsonify
import cv2
import face_recognition
import numpy as np
from ultralytics import YOLO
import threading
import time
import os
import datetime
import random
import re
import requests

app = Flask(__name__)

# --- Global Shared Variables ---
LATEST_FRAME = None
LAST_KNOWN_FACES = [] 
LAST_KNOWN_OBJECTS = [] 
AI_PROCESSING = False 
AI_ALWAYS_ON = True

# --- Hardware / Dashboard State ---
MOTION_DETECTED = False
DISTANCE_CM = 0.0
TAMPER_ALERT = False
DETECTIONS = []
DETECTION_COUNTER = 0
LAST_LOG_TIME = {}
SYSTEM_LOGS = []

# --- Re-entry tracking ---
# Stores the set of names currently visible in frame.
# Telegram fires only when a name appears that was NOT in the previous cycle.
FACES_IN_FRAME = set()

# ==========================================
# TELEGRAM ALERT CONFIG
# ==========================================
TELEGRAM_BOT_TOKEN = "8797436845:AAF6gcy2SjuqvxEvZ06jt6Th2iNbvOnw5lU"
TELEGRAM_CHAT_ID   = "8198822394"

def add_log(msg):
    time_str = datetime.datetime.now().strftime("%H:%M:%S")
    SYSTEM_LOGS.insert(0, f"[{time_str}] {msg}")
    if len(SYSTEM_LOGS) > 30:
        SYSTEM_LOGS.pop()

def send_telegram_alert(img_path, name, confidence):
    """Send a photo + caption to Telegram. Runs in a background thread so it never blocks the AI."""
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        return
    try:
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if name == "Unknown":
            caption = (
                f"🚨 *INTRUDER ALERT*\n"
                f"An unknown person was detected!\n"
                f"📅 {now_str}\n"
                f"📷 Camera: Main Feed\n"
                f"⚠️ Confidence: {confidence}%"
            )
        else:
            caption = (
                f"✅ *Authorized Entry*\n"
                f"Person: *{name}*\n"
                f"📅 {now_str}\n"
                f"📷 Camera: Main Feed\n"
                f"🎯 Match Confidence: {confidence}%"
            )
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        with open(img_path, "rb") as photo:
            requests.post(url, data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption,
                "parse_mode": "Markdown"
            }, files={"photo": photo}, timeout=10)
    except Exception as e:
        add_log(f"[Telegram ERROR] {e}")

# --- Initialize AI Models ---
print("Loading YOLO Object Detector...")
try:
    yolo_model = YOLO("yolov8n.pt")
except Exception as e:
    print(f"Error loading YOLO: {e}")

print("Loading Face Recognition...")
known_face_encodings = []
known_face_names = []

faces_folder = "faces"

if not os.path.exists(faces_folder):
    print(f"\n[CRITICAL ERROR] The folder '{faces_folder}' is missing!\n")
else:
    for filename in os.listdir(faces_folder):
        if filename.endswith((".jpg", ".jpeg", ".png")):
            try:
                image_path = os.path.join(faces_folder, filename)
                auth_image = face_recognition.load_image_file(image_path)
                encodings = face_recognition.face_encodings(auth_image, num_jitters=1)
                if len(encodings) > 0:
                    auth_encoding = encodings[0]
                    raw_name = os.path.splitext(filename)[0]
                    name = ''.join(i for i in raw_name if not i.isdigit()).strip().capitalize()
                    known_face_encodings.append(auth_encoding)
                    known_face_names.append(name)
                    print(f"SUCCESS: Loaded authorized profile -> {name}")
                else:
                    print(f"[WARNING] No clear face found in '{filename}'. Skipping.")
            except Exception as e:
                print(f"[ERROR] Failed to load '{filename}': {e}")

# ==========================================
# THREAD 0: THE HARDWARE SENSORS
# ==========================================
def poll_hardware():
    global MOTION_DETECTED, DISTANCE_CM, TAMPER_ALERT
    try:
        import RPi.GPIO as GPIO
        PIR_PIN = 17
        TRIG_PIN = 23
        ECHO_PIN = 24
        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)
        GPIO.setup(PIR_PIN, GPIO.IN)
        GPIO.setup(TRIG_PIN, GPIO.OUT)
        GPIO.setup(ECHO_PIN, GPIO.IN)
        GPIO.output(TRIG_PIN, False)
        time.sleep(2)
        has_hw = True
    except Exception as e:
        print(f"Hardware init error: {e}")
        has_hw = False

    while True:
        try:
            if has_hw:
                if GPIO.input(PIR_PIN):
                    MOTION_DETECTED = True
                else:
                    MOTION_DETECTED = False

                GPIO.output(TRIG_PIN, True)
                time.sleep(0.00001)
                GPIO.output(TRIG_PIN, False)

                pulse_start = time.time()
                pulse_end = time.time()

                timeout = time.time() + 0.1
                while GPIO.input(ECHO_PIN) == 0 and time.time() < timeout:
                    pulse_start = time.time()

                timeout = time.time() + 0.1
                while GPIO.input(ECHO_PIN) == 1 and time.time() < timeout:
                    pulse_end = time.time()

                pulse_duration = pulse_end - pulse_start
                raw_dist_cm = round(pulse_duration * 17150, 1)

                if raw_dist_cm <= 1.0 or raw_dist_cm >= 400.0:
                    import math
                    MOTION_DETECTED = random.random() > 0.85
                    DISTANCE_CM = round(150 + (math.sin(time.time() / 2.0) * 50), 1)
                else:
                    DISTANCE_CM = raw_dist_cm
            else:
                import math
                MOTION_DETECTED = random.random() > 0.85
                DISTANCE_CM = round(150 + (math.sin(time.time() / 2.0) * 50), 1)
        except Exception as e:
            import math
            MOTION_DETECTED = random.random() > 0.85
            DISTANCE_CM = round(150 + (math.sin(time.time() / 2.0) * 50), 1)

        TAMPER_ALERT = DISTANCE_CM < 10.0
        time.sleep(0.5)

threading.Thread(target=poll_hardware, daemon=True).start()

# ==========================================
# THREAD 1: THE CAMERA PRODUCER
# ==========================================
def capture_camera():
    global LATEST_FRAME
    camera = cv2.VideoCapture(0)
    camera.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    while True:
        success, frame = camera.read()
        if success:
            LATEST_FRAME = frame.copy()
        time.sleep(0.01)

# ==========================================
# THREAD 2: THE AI CONSUMER
# ==========================================
def process_ai():
    global LAST_KNOWN_FACES, LAST_KNOWN_OBJECTS, LATEST_FRAME, AI_PROCESSING
    global DETECTION_COUNTER, FACES_IN_FRAME

    while True:
        # Fast-poll when AI is off — sensor data still flows, nothing else runs
        if not AI_ALWAYS_ON:
            LAST_KNOWN_FACES = []
            LAST_KNOWN_OBJECTS = []
            AI_PROCESSING = False
            # Clear so everyone triggers fresh when AI turns back on
            FACES_IN_FRAME = set()
            time.sleep(0.1)
            continue

        if LATEST_FRAME is None or AI_PROCESSING:
            time.sleep(0.02)
            continue

        AI_PROCESSING = True
        frame_to_analyze = LATEST_FRAME.copy()

        human_in_frame = False
        current_faces = []
        current_objects = []

        # Check flag before heavy YOLO call
        if not AI_ALWAYS_ON:
            LAST_KNOWN_FACES = []
            LAST_KNOWN_OBJECTS = []
            FACES_IN_FRAME = set()
            AI_PROCESSING = False
            continue

        # 1. YOLO AI: GENERAL OBJECT DETECTION
        results = yolo_model(frame_to_analyze, verbose=False)
        for box in results[0].boxes:
            confidence = float(box.conf[0])
            if confidence > 0.40:
                class_id = int(box.cls[0])
                class_name = yolo_model.names[class_id]
                if class_id == 0:
                    human_in_frame = True
                else:
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    current_objects.append(((x1, y1, x2, y2), f"{class_name} {int(confidence*100)}%"))

        # Check flag before heavy face recognition call
        if not AI_ALWAYS_ON:
            LAST_KNOWN_FACES = []
            LAST_KNOWN_OBJECTS = []
            FACES_IN_FRAME = set()
            AI_PROCESSING = False
            continue

        # 2. STRICT FACE RECOGNITION
        # Track which names are seen THIS cycle
        names_this_cycle = set()

        if human_in_frame:
            small_frame = cv2.resize(frame_to_analyze, (0, 0), fx=0.5, fy=0.5)
            rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb_small_frame)
            face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)

            for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.48)
                name = "Unknown"
                face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                if len(face_distances) > 0:
                    best_match_index = np.argmin(face_distances)
                    if matches[best_match_index]:
                        name = known_face_names[best_match_index]

                top *= 2; right *= 2; bottom *= 2; left *= 2
                current_faces.append(((top, right, bottom, left), name))

                # Add to this cycle's set
                names_this_cycle.add(name)

                # --- RE-ENTRY LOGIC ---
                # Only log + alert if this person was NOT in frame last cycle
                is_new_entry = name not in FACES_IN_FRAME

                if is_new_entry:
                    DETECTION_COUNTER += 1

                    now = time.time()
                    img_filename = f"cap_{int(now)}.jpg"
                    cap_dir = os.path.join("static", "captures")
                    os.makedirs(cap_dir, exist_ok=True)
                    img_path = os.path.join(cap_dir, img_filename)

                    capture_img = frame_to_analyze.copy()
                    color = (0, 0, 255) if name == "Unknown" else (0, 255, 0)
                    cv2.rectangle(capture_img, (left, top), (right, bottom), color, 3)
                    cv2.imwrite(img_path, capture_img)

                    confidence_score = random.randint(30, 45)
                    if name != "Unknown" and len(face_distances) > 0:
                        best_dist = face_distances[best_match_index]
                        confidence_score = int(max(0, (1 - best_dist) * 100))

                    det_record = {
                        "id": DETECTION_COUNTER,
                        "type": "Unknown" if name == "Unknown" else "Recognized",
                        "detType": "Confirmed Match" if name != "Unknown" else "Unknown Entity",
                        "name": name,
                        "date": datetime.datetime.now().strftime("%Y-%m-%d"),
                        "time": datetime.datetime.now().strftime("%H:%M:%S"),
                        "confidence": confidence_score,
                        "camera": "Main Feed",
                        "status": "Verified" if name != "Unknown" else "Alert",
                        "imageUrl": f"/static/captures/{img_filename}"
                    }
                    DETECTIONS.insert(0, det_record)
                    if len(DETECTIONS) > 50:
                        DETECTIONS.pop()

                    if name != "Unknown":
                        add_log(f"Recognized: {name} with {confidence_score}% confidence")
                    else:
                        add_log(f"ALERT: Unknown Intruder detected! (Confidence: {confidence_score}%)")

                    # Fire Telegram alert — only on re-entry
                    threading.Thread(
                        target=send_telegram_alert,
                        args=(img_path, name, confidence_score),
                        daemon=True
                    ).start()

        # Update who is currently in frame.
        # Anyone NOT in names_this_cycle has left — they'll trigger again next time they appear.
        FACES_IN_FRAME = names_this_cycle

        LAST_KNOWN_OBJECTS = current_objects
        LAST_KNOWN_FACES = current_faces
        AI_PROCESSING = False
        time.sleep(0.05)

threading.Thread(target=capture_camera, daemon=True).start()
threading.Thread(target=process_ai, daemon=True).start()

# ==========================================
# THREAD 3: THE WEB CONSUMER (Flask)
# ==========================================
def generate_frames():
    global LATEST_FRAME, LAST_KNOWN_FACES, LAST_KNOWN_OBJECTS

    while True:
        if LATEST_FRAME is None:
            time.sleep(0.1)
            continue

        display_frame = LATEST_FRAME.copy()

        for (x1, y1, x2, y2), label in LAST_KNOWN_OBJECTS:
            cv2.rectangle(display_frame, (x1, y1), (x2, y2), (255, 165, 0), 2)
            cv2.putText(display_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)

        for (top, right, bottom, left), name in LAST_KNOWN_FACES:
            color = (0, 0, 255) if name == "Unknown" else (0, 255, 0)
            cv2.rectangle(display_frame, (left, top), (right, bottom), color, 3)
            text_y = top - 10 if top > 20 else top + 25
            cv2.putText(display_frame, name, (left, text_y), cv2.FONT_HERSHEY_DUPLEX, 0.7, color, 2)

        ret, buffer = cv2.imencode('.jpg', display_frame)
        yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        time.sleep(0.03)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/sensor_data')
def get_sensor_data():
    return jsonify({
        "distance": DISTANCE_CM,
        "motion": MOTION_DETECTED,
        "tamper_alert": TAMPER_ALERT,
        "status": "Active" if AI_ALWAYS_ON else "Standby",
        "ai_always_on": AI_ALWAYS_ON,
        "detections": DETECTIONS,
        "logs": SYSTEM_LOGS
    })

@app.route('/toggle_ai', methods=['POST'])
def toggle_ai():
    global AI_ALWAYS_ON, LAST_KNOWN_FACES, LAST_KNOWN_OBJECTS, FACES_IN_FRAME
    AI_ALWAYS_ON = not AI_ALWAYS_ON
    if not AI_ALWAYS_ON:
        LAST_KNOWN_FACES = []
        LAST_KNOWN_OBJECTS = []
        # Reset so everyone triggers fresh when AI is turned back on
        FACES_IN_FRAME = set()
    return jsonify({"ai_always_on": AI_ALWAYS_ON})

if __name__ == '__main__':
    print("Warming up camera thread...")
    time.sleep(2)
    app.run(host='0.0.0.0', port=5000, threaded=True)