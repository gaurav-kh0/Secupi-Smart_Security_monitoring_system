import face_recognition
import numpy as np
import cv2
import os

print("\n--- INITIATING FACIAL RECOGNITION SIMULATION ---\n")

def run_simulation():
    # 1. Load Registry
    registry_names = ["Parth", "Aditya"]
    registry_encodings = []
    
    print("1. Loading Authorised Registry...")
    for name in registry_names:
        filename = f"faces/{name.lower()}.jpeg"
        if os.path.exists(filename):
            image = face_recognition.load_image_file(filename)
            encoding = face_recognition.face_encodings(image)[0]
            registry_encodings.append(encoding)
            print(f"   [+] Loaded {name}'s face profile.")
        else:
            print(f"   [-] WARNING: {filename} not found.")

    if len(registry_encodings) == 0:
        print("No faces loaded to test.")
        return

    # 2. Simulate Webcam Feeds
    print("\n2. Simulating Live Camera Feeds with Bad Lighting/Blur...")
    
    # We will simulate a webcam feed of Parth but apply blur and noise to simulate a bad camera
    if os.path.exists("faces/parth.jpeg"):
        test_img = cv2.imread("faces/parth.jpeg")
        # Apply heavy blur to simulate distance/motion blur
        test_img_blurred = cv2.GaussianBlur(test_img, (15, 15), 0)
        # Convert back to RGB for face_recognition
        rgb_test = cv2.cvtColor(test_img_blurred, cv2.COLOR_BGR2RGB)
        
        print("\n>> SCENARIO A: Bad lighting/blurry image of Parth walks in.")
        face_locations = face_recognition.face_locations(rgb_test)
        if len(face_locations) > 0:
            test_encoding = face_recognition.face_encodings(rgb_test, face_locations)[0]
            
            # Run comparison math
            face_distances = face_recognition.face_distance(registry_encodings, test_encoding)
            best_match_index = np.argmin(face_distances)
            best_dist = face_distances[best_match_index]
            
            print(f"   -> Mathematical Face Distance: {best_dist:.3f}")
            
            # Old strict logic
            if best_dist <= 0.40:
                print(f"   -> [OLD v1.0 THRESHOLD]: Match successful! Identity: {registry_names[best_match_index]}")
            else:
                print(f"   -> [OLD v1.0 THRESHOLD]: Match failed! AI labelled as: UNKNOWN (Intruder Alert)")
                
            # New relaxed logic
            if best_dist <= 0.52:
                print(f"   -> [NEW v2.0 THRESHOLD]: Match successful! Identity: {registry_names[best_match_index]}")
            else:
                print(f"   -> [NEW v2.0 THRESHOLD]: Match failed! AI labelled as: UNKNOWN")
                
        else:
            print("   -> No face detected in blurred image.")
            
    # Simulate an actual intruder (we'll compare Aditya to Parth's profile)
    print("\n>> SCENARIO B: Unknown Stranger (Simulated by cross-checking Aditya vs Parth).")
    if len(registry_encodings) > 1:
        # Cross check
        face_distances = face_recognition.face_distance([registry_encodings[0]], registry_encodings[1])
        best_dist = face_distances[0]
        print(f"   -> Mathematical Face Distance (Stranger vs Parth): {best_dist:.3f}")
        
        if best_dist <= 0.52:
            print(f"   -> CRITICAL FAILURE: Stranger falsely matched as Parth!")
        else:
            print(f"   -> [NEW v2.0 THRESHOLD]: Match safely rejected! Identity: UNKNOWN (Intruder Alert)")

    print("\n--- SIMULATION COMPLETE ---\n")

try:
    run_simulation()
except Exception as e:
    print(f"Simulation error: {e}")
