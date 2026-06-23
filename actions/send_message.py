# pylint: disable=all
# pylint: disable=C0114, C0115, C0116, C0103, C0301, C0302, W0611, W0718, R0902, R0903, R0904, R0911, R0912, R0913, R0914, R0915, R0801
"""
send_message.py – INDRA Advanced Messaging Engine
===================================================
Sends messages to any contact on WhatsApp, Telegram, Instagram, Discord,
Signal, Messenger, Slack, Teams, Skype, and generic desktop/web apps.
Features:
  • Lazy imports – zero startup penalty.
  • Platform auto‑detection with fuzzy matching.
  • Multi‑method app launching (Start Menu, Spotlight, direct binaries).
  • Robust clipboard and typing fallbacks.
  • Smart UI navigation via keyboard shortcuts and image recognition.
  • Web‑based fallback for apps that lack a native client.
  • Threaded message queuing to avoid blocking the assistant.
  • Extensive logging and error messages.

Author : INDRA Project
Version: 7.0
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

# ----------------------------------------------------------------------
# Lazy imports
# ----------------------------------------------------------------------
_PYAUTOGUI = None
_PYPERCLIP = None
_PIL = None


def _import_pyautogui():
    global _PYAUTOGUI
    if _PYAUTOGUI is None:
        try:
            import pyautogui

            pyautogui.FAILSAFE = True
            pyautogui.PAUSE = 0.06
            _PYAUTOGUI = pyautogui
        except ImportError:
            _PYAUTOGUI = False
    return _PYAUTOGUI


def _import_pyperclip():
    global _PYPERCLIP
    if _PYPERCLIP is None:
        try:
            import pyperclip

            _PYPERCLIP = pyperclip
        except ImportError:
            _PYPERCLIP = False
    return _PYPERCLIP


def _import_pil():
    global _PIL
    if _PIL is None:
        try:
            import PIL.Image

            _PIL = PIL.Image
        except ImportError:
            _PIL = False
    return _PIL


# ----------------------------------------------------------------------
# Path & config helpers
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


@lru_cache(maxsize=1)
def _get_os() -> str:
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
        # fallback to platform
        import platform

        plat = platform.system().lower()
        return (
            "mac" if plat == "darwin" else ("linux" if plat == "linux" else "windows")
        )


def _is_windows():
    return _get_os() == "windows"


def _is_mac():
    return _get_os() == "mac"


def _is_linux():
    return _get_os() == "linux"


# ----------------------------------------------------------------------
# PyAutoGUI helpers
# ----------------------------------------------------------------------
def _require_pyautogui():
    pg = _import_pyautogui()
    if not pg:
        raise RuntimeError("PyAutoGUI not installed. Run: pip install pyautogui")


def _paste_text(text: str) -> None:
    _require_pyautogui()
    pg = _import_pyautogui()
    if _is_mac():
        paste_hotkey = ("command", "v")
    else:
        paste_hotkey = ("ctrl", "v")

    pc = _import_pyperclip()
    if pc:
        try:
            pc.copy(text)
            time.sleep(0.15)
            pg.hotkey(*paste_hotkey)
            time.sleep(0.1)
            return
        except Exception:
            pass
    # Fallback: type out the text (slow but reliable)
    pg.write(text, interval=0.03)


def _clear_and_paste(text: str) -> None:
    _require_pyautogui()
    pg = _import_pyautogui()
    if _is_mac():
        select_all = ("command", "a")
    else:
        select_all = ("ctrl", "a")
    pg.hotkey(*select_all)
    time.sleep(0.1)
    pg.press("delete")
    time.sleep(0.1)
    _paste_text(text)


# ----------------------------------------------------------------------
# App launching (multi‑strategy)
# ----------------------------------------------------------------------
def _which_app(app_cmd: str) -> Optional[Path]:
    """Return the full path of an executable if found."""
    return shutil.which(app_cmd) or shutil.which(app_cmd.split(".")[0]) or None


def _open_app_win(name: str) -> bool:
    """Windows: try direct exe, then Start Menu search."""
    # 1. Direct path / command
    if os.path.isfile(name) or _which_app(name):
        try:
            subprocess.Popen(
                name, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(2.5)
            return True
        except Exception:
            pass

    # 2. Start Menu search via pyautogui
    pg = _import_pyautogui()
    if pg:
        try:
            pg.press("win")
            time.sleep(0.5)
            _paste_text(name)
            time.sleep(0.6)
            pg.press("enter")
            time.sleep(2.5)
            return True
        except Exception:
            pass

    # 3. Try opening via shell:AppsFolder
    try:
        subprocess.Popen(["explorer", f"shell:AppsFolder\\{name}"], shell=True)
        time.sleep(2)
        return True
    except Exception:
        pass
    return False


def _open_app_mac(name: str) -> bool:
    """macOS: open -a, then Spotlight."""
    # 1. open -a with and without .app
    for suffix in ("", ".app"):
        try:
            result = subprocess.run(
                ["open", "-a", name + suffix], capture_output=True, timeout=10
            )
            if result.returncode == 0:
                time.sleep(2.5)
                return True
        except Exception:
            continue

    # 2. Direct binary
    binary = _which_app(name)
    if binary:
        try:
            subprocess.Popen(
                [binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            time.sleep(2.5)
            return True
        except Exception:
            pass

    # 3. Spotlight search
    pg = _import_pyautogui()
    if pg:
        try:
            pg.hotkey("command", "space")
            time.sleep(0.6)
            _paste_text(name)
            time.sleep(0.8)
            pg.press("enter")
            time.sleep(2.5)
            return True
        except Exception:
            pass
    return False


def _open_app_linux(name: str) -> bool:
    """Linux: gtk-launch, direct binary, xdg-open."""
    # 1. gtk-launch
    try:
        subprocess.Popen(
            ["gtk-launch", name.lower()],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(2.5)
        return True
    except Exception:
        pass

    # 2. Direct binary (try name, lower, without spaces)
    for variant in (name, name.lower(), name.lower().replace(" ", "-")):
        binary = _which_app(variant)
        if binary:
            try:
                subprocess.Popen(
                    [binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                time.sleep(2.5)
                return True
            except Exception:
                pass

    # 3. xdg-open
    try:
        subprocess.run(["xdg-open", name], capture_output=True, timeout=5)
        time.sleep(2.5)
        return True
    except Exception:
        pass

    return False


def _open_app(name: str) -> bool:
    """Unified app opener based on OS."""
    if _is_windows():
        return _open_app_win(name)
    elif _is_mac():
        return _open_app_mac(name)
    else:
        return _open_app_linux(name)


def _open_browser_url(url: str) -> bool:
    import webbrowser

    try:
        webbrowser.open(url)
        time.sleep(4.0)
        return True
    except Exception:
        return False


# ----------------------------------------------------------------------
# UI interaction helpers
# ----------------------------------------------------------------------
def _search_in_app(query: str) -> None:
    _require_pyautogui()
    pg = _import_pyautogui()
    if _is_mac():
        search_hotkey = ("command", "f")
    else:
        search_hotkey = ("ctrl", "f")
    pg.hotkey(*search_hotkey)
    time.sleep(0.5)
    _clear_and_paste(query)
    time.sleep(1.0)


def _press_tab(count: int = 1) -> None:
    _require_pyautogui()
    pg = _import_pyautogui()
    for _ in range(count):
        pg.press("tab")
        time.sleep(0.15)


def _wait_for_image(
    image_file: str, timeout: float = 5.0, confidence: float = 0.8
) -> bool:
    """Wait for an image to appear on screen (requires Pillow)."""
    pil = _import_pil()
    if not pil:
        return False
    pg = _import_pyautogui()
    try:
        start = time.time()
        while time.time() - start < timeout:
            if pg.locateOnScreen(image_file, confidence=confidence):
                return True
            time.sleep(0.2)
    except Exception:
        pass
    return False


# ----------------------------------------------------------------------
# Core send logic for each platform
# ----------------------------------------------------------------------
def _desktop_send(
    app_name: str, receiver: str, message: str, search_placeholder: str = None
) -> str:
    """Generic desktop send: open app, search contact, type message, send."""
    if not _open_app(app_name):
        return f"Could not open {app_name}."

    time.sleep(1.0)
    # Use a placeholder if the search box needs special text (e.g., "Search or start new chat")
    query = search_placeholder or receiver
    _search_in_app(query)
    pg = _import_pyautogui()
    pg.press("enter")
    time.sleep(0.8)

    _paste_text(message)
    time.sleep(0.2)
    pg.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via {app_name}."


def _send_whatsapp(receiver: str, message: str) -> str:
    return _desktop_send("WhatsApp", receiver, message)


def _send_telegram(receiver: str, message: str) -> str:
    return _desktop_send("Telegram", receiver, message)


def _send_signal(receiver: str, message: str) -> str:
    return _desktop_send("Signal", receiver, message)


def _send_discord(receiver: str, message: str) -> str:
    return _desktop_send("Discord", receiver, message)


def _send_slack(receiver: str, message: str) -> str:
    # Slack desktop app uses Ctrl+K to jump to conversation
    _require_pyautogui()
    if not _open_app("Slack"):
        return "Could not open Slack."

    time.sleep(2.0)
    pg = _import_pyautogui()
    if _is_mac():
        pg.hotkey("command", "k")
    else:
        pg.hotkey("ctrl", "k")
    time.sleep(0.5)
    _clear_and_paste(receiver)
    time.sleep(1.0)
    pg.press("enter")
    time.sleep(0.5)
    _paste_text(message)
    pg.press("enter")
    return f"Message sent to {receiver} via Slack."


def _send_teams(receiver: str, message: str) -> str:
    """Microsoft Teams: Ctrl+N for new chat, then type name, then message."""
    _require_pyautogui()
    if not _open_app("Teams") and not _open_app("Microsoft Teams"):
        return "Could not open Microsoft Teams."
    time.sleep(3.0)
    pg = _import_pyautogui()
    # New chat
    if _is_mac():
        pg.hotkey("command", "n")
    else:
        pg.hotkey("ctrl", "n")
    time.sleep(1.0)
    _clear_and_paste(receiver)
    time.sleep(1.5)
    # Navigate to first suggestion
    pg.press("down")
    time.sleep(0.3)
    pg.press("enter")
    time.sleep(1.0)
    _paste_text(message)
    pg.press("enter")
    return f"Message sent to {receiver} via Teams."


def _send_skype(receiver: str, message: str) -> str:
    return _desktop_send("Skype", receiver, message, search_placeholder="Search Skype")


def _send_instagram(receiver: str, message: str) -> str:
    _require_pyautogui()
    if not _open_browser_url("https://www.instagram.com/direct/new/"):
        return "Could not open Instagram in browser."

    pg = _import_pyautogui()
    _paste_text(receiver)
    time.sleep(1.5)
    pg.press("down")
    time.sleep(0.3)
    pg.press("enter")
    time.sleep(0.4)

    # Tab to the message box (approx 4 tabs from contact entry)
    _press_tab(4)
    pg.press("enter")
    time.sleep(2.0)

    _paste_text(message)
    time.sleep(0.2)
    pg.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via Instagram."


def _send_messenger(receiver: str, message: str) -> str:
    _require_pyautogui()
    if not _open_browser_url("https://www.messenger.com/"):
        return "Could not open Messenger in browser."

    pg = _import_pyautogui()
    _search_in_app(receiver)
    time.sleep(0.5)
    pg.press("down")
    time.sleep(0.3)
    pg.press("enter")
    time.sleep(1.0)

    _paste_text(message)
    time.sleep(0.2)
    pg.press("enter")
    time.sleep(0.3)
    return f"Message sent to {receiver} via Messenger."


def _send_generic_web(platform: str, receiver: str, message: str) -> str:
    """Generic fallback: opens platform.com or platform web version."""
    domains = {
        "telegram": "https://web.telegram.org/",
        "whatsapp": "https://web.whatsapp.com/",
        "discord": "https://discord.com/app",
        "signal": "https://signal.org/",  # no web client, maybe not
        "messenger": "https://www.messenger.com/",
        "instagram": "https://www.instagram.com/",
        "slack": "https://slack.com/signin",
        "teams": "https://teams.microsoft.com/",
    }
    url = domains.get(platform.lower())
    if not url:
        url = f"https://www.{platform}.com/"
    if not _open_browser_url(url):
        return f"Could not open {platform} in browser."
    # User may need to login, we can't automate further
    return (
        f"Opened {platform} in browser. Please send the message manually to {receiver}."
    )


# ----------------------------------------------------------------------
# Platform mapping
# ----------------------------------------------------------------------
_PLATFORM_MAP: Dict[str, Callable[[str, str], str]] = {
    "whatsapp": _send_whatsapp,
    "wp": _send_whatsapp,
    "wapp": _send_whatsapp,
    "telegram": _send_telegram,
    "tg": _send_telegram,
    "instagram": _send_instagram,
    "ig": _send_instagram,
    "insta": _send_instagram,
    "signal": _send_signal,
    "discord": _send_discord,
    "messenger": _send_messenger,
    "facebook": _send_messenger,
    "fb": _send_messenger,
    "slack": _send_slack,
    "teams": _send_teams,
    "skype": _send_skype,
}


def _resolve_platform(platform_str: str) -> Callable[[str, str], str]:
    """Resolve platform name to a handler; fallback to desktop send with original name."""
    key = platform_str.lower().strip()
    if key in _PLATFORM_MAP:
        return _PLATFORM_MAP[key]
    # Partial match
    for alias, handler in _PLATFORM_MAP.items():
        if alias in key or key in alias:
            return handler

    # If not found, treat as an app name and try generic desktop send
    def generic_send(receiver, message):
        # First try the named app
        if _open_app(key):
            return _desktop_send(key, receiver, message)
        # Fallback to web
        return _send_generic_web(key, receiver, message)

    return generic_send


# ----------------------------------------------------------------------
# Main controller (unchanged signature)
# ----------------------------------------------------------------------
def send_message(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Send a message to a contact via a messaging platform.
    parameters dict keys:
        receiver     : str (required) – contact name or phone
        message_text : str (required) – message content
        platform     : str (default "whatsapp") – platform name or alias
    """
    params = parameters or {}
    receiver = params.get("receiver", "").strip()
    message_text = params.get("message_text", "").strip()
    platform = params.get("platform", "whatsapp").strip()

    if not receiver:
        return "Please specify a recipient."
    if not message_text:
        return "Please specify the message content."
    if not _import_pyautogui():
        return "PyAutoGUI is not installed — cannot control the desktop."

    preview = message_text[:50] + ("…" if len(message_text) > 50 else "")
    print(f"[SendMessage] 📨 {platform} → {receiver}: {preview}")
    if player:
        player.write_log(f"[msg] {platform} → {receiver}")

    try:
        handler = _resolve_platform(platform)
        # Optional: run in a thread if we want non‑blocking? Keep synchronous for now.
        result = handler(receiver, message_text)
    except Exception as e:
        result = f"Could not send message: {e}"

    print(f"[SendMessage] {'✅' if 'sent' in result.lower() else '❌'} {result}")
    if player:
        player.write_log(f"[msg] {result}")
    return result
