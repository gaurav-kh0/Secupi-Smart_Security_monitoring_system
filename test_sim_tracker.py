import time

print("\n--- INITIATING YOLO PERSISTENT TRACKING SIMULATION ---\n")

# Fake Global Cache
TRACKED_FACES = {}
known_faces_database = ["Aditya", "Gaurav"]

# Fake 3 Frames of Video Camera Data
frames = [
    {"frame": 1, "people": [{"id": 105, "face_visible": True, "real_identity": "Aditya"}, {"id": 106, "face_visible": False, "real_identity": "Stranger"}]},
    {"frame": 2, "people": [{"id": 105, "face_visible": False, "real_identity": "Aditya"}, {"id": 106, "face_visible": True, "real_identity": "Stranger"}]},
    {"frame": 3, "people": [{"id": 105, "face_visible": False, "real_identity": "Aditya"}, {"id": 106, "face_visible": False, "real_identity": "Stranger"}]},
]

for frame_data in frames:
    print(f">> PROCESSING FRAME {frame_data['frame']} ...")
    
    for person in frame_data["people"]:
        track_id = person["id"]
        
        # 1. Smart Caching Check
        if track_id in TRACKED_FACES:
            name = TRACKED_FACES[track_id]
            print(f"   [YOLO ID: {track_id}] CACHE HIT! Bypassing math. Auto-labeling body as: {name}")
        else:
            print(f"   [YOLO ID: {track_id}] NEW BODY DETECTED! Isolating frame for Face Recognition...")
            time.sleep(0.5) # Simulate heavy math
            
            if person["face_visible"]:
                if person["real_identity"] in known_faces_database:
                    name = person["real_identity"]
                    print(f"      -> Face Math Complete: Match found! Caching ID {track_id} as '{name}'")
                else:
                    name = "Unknown"
                    print(f"      -> Face Math Complete: No match. Caching ID {track_id} as 'Unknown'")
                TRACKED_FACES[track_id] = name
            else:
                name = "Unknown"
                print(f"      -> Face hidden (back turned). Cannot run math. Temporary label: 'Unknown'")
                
    print("-" * 50)
    time.sleep(1)

print("\n--- SIMULATION COMPLETE ---\n")
