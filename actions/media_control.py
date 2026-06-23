# pylint: disable=all
# pylint: disable=C0114, C0115, C0116, C0103, C0301, C0302, W0611, W0718, R0902, R0903, R0904, R0911, R0912, R0913, R0914, R0915, R0801
import pyautogui
from typing import Any

def media_control(parameters: dict[str, Any], ui_callback, dashboard_callback, send_log_callback, get_memory_callback) -> str:
    """Controls OS media player and volume."""
    action = parameters.get("action", "play_pause")
    
    try:
        if action == "play_pause":
            pyautogui.press("playpause")
            return "Toggled play/pause."
        elif action == "next_track":
            pyautogui.press("nexttrack")
            return "Skipped to next track."
        elif action == "previous_track":
            pyautogui.press("prevtrack")
            return "Went to previous track."
        elif action == "volume_up":
            pyautogui.press("volumeup", presses=5)
            return "Increased volume."
        elif action == "volume_down":
            pyautogui.press("volumedown", presses=5)
            return "Decreased volume."
        elif action == "mute":
            pyautogui.press("volumemute")
            return "Toggled mute."
            
        return f"Unknown media_control action: {action}"
    except Exception as e:
        return f"Failed to execute media control: {e}"
