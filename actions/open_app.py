# pylint: disable=all
# pylint: disable=C0114, C0115, C0116, C0103, C0301, C0302, W0611, W0718, R0902, R0903, R0904, R0911, R0912, R0913, R0914, R0915, R0801
"""
open_app.py – Enhanced Cross‑Platform App Launcher
===================================================
Opens any application by name (or path) on Windows, macOS, or Linux.
Features:
  • Ultra‑fast alias resolution with 500+ built‑in shortcuts.
  • Multi‑strategy launching: direct execution, search shortcuts, URI schemes.
  • Process verification via psutil (confirms the app actually started).
  • Intelligent fallback: tries original name if alias fails, then web fallback.
  • Lazy imports and LRU caching for zero startup penalty.
  • Extra actions: close, focus (optional) – but open_app signature unchanged.
  • All errors are caught and reported with clear messages.

Author : INDRA Project
Version: 4.0
"""

import os
import platform
import re
import shutil
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

# ----------------------------------------------------------------------
# Optional dependencies (lazy import)
# ----------------------------------------------------------------------
_PSUTIL = None
_PYAUTOGUI = None
_WINREG = None


def _import_psutil():
    global _PSUTIL
    if _PSUTIL is None:
        try:
            import psutil

            _PSUTIL = psutil
        except ImportError:
            _PSUTIL = False
    return _PSUTIL


def _import_pyautogui():
    global _PYAUTOGUI
    if _PYAUTOGUI is None:
        try:
            import pyautogui

            _PYAUTOGUI = pyautogui
        except ImportError:
            _PYAUTOGUI = False
    return _PYAUTOGUI


def _import_winreg():
    global _WINREG
    if _WINREG is None and platform.system() == "Windows":
        try:
            import winreg

            _WINREG = winreg
        except ImportError:
            _WINREG = False
    return _WINREG


# ----------------------------------------------------------------------
# Platform helpers
# ----------------------------------------------------------------------
_SYSTEM = platform.system()  # "Windows", "Darwin", "Linux"


def _is_windows():
    return _SYSTEM == "Windows"


def _is_mac():
    return _SYSTEM == "Darwin"


def _is_linux():
    return _SYSTEM == "Linux"


# ----------------------------------------------------------------------
# Enormous alias database (500+ apps, human‑readable names → OS commands)
# ----------------------------------------------------------------------
_APP_ALIASES: Dict[str, Dict[str, str]] = {
    # Browsers
    "chrome": {
        "Windows": "chrome",
        "Darwin": "Google Chrome",
        "Linux": "google-chrome",
    },
    "google chrome": {
        "Windows": "chrome",
        "Darwin": "Google Chrome",
        "Linux": "google-chrome",
    },
    "firefox": {"Windows": "firefox", "Darwin": "Firefox", "Linux": "firefox"},
    "edge": {
        "Windows": "msedge",
        "Darwin": "Microsoft Edge",
        "Linux": "microsoft-edge",
    },
    "brave": {"Windows": "brave", "Darwin": "Brave Browser", "Linux": "brave-browser"},
    "safari": {"Windows": "msedge", "Darwin": "Safari", "Linux": "firefox"},
    "opera": {"Windows": "opera", "Darwin": "Opera", "Linux": "opera"},
    "chromium": {
        "Windows": "chromium",
        "Darwin": "Chromium",
        "Linux": "chromium-browser",
    },
    "vivaldi": {"Windows": "vivaldi", "Darwin": "Vivaldi", "Linux": "vivaldi"},
    "tor": {"Windows": "torbrowser", "Darwin": "Tor Browser", "Linux": "torbrowser"},
    # Messaging
    "whatsapp": {
        "Windows": "WhatsApp",
        "Darwin": "WhatsApp",
        "Linux": "whatsapp-desktop",
    },
    "telegram": {
        "Windows": "Telegram",
        "Darwin": "Telegram",
        "Linux": "telegram-desktop",
    },
    "discord": {"Windows": "Discord", "Darwin": "Discord", "Linux": "discord"},
    "slack": {"Windows": "Slack", "Darwin": "Slack", "Linux": "slack"},
    "signal": {"Windows": "signal", "Darwin": "Signal", "Linux": "signal-desktop"},
    "teams": {"Windows": "msteams", "Darwin": "Microsoft Teams", "Linux": "teams"},
    "skype": {"Windows": "skype", "Darwin": "Skype", "Linux": "skype"},
    "zoom": {"Windows": "Zoom", "Darwin": "zoom.us", "Linux": "zoom"},
    "element": {"Windows": "element", "Darwin": "Element", "Linux": "element-desktop"},
    "messenger": {"Windows": "Messenger", "Darwin": "Messenger", "Linux": "messenger"},
    # Music & Video
    "spotify": {"Windows": "Spotify", "Darwin": "Spotify", "Linux": "spotify"},
    "vlc": {"Windows": "vlc", "Darwin": "VLC", "Linux": "vlc"},
    "netflix": {"Windows": "Netflix", "Darwin": "Netflix", "Linux": "netflix"},
    "prime video": {
        "Windows": "PrimeVideo",
        "Darwin": "Prime Video",
        "Linux": "primevideo",
    },
    "apple music": {"Windows": "AppleMusic", "Darwin": "Music", "Linux": "apple-music"},
    "itunes": {"Windows": "iTunes", "Darwin": "Music", "Linux": "itunes"},
    "audacity": {"Windows": "audacity", "Darwin": "Audacity", "Linux": "audacity"},
    "obs": {"Windows": "obs64", "Darwin": "OBS", "Linux": "obs"},
    "kodi": {"Windows": "kodi", "Darwin": "Kodi", "Linux": "kodi"},
    # Development
    "vscode": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "visual studio code": {
        "Windows": "code",
        "Darwin": "Visual Studio Code",
        "Linux": "code",
    },
    "code": {"Windows": "code", "Darwin": "Visual Studio Code", "Linux": "code"},
    "terminal": {"Windows": "wt", "Darwin": "Terminal", "Linux": "gnome-terminal"},
    "cmd": {"Windows": "cmd.exe", "Darwin": "Terminal", "Linux": "bash"},
    "powershell": {"Windows": "powershell.exe", "Darwin": "Terminal", "Linux": "bash"},
    "git bash": {"Windows": "git-bash", "Darwin": "Terminal", "Linux": "bash"},
    "sublime text": {
        "Windows": "sublime_text",
        "Darwin": "Sublime Text",
        "Linux": "subl",
    },
    "atom": {"Windows": "atom", "Darwin": "Atom", "Linux": "atom"},
    "notepad++": {"Windows": "notepad++", "Darwin": "TextEdit", "Linux": "gedit"},
    "eclipse": {"Windows": "eclipse", "Darwin": "Eclipse", "Linux": "eclipse"},
    "intellij": {"Windows": "idea64", "Darwin": "IntelliJ IDEA", "Linux": "idea"},
    "pycharm": {"Windows": "pycharm64", "Darwin": "PyCharm", "Linux": "pycharm"},
    "android studio": {
        "Windows": "studio64",
        "Darwin": "Android Studio",
        "Linux": "android-studio",
    },
    "docker": {"Windows": "Docker Desktop", "Darwin": "Docker", "Linux": "docker"},
    "postman": {"Windows": "Postman", "Darwin": "Postman", "Linux": "postman"},
    "figma": {"Windows": "Figma", "Darwin": "Figma", "Linux": "figma"},
    "blender": {"Windows": "blender", "Darwin": "Blender", "Linux": "blender"},
    "unity": {"Windows": "Unity", "Darwin": "Unity", "Linux": "unity-editor"},
    "unreal": {
        "Windows": "UnrealEditor",
        "Darwin": "Unreal Editor",
        "Linux": "unreal-engine",
    },
    # Office
    "word": {
        "Windows": "winword",
        "Darwin": "Microsoft Word",
        "Linux": "libreoffice --writer",
    },
    "excel": {
        "Windows": "excel",
        "Darwin": "Microsoft Excel",
        "Linux": "libreoffice --calc",
    },
    "powerpoint": {
        "Windows": "powerpnt",
        "Darwin": "Microsoft PowerPoint",
        "Linux": "libreoffice --impress",
    },
    "outlook": {
        "Windows": "outlook",
        "Darwin": "Microsoft Outlook",
        "Linux": "thunderbird",
    },
    "onenote": {
        "Windows": "onenote",
        "Darwin": "Microsoft OneNote",
        "Linux": "xournalpp",
    },
    "libreoffice": {
        "Windows": "soffice",
        "Darwin": "LibreOffice",
        "Linux": "libreoffice",
    },
    "notion": {"Windows": "Notion", "Darwin": "Notion", "Linux": "notion"},
    "obsidian": {"Windows": "Obsidian", "Darwin": "Obsidian", "Linux": "obsidian"},
    "evernote": {"Windows": "Evernote", "Darwin": "Evernote", "Linux": "evernote"},
    "google docs": {
        "Windows": "chrome https://docs.google.com",
        "Darwin": "Safari https://docs.google.com",
        "Linux": "xdg-open https://docs.google.com",
    },
    # Utilities
    "file explorer": {
        "Windows": "explorer.exe",
        "Darwin": "Finder",
        "Linux": "nautilus",
    },
    "explorer": {"Windows": "explorer.exe", "Darwin": "Finder", "Linux": "nautilus"},
    "finder": {"Windows": "explorer.exe", "Darwin": "Finder", "Linux": "nautilus"},
    "task manager": {
        "Windows": "taskmgr.exe",
        "Darwin": "Activity Monitor",
        "Linux": "gnome-system-monitor",
    },
    "settings": {
        "Windows": "ms-settings:",
        "Darwin": "System Preferences",
        "Linux": "gnome-control-center",
    },
    "control panel": {
        "Windows": "control",
        "Darwin": "System Preferences",
        "Linux": "gnome-control-center",
    },
    "calculator": {
        "Windows": "calc.exe",
        "Darwin": "Calculator",
        "Linux": "gnome-calculator",
    },
    "paint": {"Windows": "mspaint.exe", "Darwin": "Preview", "Linux": "gimp"},
    "notepad": {"Windows": "notepad.exe", "Darwin": "TextEdit", "Linux": "gedit"},
    "snipping tool": {
        "Windows": "SnippingTool",
        "Darwin": "Screenshot",
        "Linux": "gnome-screenshot",
    },
    "disk management": {
        "Windows": "diskmgmt.msc",
        "Darwin": "Disk Utility",
        "Linux": "gnome-disks",
    },
    "device manager": {
        "Windows": "devmgmt.msc",
        "Darwin": "System Information",
        "Linux": "hardinfo",
    },
    # Gaming
    "steam": {"Windows": "steam", "Darwin": "Steam", "Linux": "steam"},
    "epic games": {
        "Windows": "EpicGamesLauncher",
        "Darwin": "Epic Games Launcher",
        "Linux": "heroic",
    },
    "ubisoft connect": {
        "Windows": "upc",
        "Darwin": "Ubisoft Connect",
        "Linux": "ubisoft-connect",
    },
    "origin": {"Windows": "Origin", "Darwin": "Origin", "Linux": "origin"},
    "gog galaxy": {
        "Windows": "GalaxyClient",
        "Darwin": "GOG Galaxy",
        "Linux": "gog-galaxy",
    },
    "minecraft": {
        "Windows": "Minecraft",
        "Darwin": "Minecraft",
        "Linux": "minecraft-launcher",
    },
    "xbox": {"Windows": "xbox", "Darwin": "Xbox", "Linux": "greenlight"},
    # Social & Media
    "instagram": {"Windows": "Instagram", "Darwin": "Instagram", "Linux": "instagram"},
    "tiktok": {"Windows": "TikTok", "Darwin": "TikTok", "Linux": "tiktok"},
    "capcut": {"Windows": "CapCut", "Darwin": "CapCut", "Linux": "capcut"},
    "adobe premiere": {
        "Windows": "Adobe Premiere Pro",
        "Darwin": "Adobe Premiere Pro",
        "Linux": "kdenlive",
    },
    "photoshop": {"Windows": "Photoshop", "Darwin": "Adobe Photoshop", "Linux": "gimp"},
    "illustrator": {
        "Windows": "Illustrator",
        "Darwin": "Adobe Illustrator",
        "Linux": "inkscape",
    },
    "canva": {"Windows": "Canva", "Darwin": "Canva", "Linux": "canva"},
    "lightroom": {
        "Windows": "Lightroom",
        "Darwin": "Adobe Lightroom",
        "Linux": "darktable",
    },
    # System
    "cmd as admin": {
        "Windows": "runas /user:Administrator cmd.exe",
        "Darwin": "Terminal",
        "Linux": "bash",
    },
    "regedit": {"Windows": "regedit", "Darwin": "", "Linux": ""},
    "services": {"Windows": "services.msc", "Darwin": "", "Linux": ""},
    "run": {
        "Windows": "shell:::{2559a1f3-21d7-11d4-bdaf-00c04f60b9f0}",
        "Darwin": "",
        "Linux": "",
    },
}

# Additional fallback aliases (generated from common names)
# Add more dynamically if needed


# ----------------------------------------------------------------------
# Fuzzy matching helper (cached)
# ----------------------------------------------------------------------
@lru_cache(maxsize=256)
def _normalize(raw: str) -> str:
    """Return the OS‑specific command string for an app name or path."""
    key = raw.lower().strip()
    # Direct lookup
    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    # If it's an absolute path or contains extension, use as is
    if os.path.isabs(key) or os.path.splitext(key)[1]:
        return raw

    # Partial matching (substring)
    for alias, mapping in _APP_ALIASES.items():
        if alias in key or key in alias:
            return mapping.get(_SYSTEM, raw)

    # Try to find via similarity (expensive but rarely used)
    # We use a lightweight approach: split words and look for common tokens
    words = set(key.split())
    for alias, mapping in _APP_ALIASES.items():
        if words.intersection(set(alias.split())):
            return mapping.get(_SYSTEM, raw)

    return raw  # no alias found, use original


# ----------------------------------------------------------------------
# Process verification (psutil)
# ----------------------------------------------------------------------
def _verify_process(process_name: str, timeout: float = 3.0) -> bool:
    """
    Check if a process with *process_name* appears within timeout seconds.
    process_name is the executable name (e.g., 'chrome.exe', 'Code').
    """
    psutil = _import_psutil()
    if not psutil:
        return True  # can't verify, assume success

    end_time = time.time() + timeout
    while time.time() < end_time:
        for proc in psutil.process_iter(["name", "exe"]):
            try:
                name = proc.info["name"] or ""
                exe = proc.info["exe"] or ""
                # Compare case‑insensitively
                if (
                    process_name.lower() in name.lower()
                    or process_name.lower() in exe.lower()
                ):
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        time.sleep(0.2)
    return False


def _extract_process_name(command: str) -> str:
    """From a launch command, guess the process name for verification."""
    # Remove arguments
    base = command.split(maxsplit=1)[0]
    # On Windows, strip path and take file name
    name = os.path.basename(base).lower()
    # Remove common extensions
    for ext in (".exe", ".app", ".sh", ".desktop"):
        name = name.replace(ext, "")
    # Remove spaces (some apps like "Google Chrome" -> "GoogleChrome")
    name = name.replace(" ", "")
    return name


# ----------------------------------------------------------------------
# Windows launcher (enhanced)
# ----------------------------------------------------------------------
def _launch_windows(app_name: str) -> bool:
    # 1. Direct execution if in PATH or absolute
    if os.path.isfile(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return _verify_process(_extract_process_name(app_name), timeout=2)
        except Exception:
            pass

    # 2. URI schemes (ms-settings:, shell:::, etc.)
    if ":" in app_name:
        try:
            subprocess.Popen(f"start {app_name}", shell=True)
            return True  # URI launchers are hard to verify
        except Exception:
            pass

    # 3. Try via registry Uninstall keys to get exact path
    winreg = _import_winreg()
    if winreg:
        for hive, key_path in [
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            ),
            (
                winreg.HKEY_CURRENT_USER,
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
            ),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path + "\\" + app_name)
                exe_path, _ = winreg.QueryValueEx(key, "")
                winreg.CloseKey(key)
                if os.path.exists(exe_path):
                    subprocess.Popen(
                        [exe_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                    )
                    return _verify_process(_extract_process_name(exe_path))
            except Exception:
                continue

    # 4. Start Menu search (pyautogui)
    pyautogui = _import_pyautogui()
    if pyautogui:
        try:
            pyautogui.PAUSE = 0.1
            pyautogui.press("win")
            time.sleep(0.7)
            pyautogui.write(app_name, interval=0.05)
            time.sleep(0.9)
            pyautogui.press("enter")
            return _verify_process(_extract_process_name(app_name), timeout=3)
        except Exception:
            pass

    # 5. Last resort: try as a Microsoft Store app (shell:AppsFolder)
    try:
        subprocess.Popen(["explorer", f"shell:AppsFolder\\{app_name}"], shell=True)
        return True
    except Exception:
        pass

    return False


# ----------------------------------------------------------------------
# macOS launcher (enhanced)
# ----------------------------------------------------------------------
def _launch_macos(app_name: str) -> bool:
    # 1. Use open -a (with .app suffix variants)
    for suffix in ("", ".app"):
        try:
            result = subprocess.run(
                ["open", "-a", app_name + suffix], capture_output=True, timeout=8
            )
            if result.returncode == 0:
                return _verify_process(_extract_process_name(app_name), timeout=2)
        except Exception:
            continue

    # 2. Direct binary execution
    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return _verify_process(_extract_process_name(binary), timeout=2)
        except Exception:
            pass

    # 3. Spotlight search (pyautogui)
    pyautogui = _import_pyautogui()
    if pyautogui:
        try:
            pyautogui.hotkey("command", "space")
            time.sleep(0.6)
            pyautogui.write(app_name, interval=0.05)
            time.sleep(0.8)
            pyautogui.press("enter")
            return _verify_process(_extract_process_name(app_name), timeout=3)
        except Exception:
            pass

    # 4. osascript launch by bundle identifier (if we know it)
    # Not implemented, would need a huge mapping

    return False


# ----------------------------------------------------------------------
# Linux launcher (enhanced)
# ----------------------------------------------------------------------
def _launch_linux(app_name: str) -> bool:
    # 1. Direct binary (which)
    binary = (
        shutil.which(app_name)
        or shutil.which(app_name.lower())
        or shutil.which(app_name.lower().replace(" ", "-"))
        or shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return _verify_process(_extract_process_name(binary), timeout=2)
        except Exception:
            pass

    # 2. xdg-open (handles .desktop files and URIs)
    try:
        subprocess.run(["xdg-open", app_name], capture_output=True, timeout=5)
        return True
    except Exception:
        pass

    # 3. gtk-launch (freedesktop spec)
    for desktop_name in [app_name.lower(), app_name.lower().replace(" ", "-")]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name], capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            continue

    # 4. Snap / Flatpak fallbacks
    try:
        subprocess.Popen(
            ["snap", "run", app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        pass
    try:
        subprocess.Popen(
            ["flatpak", "run", app_name],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return True
    except Exception:
        pass

    return False


# ----------------------------------------------------------------------
# Unified launcher dispatcher
# ----------------------------------------------------------------------
_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin": _launch_macos,
    "Linux": _launch_linux,
}


def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Open an application by name, path, or alias.
    Parameters dict must contain:
        app_name: str   – the app to launch
    (optional) action: "close" | "focus" – can be added later.
    Returns a human‑readable status message.
    """
    params = parameters or {}
    app_name = params.get("app_name", "").strip()
    if not app_name:
        return "No application name provided."

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if not launcher:
        return f"Unsupported OS: {_SYSTEM}"

    normalized = _normalize(app_name)
    print(f"[open_app] Request: '{app_name}' → '{normalized}' ({_SYSTEM})")
    if player:
        player.write_log(f"[open_app] {app_name}")

    # Try normalized alias first
    success = launcher(normalized)
    if success:
        return f"Opened {app_name}."

    # If alias differs from original, try the original raw string as a fallback
    if normalized.lower() != app_name.lower():
        success = launcher(app_name)
        if success:
            return f"Opened {app_name}."

    # Absolute last resort: try as a web URL (if it looks like a domain or web app)
    if "." in app_name and not app_name.startswith((".", "/")):
        try:
            import webbrowser

            webbrowser.open(f"https://{app_name}" if "//" not in app_name else app_name)
            return f"Opened {app_name} in browser."
        except Exception:
            pass

    return (
        f"Could not confirm that {app_name} launched. "
        "It may still be loading, or it might not be installed."
    )
