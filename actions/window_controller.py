import pygetwindow as gw

def window_controller(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Manages active application windows on the desktop.
    """
    action = parameters.get("action", "list").lower()
    title = parameters.get("title", "")

    if action == "list":
        windows = gw.getAllTitles()
        active = [w for w in windows if w.strip()]
        if not active:
            return "No active named windows found."
        return "Open windows:\n" + "\n".join(f"- {w}" for w in active)
        
    elif action == "focus":
        if not title:
            return "Must specify a window title to focus."
        windows = gw.getWindowsWithTitle(title)
        if not windows:
            return f"No window found matching '{title}'"
        
        win = windows[0]
        try:
            if win.isMinimized:
                win.restore()
            win.activate()
            return f"Focused window: {win.title}"
        except Exception as e:
            return f"Failed to focus window: {e}"
            
    elif action == "close":
        if not title:
            return "Must specify a window title to close."
        windows = gw.getWindowsWithTitle(title)
        if not windows:
            return f"No window found matching '{title}'"
            
        win = windows[0]
        try:
            win.close()
            return f"Closed window: {win.title}"
        except Exception as e:
            return f"Failed to close window: {e}"
            
    elif action == "minimize":
        if not title:
            return "Must specify a window title to minimize."
        windows = gw.getWindowsWithTitle(title)
        if not windows:
            return f"No window found matching '{title}'"
            
        win = windows[0]
        try:
            win.minimize()
            return f"Minimized window: {win.title}"
        except Exception as e:
            return f"Failed to minimize window: {e}"
            
    elif action == "minimize_all":
        try:
            windows = gw.getAllWindows()
            for w in windows:
                if w.title.strip():
                    w.minimize()
            return "Minimized all active windows."
        except Exception as e:
            return f"Failed to minimize all windows: {e}"
            
    else:
        return f"Unknown window action: {action}"
