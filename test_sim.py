import sys
from unittest.mock import MagicMock, patch

# Mock all Raspberry Pi and ML libraries so we can import main.py on Windows
sys.modules['RPi'] = MagicMock()
sys.modules['RPi.GPIO'] = MagicMock()
sys.modules['face_recognition'] = MagicMock()
sys.modules['ultralytics'] = MagicMock()
sys.modules['cv2'] = MagicMock()

import main

# Fill with fake data
main.TELEGRAM_BOT_TOKEN = "TEST_TOKEN"
main.TELEGRAM_CHAT_ID = "TEST_ID"
main.REPORT_STATS["motion_events"] = 42
main.REPORT_STATS["auth_entries"] = 8
main.REPORT_STATS["intruders"] = 1

def run_simulation():
    print("--- STARTING TIMER SIMULATION ---\n")
    
    with patch('main.time.sleep') as mock_sleep, patch('main.requests.post') as mock_post:
        
        # Define what happens when the code calls time.sleep()
        def sleep_behavior(seconds):
            if seconds == 3 * 3600:
                print(f"[TIMER] Code successfully waited {int(seconds/3600)} Hours.")
                print(f"[ACTION] Sending DEMO Telegram Report!\n")
            elif seconds == 24 * 3600:
                print(f"[TIMER] Code successfully waited {int(seconds/3600)} Hours.")
                print(f"[ACTION] Sending DAILY Telegram Report!\n")
                
                # Stop the infinite while True loop after two days for this simulation
                if mock_sleep.call_count >= 3:
                    print("[STOP] Stopping simulation (verified 3-hour demo and two 24-hour loops).")
                    raise KeyboardInterrupt
        
        mock_sleep.side_effect = sleep_behavior
        
        # Intercept the Telegram API call to read what it's trying to send
        def post_behavior(url, data=None, files=None):
            if data and 'text' in data:
                print("[TELEGRAM API INTERCEPTED MESSAGE]:")
                print(data['text'])
                print("-" * 40 + "\n")
        
        mock_post.side_effect = post_behavior

        # Start the worker!
        try:
            main.report_worker()
        except KeyboardInterrupt:
            pass

run_simulation()
