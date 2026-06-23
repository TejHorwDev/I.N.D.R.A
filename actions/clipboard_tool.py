import pyperclip

def clipboard_tool(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """
    Reads from or writes to the system clipboard.
    """
    action = parameters.get("action", "read").lower()
    text = parameters.get("text", "")

    if action == "read":
        try:
            content = pyperclip.paste()
            if not content:
                return "Clipboard is currently empty."
            return f"Clipboard contents:\n{content}"
        except Exception as e:
            return f"Failed to read clipboard: {e}"
    elif action == "write":
        if not text:
            return "No text provided to write to clipboard."
        try:
            pyperclip.copy(text)
            return "Successfully copied text to clipboard."
        except Exception as e:
            return f"Failed to write to clipboard: {e}"
    else:
        return f"Unknown clipboard action: {action}"
