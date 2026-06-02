from flask import Flask, render_template, Response, jsonify
import os
import sys
import threading
import time
import datetime
import requests

# Strict physical hardware imports
try:
    import RPi.GPIO as GPIO
    import cv2
    import face_recognition
    import numpy as np
    from ultralytics import YOLO
except ImportError as e:
    print(f"FATAL: Missing real-time dependency: {e}")
    print("This system now strictly requires Raspberry Pi hardware and vision libraries.")
    sys.exit(1)

app = Flask(__name__)

# Make sure captures directory is available for storing event images
os.makedirs("static/captures", exist_ok=True)

# Save sample image as fallback
fallback_canvas = np.zeros((240, 320, 3), dtype=np.uint8)
fallback_canvas[:] = [248, 233, 214] # Light blue theme
cv2.putText(fallback_canvas, "SecuPi Event Capture", (20, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (15, 128, 21), 2)
cv2.imwrite("static/captures/sample.png", fallback_canvas)

# ==========================================
# 0. TELEGRAM CONFIGURATION
# ==========================================
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"

# ==========================================
# 1. HARDWARE CONFIGURATION (RPi 5 GPIO BCM)
# ==========================================
TRIG, ECHO = 23, 24
PIR_PIN = 17
GREEN_LED, RED_LED = 27, 22

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(TRIG, GPIO.OUT)
GPIO.setup(ECHO, GPIO.IN)
GPIO.setup(PIR_PIN, GPIO.IN)
GPIO.setup(GREEN_LED, GPIO.OUT)
GPIO.setup(RED_LED, GPIO.OUT)

# Reset lights to off on bootup
GPIO.output(GREEN_LED, False)
GPIO.output(RED_LED, False)
GPIO.output(TRIG, False)

# ==========================================
# 2. GLOBAL STATE & MEMORY QUEUES
# ==========================================
LATEST_FRAME = None
LAST_KNOWN_FACES = []
LAST_KNOWN_OBJECTS = []
RECENT_LOGS = [] 
DETECTION_EVENTS = [] 

SYSTEM_STATE = {
    "motion": False,
    "distance": 0.0,
    "status": "Standby - Camera Active",
    "tamper_alert": False,
    "ai_always_on": False, # Switch control state for continuous AI
    "logs": RECENT_LOGS
}

LAST_MOTION_TIME = 0
IDLE_TIMEOUT = 10 

PERSON_COOLDOWNS = {}
LAST_ALERT_TIME = 0

# ==========================================
# 3. LOGGING & EVENT CAPTURE SYSTEM
# ==========================================
def write_log(event_type, details):
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    time_only = timestamp.split(' ')[1]
    
    # Save to local persistent log CSV
    with open("security_log.csv", "a") as f:
        f.write(f"{timestamp},{event_type},{details}\n")
        
    log_string = f"[{time_only}] {event_type}: {details}"
    RECENT_LOGS.insert(0, log_string)
    if len(RECENT_LOGS) > 15:
        RECENT_LOGS.pop()
        
    print(f">> LOG: {log_string}")

def add_detection_event(type_name, name, confidence, frame=None):
    """
    Saves a captured vision detection event, saves frame to disk, 
    and appends a structured record for the frontend AJAX dashboard.
    """
    event_id = f"DET-{int(time.time() * 10) % 1000000}"
    timestamp = datetime.datetime.now().strftime("%I:%M %p")
    date_str = datetime.datetime.now().strftime("%d %B %Y")
    
    img_name = f"det_{event_id}.jpg"
    img_path = os.path.join("static", "captures", img_name)
    img_url = f"/static/captures/{img_name}"
    
    # Save actual camera frame
    if frame is not None and cv2 is not None:
        cv2.imwrite(img_path, frame)
    else:
        # Draw a beautiful OpenCV visual card as placeholder if libraries are missing/Windows
        if np is not None and cv2 is not None:
            canvas = np.zeros((480, 640, 3), dtype=np.uint8)
            canvas[:] = [248, 233, 214] # Sky-blue background (#D6E9F8 BGR)
            color = (34, 197, 22) if type_name == "Recognized" else (68, 68, 239) # Green vs Red BGR
            # Draw targeting grid
            cv2.circle(canvas, (320, 240), 90, color, 3)
            cv2.circle(canvas, (320, 240), 8, color, -1)
            cv2.rectangle(canvas, (180, 70), (460, 410), color, 4)
            # Metadata text
            cv2.putText(canvas, f"ID: {event_id}", (190, 110), cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
            cv2.putText(canvas, name, (190, 350), cv2.FONT_HERSHEY_DUPLEX, 0.85, color, 2)
            cv2.putText(canvas, f"Conf: {confidence}%", (190, 385), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            cv2.imwrite(img_path, canvas)
            
    det_event = {
        "id": event_id,
        "type": type_name, # "Unknown" or "Recognized"
        "detType": "Unknown Person" if type_name == "Unknown" else ("Confirmed Match" if confidence > 80 else "Possible Match"),
        "name": name if type_name == "Recognized" else "—",
        "imageUrl": img_url,
        "time": timestamp,
        "date": date_str,
        "status": "ALERT" if type_name == "Unknown" else "Verified",
        "camera": "Front Lobby Camera",
        "confidence": confidence
    }
    
    DETECTION_EVENTS.insert(0, det_event)
    if len(DETECTION_EVENTS) > 50:
        # Limit memory queue size and clean up associated file
        old_event = DETECTION_EVENTS.pop()
        try:
            old_path = old_event["imageUrl"].lstrip("/")
            if os.path.exists(old_path):
                os.remove(old_path)
        except Exception:
            pass
            
    # Auto log the vision update in activity log window
    write_log("AI_VISION" if type_name == "Recognized" else "ALERT", f"Spotted {name} ({confidence}% Match)")
    return det_event

write_log("SYSTEM", "CCTV Engine Booted Up")

# ==========================================
# 4. INITIALIZE AI MODELS
# ==========================================
yolo_model = None
if YOLO is not None:
    print("Loading YOLO Object Detector...")
    try:
        yolo_model = YOLO("yolov8n.pt") 
    except Exception as e:
        print(f"YOLO load failure: {e}")

known_face_encodings = []
known_face_names = []

if face_recognition is not None:
    print("Loading Face Recognition Registry...")
    faces_folder = "faces"
    if os.path.exists(faces_folder):
        for filename in os.listdir(faces_folder):
            if filename.endswith((".jpg", ".jpeg", ".png")):
                try:
                    img_path = os.path.join(faces_folder, filename)
                    auth_image = face_recognition.load_image_file(img_path)
                    auth_encoding = face_recognition.face_encodings(auth_image, num_jitters=1)[0]
                    name = os.path.splitext(filename)[0].capitalize()
                    known_face_encodings.append(auth_encoding)
                    known_face_names.append(name)
                    print(f"Authorized Profile Loaded: {name}")
                except Exception as e:
                    pass

# ==========================================
# THREAD 1: TELEGRAM WORKER
# ==========================================
def send_telegram_alert(frame_to_send, trigger_reason):
    if not TELEGRAM_BOT_TOKEN or TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or cv2 is None:
        return

    try:
        ret, buffer = cv2.imencode('.jpg', frame_to_send)
        if not ret: return
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        files = {'photo': ('alert.jpg', buffer.tobytes(), 'image/jpeg')}
        data = {'chat_id': TELEGRAM_CHAT_ID, 'caption': f'🚨 {trigger_reason} 🚨'}
        requests.post(url, files=files, data=data)
    except Exception as e:
        pass

# ==========================================
# THREAD 2: HARDWARE MONITOR (Sensors)
# ==========================================
def get_distance():
    try:
        # High resolution distance measurement using performance counters
        GPIO.output(TRIG, True)
        time.sleep(0.00001)
        GPIO.output(TRIG, False)
        
        pulse_start = pulse_end = time.perf_counter()
        timeout_start = time.perf_counter()
        
        # Capped microsecond check to prevent crazy high values
        # Wait for Echo to go high (with 20ms timeout = ~340cm physical range)
        while GPIO.input(ECHO) == 0:
            pulse_start = time.perf_counter()
            if pulse_start - timeout_start > 0.02:
                return 400.0
                
        # Wait for Echo to go low (with 20ms timeout)
        while GPIO.input(ECHO) == 1:
            pulse_end = time.perf_counter()
            if pulse_end - pulse_start > 0.02:
                return 400.0
                
        duration = pulse_end - pulse_start
        distance = round(duration * 17150, 1)
        return distance
    except Exception:
        return 400.0

def hardware_loop():
    global LAST_MOTION_TIME
    tamper_triggered = False
    motion_triggered = False

    while True:
        dist = get_distance()
        SYSTEM_STATE["distance"] = dist
        is_tampered = dist < 10.0
        SYSTEM_STATE["tamper_alert"] = is_tampered
        
        if is_tampered and not tamper_triggered:
            write_log("ALERT", f"Tamper detected! Distance: {dist}cm")
            tamper_triggered = True
        elif not is_tampered:
            tamper_triggered = False
            
        if GPIO.input(PIR_PIN):
            LAST_MOTION_TIME = time.time()
            SYSTEM_STATE["motion"] = True
            SYSTEM_STATE["status"] = "Active - Motion Alert Triggered"
            if not motion_triggered:
                write_log("HARDWARE", "Motion detected, AI processes active.")
                motion_triggered = True
        elif time.time() - LAST_MOTION_TIME > IDLE_TIMEOUT:
            SYSTEM_STATE["motion"] = False
            if SYSTEM_STATE.get("ai_always_on", False):
                SYSTEM_STATE["status"] = "Active - AI Always-On Mode"
            else:
                SYSTEM_STATE["status"] = "Standby - Camera Active"
            if motion_triggered:
                write_log("HARDWARE", "Area clear, entering AI standby.")
                motion_triggered = False
            
        time.sleep(0.75)  # Reduced hardware polling to lower CPU load

# ==========================================
# THREAD 3: CAMERA & AI PIPELINE
# ==========================================
def process_ai():
    global LATEST_FRAME, LAST_KNOWN_FACES, LAST_KNOWN_OBJECTS, LAST_ALERT_TIME

    camera = cv2.VideoCapture(0)
    while True:
        success, frame = camera.read()
        if not success: 
            time.sleep(0.01)
            continue
            
        ai_enabled = SYSTEM_STATE["motion"] or SYSTEM_STATE.get("ai_always_on", False)
        
        human_in_frame = False
        current_faces = []
        current_objects = []
        intruder_spotted = False
        auth_spotted = False
        current_time = time.time()

        # Perform YOLO and Face AI *only* if enabled by motion or switch
        if ai_enabled:
            # Step 1: YOLO Object Detection
            results = yolo_model(frame, verbose=False)
            for box in results[0].boxes:
                conf = float(box.conf[0])
                if conf > 0.30:
                    class_id = int(box.cls[0])
                    class_name = yolo_model.names[class_id]
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    
                    if class_id == 0: human_in_frame = True 
                    else: current_objects.append(((x1, y1, x2, y2), f"{class_name} {int(conf*100)}%"))

            faces_processed = []

            # Step 2: Face Recognition Pipeline
            if human_in_frame:
                small_frame = cv2.resize(frame, (0, 0), fx=0.25, fy=0.25)
                rgb_small_frame = cv2.cvtColor(small_frame, cv2.COLOR_BGR2RGB)
                
                face_locations = face_recognition.face_locations(rgb_small_frame)
                face_encodings = face_recognition.face_encodings(rgb_small_frame, face_locations)
                
                for (top, right, bottom, left), face_encoding in zip(face_locations, face_encodings):
                    matches = face_recognition.compare_faces(known_face_encodings, face_encoding, tolerance=0.55)
                    name = "Unknown Intruder"
                    
                    face_distances = face_recognition.face_distance(known_face_encodings, face_encoding)
                    if len(face_distances) > 0:
                        best_match_index = np.argmin(face_distances)
                        if matches[best_match_index]:
                            name = known_face_names[best_match_index]
                            auth_spotted = True
                    
                    if name == "Unknown Intruder": 
                        intruder_spotted = True
                    
                    top *= 4; right *= 4; bottom *= 4; left *= 4
                    current_faces.append(((top, right, bottom, left), name))
                    faces_processed.append(name)

                    # Event log & capture (with a 2-minute testing cooldown)
                    last_seen = PERSON_COOLDOWNS.get(name, 0)
                    if current_time - last_seen > 120:
                        PERSON_COOLDOWNS[name] = current_time
                        
                        # Annotate the picture frame explicitly to embed AI model markers
                        capture_frame = frame.copy()
                        color = (0, 255, 0) if name != "Unknown Intruder" else (0, 0, 255)
                        cv2.rectangle(capture_frame, (left, top), (right, bottom), color, 3)
                        cv2.putText(capture_frame, name, (left + 6, bottom - 8), cv2.FONT_HERSHEY_DUPLEX, 0.7, color, 2)
                        
                        confidence_score = 35 if name == "Unknown Intruder" else int((1 - face_distances[best_match_index]) * 100) if len(face_distances) > 0 else 92
                        add_detection_event("Unknown" if name == "Unknown Intruder" else "Recognized", name, confidence_score, capture_frame)
                        
                        if name == "Unknown Intruder" and (current_time - LAST_ALERT_TIME > 60):
                            threading.Thread(target=send_telegram_alert, args=(capture_frame.copy(), "Unknown Person Detected!")).start()
                            LAST_ALERT_TIME = current_time

            # YOLO saw a human, but face recognition couldn't extract any faces (e.g. facing away)
            # Log as Unknown Intruder instantly using body bounding frames
            if human_in_frame and len(faces_processed) == 0:
                intruder_spotted = True
                name = "Unknown Intruder"
                
                last_seen = PERSON_COOLDOWNS.get(name, 0)
                if current_time - last_seen > 120: # 2-minute cooldown
                    PERSON_COOLDOWNS[name] = current_time
                    
                    capture_frame = frame.copy()
                    # Find and draw YOLO body bounding box
                    for box in results[0].boxes:
                        if int(box.cls[0]) == 0:
                            x1, y1, x2, y2 = map(int, box.xyxy[0])
                            cv2.rectangle(capture_frame, (x1, y1), (x2, y2), (0, 0, 255), 3)
                            cv2.putText(capture_frame, "Unknown Intruder (Body Detected)", (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 0, 255), 2)
                            break
                    else:
                        cv2.putText(capture_frame, "Unknown Intruder Detected", (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 0, 255), 2)
                        
                    add_detection_event("Unknown", name, 42, capture_frame)
                    
                    if current_time - LAST_ALERT_TIME > 60:
                        threading.Thread(target=send_telegram_alert, args=(capture_frame.copy(), "Unknown Intruder Detected!")).start()
                        LAST_ALERT_TIME = current_time

            # Step 3: Precise physical LED warning outputs
            if SYSTEM_STATE["tamper_alert"] or intruder_spotted:
                GPIO.output(RED_LED, True)   
                GPIO.output(GREEN_LED, False)
            elif auth_spotted:
                GPIO.output(GREEN_LED, True)  
                GPIO.output(RED_LED, False)
            else:
                GPIO.output(GREEN_LED, False)
                GPIO.output(RED_LED, False)
        else:
            # Standby (AI disabled) -> clear LED lights
            GPIO.output(GREEN_LED, False)
            GPIO.output(RED_LED, False)

        LAST_KNOWN_OBJECTS = current_objects if ai_enabled else []
        LAST_KNOWN_FACES = current_faces if ai_enabled else []
        LATEST_FRAME = frame.copy()
        time.sleep(0.15)  # Drop AI frame rate target to ~6 FPS to save CPU
        
threading.Thread(target=hardware_loop, daemon=True).start()
threading.Thread(target=process_ai, daemon=True).start()

# ==========================================
# THREAD 4: THE WEB SERVER (Flask)
# ==========================================
def generate_stream():
    global LATEST_FRAME, LAST_KNOWN_FACES, LAST_KNOWN_OBJECTS
    
    while True:
        if LATEST_FRAME is None:
            time.sleep(0.1)
            continue
            
        display_frame = LATEST_FRAME.copy()
        
        # Overlay active object bounding frames
        if cv2 is not None:
            for (x1, y1, x2, y2), label in LAST_KNOWN_OBJECTS:
                cv2.rectangle(display_frame, (x1, y1), (x2, y2), (255, 165, 0), 2)
                cv2.putText(display_frame, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 165, 0), 2)

            # Overlay face bounding boxes
            for (top, right, bottom, left), name in LAST_KNOWN_FACES:
                color = (0, 0, 255) if name == "Unknown Intruder" else (0, 255, 0)
                cv2.rectangle(display_frame, (left, top), (right, bottom), color, 3)
                cv2.putText(display_frame, name, (left + 6, bottom - 6), cv2.FONT_HERSHEY_DUPLEX, 0.7, color, 1)

            ret, buffer = cv2.imencode('.jpg', display_frame)
            yield (b'--frame\r\nContent-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        else:
            time.sleep(0.1)
            
        time.sleep(0.1)  # Reduce video stream FPS to 10 FPS

@app.route('/')
def index(): 
    return render_template('index.html')

@app.route('/video_feed')
def video_feed(): 
    return Response(generate_stream(), mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/sensor_data')
def get_sensor_data():
    SYSTEM_STATE["logs"] = RECENT_LOGS 
    SYSTEM_STATE["detections"] = DETECTION_EVENTS
    return jsonify(SYSTEM_STATE)

@app.route('/toggle_ai', methods=['POST'])
def toggle_ai():
    """
    Toggles the Always-On AI analysis mode, bypasses PIR motion triggers, 
    and keeps the YOLO/Face scanner executing continuously.
    """
    current = SYSTEM_STATE.get("ai_always_on", False)
    SYSTEM_STATE["ai_always_on"] = not current
    
    if SYSTEM_STATE["ai_always_on"]:
        SYSTEM_STATE["status"] = "Active - AI Always-On Mode"
        write_log("SYSTEM", "Always-On AI Analysis Activated")
    else:
        if SYSTEM_STATE["motion"]:
            SYSTEM_STATE["status"] = "Active - Motion Alert Triggered"
        else:
            SYSTEM_STATE["status"] = "Standby - Camera Active"
        write_log("SYSTEM", "Always-On AI Analysis Standby Mode")
        
    return jsonify({"success": True, "ai_always_on": SYSTEM_STATE["ai_always_on"]})



if __name__ == '__main__':
    try:
        app.run(host='0.0.0.0', port=5000, threaded=True)
    finally:
        GPIO.cleanup()
