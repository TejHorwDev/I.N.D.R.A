import cv2
import os
from pathlib import Path

def camera_vision(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Takes a photo using the default webcam and saves it for analysis.
    """
    action = parameters.get("action", "capture").lower()
    
    if action == "capture":
        try:
                                 
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                return "Failed to access the webcam. It might be in use or disabled."

            for _ in range(5):
                cap.read()
                
            ret, frame = cap.read()
            cap.release()
            
            if not ret:
                return "Failed to grab frame from the webcam."
                
            save_path = Path.home() / "Desktop" / "INDRA_webcam_capture.jpg"
            cv2.imwrite(str(save_path), frame)

                                                                                      
            return f"Webcam photo captured and saved to: {save_path}\nYou can now use your built-in image analysis tools on it!"
        except Exception as e:
            return f"Error during webcam capture: {e}"
    else:
        return f"Unknown camera action: {action}"
