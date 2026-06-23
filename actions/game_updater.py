# pylint: disable=all
# pylint: disable=C0114, C0115, C0116, C0103, C0301, C0302, W0611, W0718, R0902, R0903, R0904, R0911, R0912, R0913, R0914, R0915, R0801
# game_updater.py — Enhanced Multi‑Platform Game Updater
#
# Peak‑performance, robust, and accurate game management for Steam & Epic.
# All controller signatures remain 100% compatible with the original.
#
# Features:
#   • Smart caching of game data, paths, and API lookups for instant responses
#   • Parallel processing where safe, lazy imports to avoid startup delays
#   • Accurate app ID resolution via local library, online API, and fuzzy matching
#   • Resilient dialog automation for installation drive selection
#   • Threaded shutdown monitor with dead‑man switch
#   • Cross‑platform scheduling (Task Scheduler, launchd, cron)
#   • Comprehensive error handling and detailed feedback

import json
import os
import re
import shutil
import string
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

# Optional imports (lazy, with fallbacks)
_PYGETWINDOW = None
_PYAUTOGUI = None
_PYWINAUTO = None
_NUMPY = None
_DIFFLIB = None


def _lazy_pygetwindow():
    global _PYGETWINDOW
    if _PYGETWINDOW is None:
        try:
            import pygetwindow as gw

            _PYGETWINDOW = gw
        except ImportError:
            _PYGETWINDOW = False
    return _PYGETWINDOW


def _lazy_pyautogui():
    global _PYAUTOGUI
    if _PYAUTOGUI is None:
        try:
            import pyautogui

            _PYAUTOGUI = pyautogui
        except ImportError:
            _PYAUTOGUI = False
    return _PYAUTOGUI


def _lazy_pywinauto():
    global _PYWINAUTO
    if _PYWINAUTO is None:
        try:
            from pywinauto import Application, findwindows

            _PYWINAUTO = (Application, findwindows)
        except ImportError:
            _PYWINAUTO = False
    return _PYWINAUTO


def _lazy_numpy():
    global _NUMPY
    if _NUMPY is None:
        try:
            import numpy as np

            _NUMPY = np
        except ImportError:
            _NUMPY = False
    return _NUMPY


def _lazy_difflib():
    global _DIFFLIB
    if _DIFFLIB is None:
        try:
            import difflib

            _DIFFLIB = difflib
        except ImportError:
            _DIFFLIB = False
    return _DIFFLIB


# --------------------------------------------------------------------
# Platform detection (simple helpers, no external config needed)
# --------------------------------------------------------------------
def _is_windows():
    return sys.platform.startswith("win")


def _is_mac():
    return sys.platform.startswith("darwin")


def _is_linux():
    return sys.platform.startswith("linux")


# --------------------------------------------------------------------
# API key loading (cached)
# --------------------------------------------------------------------
@lru_cache(maxsize=1)
def _get_api_key() -> str:
    config_path = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return json.load(f)["gemini_api_key"]
    except Exception as e:
        raise RuntimeError(f"Gemini API key not found in {config_path}: {e}")


# --------------------------------------------------------------------
# Known App IDs (extended, ordered by popularity for quick lookup)
# --------------------------------------------------------------------
_KNOWN_APPIDS: Dict[str, Tuple[str, str]] = {
    # (lowercase key → (appid, canonical name))
    "pubg": ("578080", "PUBG: BATTLEGROUNDS"),
    "pubg battlegrounds": ("578080", "PUBG: BATTLEGROUNDS"),
    "battlegrounds": ("578080", "PUBG: BATTLEGROUNDS"),
    "gta5": ("271590", "Grand Theft Auto V"),
    "gta v": ("271590", "Grand Theft Auto V"),
    "grand theft auto v": ("271590", "Grand Theft Auto V"),
    "cs2": ("730", "Counter-Strike 2"),
    "csgo": ("730", "Counter-Strike 2"),
    "counter-strike 2": ("730", "Counter-Strike 2"),
    "counter strike 2": ("730", "Counter-Strike 2"),
    "dota2": ("570", "Dota 2"),
    "dota 2": ("570", "Dota 2"),
    "rust": ("252490", "Rust"),
    "valheim": ("892970", "Valheim"),
    "cyberpunk": ("1091500", "Cyberpunk 2077"),
    "cyberpunk 2077": ("1091500", "Cyberpunk 2077"),
    "elden ring": ("1245620", "ELDEN RING"),
    "minecraft": ("1672970", "Minecraft Launcher"),
    "apex legends": ("1172470", "Apex Legends"),
    "apex": ("1172470", "Apex Legends"),
    "fortnite": ("1517990", "Fortnite"),
    "goose goose duck": ("1568590", "Goose Goose Duck"),
    "among us": ("945360", "Among Us"),
    "fall guys": ("1097150", "Fall Guys"),
    "rocket league": ("252950", "Rocket League"),
    "warframe": ("230410", "Warframe"),
    "destiny 2": ("1085660", "Destiny 2"),
    "team fortress 2": ("440", "Team Fortress 2"),
    "tf2": ("440", "Team Fortress 2"),
    "left 4 dead 2": ("550", "Left 4 Dead 2"),
    "l4d2": ("550", "Left 4 Dead 2"),
    "paladins": ("444090", "Paladins"),
    "smite": ("386360", "SMITE"),
    "war thunder": ("236390", "War Thunder"),
    "world of warships": ("552990", "World of Warships"),
    "path of exile": ("238960", "Path of Exile"),
    "poe": ("238960", "Path of Exile"),
    "lost ark": ("1599340", "Lost Ark"),
    "new world": ("1063730", "New World: Aeternum"),
    # additional popular titles
    "call of duty": ("1962663", "Call of Duty®"),
    "battlefield 2042": ("1517290", "Battlefield™ 2042"),
    "fifa 23": ("1811260", "EA SPORTS™ FIFA 23"),
    "the witcher 3": ("292030", "The Witcher 3: Wild Hunt"),
    "baldur's gate 3": ("1086940", "Baldur's Gate 3"),
}

# Regex patterns (precompiled)
_RE_APPID = re.compile(r'"appid"\s+"(\d+)"')
_RE_NAME = re.compile(r'"name"\s+"([^"]+)"')
_RE_STATE = re.compile(r'"StateFlags"\s+"(\d+)"')
_RE_SIZE = re.compile(r'"SizeOnDisk"\s+"(\d+)"')
_RE_VDF_PATH = re.compile(r'"path"\s+"([^"]+)"')
_RE_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")

# Steam state constants
STATE_UPTODATE = 4
STATE_DOWNLOADING = 1026
STATE_PENDING = {6, 516}


# --------------------------------------------------------------------
# Path helpers (cached)
# --------------------------------------------------------------------
@lru_cache(maxsize=1)
def _find_steam_path() -> Optional[Path]:
    if _is_windows():
        return _find_steam_windows()
    if _is_mac():
        return _find_steam_mac()
    return _find_steam_linux()


def _find_steam_windows() -> Optional[Path]:
    # Registry + common paths
    try:
        import winreg

        for hive, key_path in [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Valve\Steam"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Valve\Steam"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "InstallPath")
                winreg.CloseKey(key)
                p = Path(val)
                if (p / "steam.exe").exists():
                    return p
            except Exception:
                continue
    except ImportError:
        pass
    for p in [
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam",
        Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Steam",
        Path("C:/Steam"),
        Path("D:/Steam"),
        Path("E:/Steam"),
        Path("F:/Steam"),
    ]:
        if (p / "steam.exe").exists():
            return p
    return None


def _find_steam_mac() -> Optional[Path]:
    for p in [
        Path.home() / "Library/Application Support/Steam",
        Path("/Applications/Steam.app/Contents/MacOS"),
    ]:
        if p.exists():
            return p
    return None


def _find_steam_linux() -> Optional[Path]:
    for p in [
        Path.home() / ".steam/steam",
        Path.home() / ".steam/root",
        Path.home() / ".local/share/Steam",
        Path("/usr/share/steam"),
        Path("/opt/steam"),
    ]:
        if p.exists():
            return p
    return None


def _steam_exe(steam_path: Path) -> Path:
    if _is_windows():
        return steam_path / "steam.exe"
    if _is_mac():
        return Path("/Applications/Steam.app/Contents/MacOS/steam_osx")
    return steam_path / "steam.sh"


# --------------------------------------------------------------------
# Steam library scanning (cached with TTL)
# --------------------------------------------------------------------
_STEAM_GAMES_CACHE = {"data": [], "ts": 0, "steam_path": None}
_STEAM_LIBRARIES_CACHE = {"libs": [], "ts": 0, "steam_path": None}


def _get_steam_libraries(steam_path: Path) -> List[Path]:
    global _STEAM_LIBRARIES_CACHE
    now = time.time()
    if (
        _STEAM_LIBRARIES_CACHE["steam_path"] == steam_path
        and now - _STEAM_LIBRARIES_CACHE["ts"] < 60
    ):
        return _STEAM_LIBRARIES_CACHE["libs"]

    libraries = [steam_path / "steamapps"]
    vdf = steam_path / "steamapps" / "libraryfolders.vdf"
    if vdf.exists():
        try:
            content = vdf.read_text(encoding="utf-8", errors="ignore")
            for m in _RE_VDF_PATH.finditer(content):
                raw = m.group(1).replace("\\\\", "/")
                lib = Path(raw) / "steamapps"
                if lib.exists() and lib not in libraries:
                    libraries.append(lib)
        except Exception:
            pass
    _STEAM_LIBRARIES_CACHE = {"libs": libraries, "ts": now, "steam_path": steam_path}
    return libraries


def _get_steam_games(steam_path: Path) -> List[Dict]:
    global _STEAM_GAMES_CACHE
    now = time.time()
    if (
        _STEAM_GAMES_CACHE["steam_path"] == steam_path
        and now - _STEAM_GAMES_CACHE["ts"] < 30
    ):
        return _STEAM_GAMES_CACHE["data"]

    games = []
    for lib in _get_steam_libraries(steam_path):
        for acf in lib.glob("appmanifest_*.acf"):
            try:
                content = acf.read_text(encoding="utf-8", errors="ignore")
                app_id_match = _RE_APPID.search(content)
                name_match = _RE_NAME.search(content)
                state_match = _RE_STATE.search(content)
                size_match = _RE_SIZE.search(content)
                if app_id_match and name_match:
                    games.append(
                        {
                            "id": app_id_match.group(1),
                            "name": name_match.group(1),
                            "state": int(state_match.group(1)) if state_match else 0,
                            "size": int(size_match.group(1)) if size_match else 0,
                            "lib": str(lib),
                            "acf": str(acf),
                        }
                    )
            except Exception:
                continue
    _STEAM_GAMES_CACHE = {"data": games, "ts": now, "steam_path": steam_path}
    return games


# --------------------------------------------------------------------
# Steam process / window detection
# --------------------------------------------------------------------
def _is_steam_running() -> bool:
    try:
        if _is_windows():
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq steam.exe"],
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout
            return "steam.exe" in out.lower()
        proc = "steam_osx" if _is_mac() else "steam"
        out = subprocess.run(
            ["pgrep", "-x", proc], capture_output=True, text=True, timeout=3
        ).stdout
        return bool(out.strip())
    except Exception:
        return False


def _get_steam_window_rect() -> Optional[Tuple[int, int, int, int]]:
    gw = _lazy_pygetwindow()
    if not gw:
        return None
    try:
        for w in gw.getAllWindows():
            if "steam" in w.title.lower() and w.width > 200 and w.visible:
                return w.left, w.top, w.width, w.height
    except Exception:
        pass
    return None


# --------------------------------------------------------------------
# Steam launch / URL handling
# --------------------------------------------------------------------
def _launch_steam_url(exe: Path, url: str) -> None:
    if _is_mac():
        subprocess.Popen(["open", url])
    elif _is_linux():
        subprocess.Popen(["xdg-open", url])
    else:
        subprocess.Popen([str(exe), url])


# --------------------------------------------------------------------
# Profile selection (Steam login dialog)
# --------------------------------------------------------------------
def _click_first_profile_by_screenshot() -> bool:
    pyautogui = _lazy_pyautogui()
    np = _lazy_numpy()
    if not pyautogui or not np:
        return False
    try:
        time.sleep(1.5)
        win = _get_steam_window_rect()
        if not win:
            return False
        wx, wy, ww, wh = win
        screenshot = pyautogui.screenshot(region=(wx, wy, ww, wh))
        img = np.array(screenshot)
        h, w = img.shape[:2]
        # Search only middle area for colorful avatar
        y1, y2 = h // 3, h * 3 // 4
        x1, x2 = w // 5, w * 4 // 5
        region = img[y1:y2, x1:x2]
        r, g, b = (
            region[:, :, 0].astype(int),
            region[:, :, 1].astype(int),
            region[:, :, 2].astype(int),
        )
        max_c = np.maximum(np.maximum(r, g), b)
        min_c = np.minimum(np.minimum(r, g), b)
        colorful = (max_c > 60) & ((max_c - min_c) > 40)
        if not colorful.any():
            # fallback: click center‑left area
            pyautogui.click(wx + ww // 2 - ww // 6, wy + wh // 2)
            return True
        cols = np.where(colorful.any(axis=0))[0]
        rows = np.where(colorful.any(axis=1))[0]
        if not len(cols) or not len(rows):
            return False
        avatar_w = min(90, region.shape[1] // 4)
        first_col = int(cols[0])
        block_cols = cols[cols < first_col + avatar_w]
        abs_x = wx + x1 + int(block_cols.mean())
        abs_y = wy + y1 + int(rows.mean())
        pyautogui.click(abs_x, abs_y)
        return True
    except Exception as e:
        print(f"[GameUpdater] Profile click failed: {e}")
        return False


def _handle_steam_profile_selection() -> bool:
    win = _get_steam_window_rect()
    if not win:
        return False
    wx, wy, ww, wh = win
    pyautogui = _lazy_pyautogui()
    np = _lazy_numpy()
    # Quick check for small window / white top (likely login dialog)
    if pyautogui and np:
        try:
            screenshot = pyautogui.screenshot(region=(wx, wy, ww, wh))
            img = np.array(screenshot)
            is_small = ww < 900 and wh < 700
            top_region = img[: wh // 3, :, :]
            white_pixels = int(
                np.sum(
                    (top_region[:, :, 0] > 200)
                    & (top_region[:, :, 1] > 200)
                    & (top_region[:, :, 2] > 200)
                )
            )
            if not is_small and white_pixels <= 100:
                return False  # already logged in
        except Exception:
            pass
    print("[GameUpdater] Profile selection detected – clicking first profile.")
    return _click_first_profile_by_screenshot()


def _ensure_steam_running(steam_path: Path) -> bool:
    if _is_steam_running():
        return True
    exe = _steam_exe(steam_path)
    if not exe.exists():
        print(f"[GameUpdater] Steam executable not found: {exe}")
        return False
    print("[GameUpdater] Starting Steam...")
    if _is_mac():
        subprocess.Popen(["open", "-a", "Steam"])
    else:
        subprocess.Popen([str(exe)])
    for _ in range(30):
        time.sleep(1)
        if _is_steam_running():
            print("[GameUpdater] Steam is running.")
            time.sleep(5)
            if _is_windows():
                _handle_steam_profile_selection()
            return True
    print("[GameUpdater] Steam did not start within 30s.")
    return False


# --------------------------------------------------------------------
# Smart drive selection (for install dialog)
# --------------------------------------------------------------------
def _find_best_drive() -> Optional[Dict]:
    drives = []
    for letter in string.ascii_uppercase:
        drive_path = f"{letter}:\\"
        if os.path.exists(drive_path):
            try:
                free_gb = shutil.disk_usage(drive_path).free / (1024**3)
                if free_gb > 0.5:  # ignore tiny or full drives
                    drives.append(
                        {"letter": letter, "path": drive_path, "free_gb": free_gb}
                    )
            except Exception:
                continue
    return max(drives, key=lambda d: d["free_gb"]) if drives else None


def _select_drive_in_dialog(dialog, drive_letter: str) -> bool:
    target = drive_letter.upper()
    # Try direct controls
    for control_type in ("ListItem", "RadioButton"):
        try:
            for ctrl in dialog.descendants(control_type=control_type):
                if target in ctrl.window_text().upper():
                    ctrl.click_input()
                    return True
        except Exception:
            continue
    # Try combo box
    try:
        for combo in dialog.descendants(control_type="ComboBox"):
            try:
                combo.expand()
                time.sleep(0.2)
                for idx, txt in enumerate(combo.texts()):
                    if target in txt.upper():
                        combo.select(idx)
                        return True
                combo.collapse()
            except Exception:
                continue
    except Exception:
        pass
    # Last fallback: any control containing "C:" etc.
    try:
        for ctrl in dialog.descendants():
            txt = ctrl.window_text().upper()
            if f"{target}:" in txt and len(txt) < 80:
                ctrl.click_input()
                return True
    except Exception:
        pass
    return False


def _click_button(window, keywords: List[str]) -> bool:
    try:
        for btn in window.descendants(control_type="Button"):
            txt = btn.window_text().lower().strip()
            if txt in keywords or any(kw in txt for kw in keywords):
                btn.click_input()
                return True
    except Exception:
        pass
    return False


def _handle_install_dialog(game_name: str) -> str:
    best_drive = _find_best_drive()
    if not best_drive:
        return f"Install dialog for '{game_name}' opened, but no suitable drive found."
    drive_letter = best_drive["letter"]
    print(
        f"[GameUpdater] Target drive: {drive_letter}: ({best_drive['free_gb']:.1f} GB free)"
    )

    pywinauto = _lazy_pywinauto()
    if not pywinauto:
        # Fallback to pyautogui
        return _handle_install_dialog_pyautogui(game_name, best_drive)

    Application, findwindows = pywinauto
    dialog = None
    for _ in range(40):
        time.sleep(0.5)
        try:
            for hwnd in findwindows.find_windows(
                title_re=r"(?i)(install|yükle|steam)", visible_only=True
            ):
                try:
                    app = Application(backend="uia").connect(handle=hwnd)
                    win = app.window(handle=hwnd)
                    rect = win.rectangle()
                    if win.is_visible() and rect.width() > 300 and rect.height() > 200:
                        all_text = " ".join(
                            c.window_text()
                            for c in win.descendants()
                            if c.window_text()
                        ).upper()
                        if any(
                            d in all_text
                            for d in ("C:", "D:", "E:", "F:", "INSTALL", "YÜKLE")
                        ):
                            dialog = win
                            break
                except Exception:
                    continue
        except Exception:
            pass
        if dialog:
            break

    if not dialog:
        return _handle_install_dialog_pyautogui(game_name, best_drive)

    dialog.set_focus()
    time.sleep(0.4)
    drive_selected = _select_drive_in_dialog(dialog, drive_letter)
    install_clicked = _click_button(
        dialog, ["install", "yükle", "next", "ileri", "ok", "tamam"]
    )
    if install_clicked:
        msg = (
            f"Selected {drive_letter}: and"
            if drive_selected
            else "Default drive used, but"
        )
        return f"{msg} clicked Install for '{game_name}'."
    return f"Please click Install manually for '{game_name}'."


def _handle_install_dialog_pyautogui(game_name: str, best_drive: dict) -> str:
    pyautogui = _lazy_pyautogui()
    gw = _lazy_pygetwindow()
    if not pyautogui or not gw:
        return f"Please select '{best_drive['letter']}:' and click Install manually."
    pyautogui.FAILSAFE = False
    drive_label = f"{best_drive['letter']}:"
    install_win = None
    for _ in range(30):
        time.sleep(0.5)
        for w in gw.getAllWindows():
            if (
                ("install" in w.title.lower() or "steam" in w.title.lower())
                and w.width > 300
                and w.visible
            ):
                install_win = w
                break
        if install_win:
            break
    if not install_win:
        return f"Install dialog not found for '{game_name}'."
    try:
        install_win.activate()
        time.sleep(0.4)
    except Exception:
        pass
    wx, wy = install_win.left, install_win.top
    ww, wh = install_win.width, install_win.height
    # Click drive selection area (estimated)
    pyautogui.click(wx + int(ww * 0.35), wy + int(wh * 0.45))
    time.sleep(0.2)
    pyautogui.typewrite(best_drive["letter"], interval=0.05)
    time.sleep(0.2)
    # Click install button (estimated)
    pyautogui.click(wx + int(ww * 0.72), wy + int(wh * 0.88))
    return f"Attempted {drive_label} selection and Install click for '{game_name}'."


# --------------------------------------------------------------------
# App ID resolution (multi‑strategy with caching)
# --------------------------------------------------------------------
@lru_cache(maxsize=128)
def _search_steam_appid(game_name: str) -> Tuple[Optional[str], Optional[str]]:
    name_lower = game_name.lower().strip()
    if not name_lower:
        return None, None

    # 1. Exact match in known dict
    if name_lower in _KNOWN_APPIDS:
        app_id, canonical = _KNOWN_APPIDS[name_lower]
        return app_id, canonical

    # 2. Local Steam library
    steam_path = _find_steam_path()
    if steam_path:
        for g in _get_steam_games(steam_path):
            if name_lower in g["name"].lower():
                return g["id"], g["name"]

    # 3. Substring / fuzzy match in known dict
    best_ratio = 0
    best_candidate = None
    difflib = _lazy_difflib()
    for key, (app_id, canonical) in _KNOWN_APPIDS.items():
        if name_lower in key or key in name_lower:
            return app_id, canonical
        if difflib:
            ratio = difflib.SequenceMatcher(None, name_lower, key).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_candidate = (app_id, canonical)
    if best_candidate and best_ratio > 0.7:
        return best_candidate

    # 4. Online Steam Store API
    try:
        query = urllib.parse.quote(game_name)
        url = f"https://store.steampowered.com/api/storesearch/?term={query}&l=english&cc=US"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            items = json.loads(resp.read().decode()).get("items", [])
        if items:
            best = items[0]
            return str(best["id"]), best["name"]
    except Exception as e:
        print(f"[GameUpdater] Steam store search failed: {e}")

    return None, None


# --------------------------------------------------------------------
# Steam update / install logic
# --------------------------------------------------------------------
def _update_steam_games(steam_path: Path, game_name: str = None) -> str:
    if not _ensure_steam_running(steam_path):
        return "Could not start Steam."
    exe = _steam_exe(steam_path)
    games = _get_steam_games(steam_path)
    if not games:
        return "No Steam games found."

    if game_name:
        name_lower = game_name.lower()
        targets = [g for g in games if name_lower in g["name"].lower()]
        if not targets:
            return f"Game '{game_name}' not installed."
    else:
        targets = games

    updated, running, pending, errors = [], [], [], []
    for g in targets:
        state = g["state"]
        name = g["name"]
        if state == STATE_UPTODATE:
            updated.append(name)
        elif state == STATE_DOWNLOADING:
            running.append(name)
        elif state in STATE_PENDING:
            pending.append(name)
        else:
            try:
                _launch_steam_url(exe, f"steam://update/{g['id']}")
                updated.append(name)
                time.sleep(0.3)
            except Exception as e:
                errors.append(f"{name}: {e}")

    parts = []
    if updated:
        parts.append(f"Update started for {len(updated)} game(s).")
    if running:
        parts.append(f"Already downloading: {', '.join(running)}.")
    if pending:
        parts.append(f"Pending updates: {', '.join(pending[:3])}.")
    if errors:
        parts.append(f"Errors: {'; '.join(errors)}.")
    return " ".join(parts) if parts else "All games up to date."


def _install_steam_game(
    steam_path: Path, game_name: str = None, app_id: str = None
) -> str:
    if not _ensure_steam_running(steam_path):
        return "Could not start Steam."
    exe = _steam_exe(steam_path)
    installed = _get_steam_games(steam_path)

    # Check if already installed
    if app_id:
        already = next((g for g in installed if g["id"] == str(app_id)), None)
    elif game_name:
        name_lower = game_name.lower()
        already = next((g for g in installed if name_lower in g["name"].lower()), None)
    else:
        return "Please specify a game name or AppID."

    if already:
        state = already["state"]
        name = already["name"]
        if state == STATE_UPTODATE:
            return f"'{name}' is already installed and up to date."
        if state == STATE_DOWNLOADING:
            return f"'{name}' is currently downloading."
        if state in STATE_PENDING:
            _launch_steam_url(exe, f"steam://update/{already['id']}")
            return f"'{name}' has a pending update – update triggered."
        return f"'{name}' is already installed."

    # Resolve AppID if missing
    if not app_id and game_name:
        found_id, found_name = _search_steam_appid(game_name)
        if not found_id:
            return (
                f"Could not find '{game_name}' on Steam. "
                "Please check the name or provide an AppID."
            )
        app_id = found_id
        game_name = found_name or game_name

    _launch_steam_url(exe, f"steam://install/{app_id}")
    threading.Thread(
        target=_handle_install_dialog, args=(game_name,), daemon=True
    ).start()
    return f"Installation started for '{game_name}' (AppID {app_id})."


def _get_download_status(steam_path: Path) -> str:
    games = _get_steam_games(steam_path)
    active = [g for g in games if g["state"] == STATE_DOWNLOADING]
    pending = [g for g in games if g["state"] in STATE_PENDING]
    parts = []
    if active:
        parts.append(f"Downloading: {', '.join(g['name'] for g in active)}.")
    if pending:
        parts.append(f"Pending: {', '.join(g['name'] for g in pending[:5])}.")
    return " ".join(parts) if parts else "No active downloads or pending updates."


# --------------------------------------------------------------------
# Auto‑shutdown after downloads
# --------------------------------------------------------------------
def _system_shutdown() -> None:
    if _is_windows():
        subprocess.run(["shutdown", "/s", "/t", "10"])
    elif _is_mac():
        subprocess.run(["osascript", "-e", 'tell app "System Events" to shut down'])
    else:
        subprocess.run(["systemctl", "poweroff"])


def _watch_and_shutdown(
    steam_path: Path, speak=None, check_interval: int = 30, timeout_hours: int = 12
):
    deadline = time.time() + timeout_hours * 3600
    # Wait for download to actually start
    for _ in range(24):
        time.sleep(5)
        if any(g["state"] == STATE_DOWNLOADING for g in _get_steam_games(steam_path)):
            if speak:
                speak("Downloads are active. I will shut down once they finish.")
            break
    else:
        return  # no download started

    while time.time() < deadline:
        time.sleep(check_interval)
        if not any(
            g["state"] == STATE_DOWNLOADING for g in _get_steam_games(steam_path)
        ):
            if speak:
                speak("All downloads complete. Shutting down now.")
            time.sleep(5)
            _system_shutdown()
            return
    if speak:
        speak("Downloads are taking too long. Auto‑shutdown cancelled.")


# --------------------------------------------------------------------
# Epic Games support (unchanged core, minor optimisations)
# --------------------------------------------------------------------
@lru_cache(maxsize=1)
def _find_epic_exe() -> Optional[Path]:
    if _is_windows():
        return _find_epic_exe_windows()
    if _is_mac():
        return _find_epic_exe_mac()
    return _find_epic_exe_linux()


def _find_epic_exe_windows() -> Optional[Path]:
    try:
        import winreg

        for hive, key_path in [
            (
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\WOW6432Node\EpicGames\EpicGamesLauncher",
            ),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\EpicGames\EpicGamesLauncher"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\EpicGames\EpicGamesLauncher"),
        ]:
            try:
                key = winreg.OpenKey(hive, key_path)
                val, _ = winreg.QueryValueEx(key, "AppDataPath")
                winreg.CloseKey(key)
                exe = Path(val) / "Binaries" / "Win64" / "EpicGamesLauncher.exe"
                if exe.exists():
                    return exe
            except Exception:
                continue
    except ImportError:
        pass
    for candidate in [
        Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
        / "Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe",
        Path(os.environ.get("ProgramFiles", "C:/Program Files"))
        / "Epic Games/Launcher/Portal/Binaries/Win64/EpicGamesLauncher.exe",
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "EpicGamesLauncher/Portal/Binaries/Win64/EpicGamesLauncher.exe",
    ]:
        if candidate.exists():
            return candidate
    return None


def _find_epic_exe_mac() -> Optional[Path]:
    p = Path("/Applications/Epic Games Launcher.app/Contents/MacOS/EpicGamesLauncher")
    return p if p.exists() else None


def _find_epic_exe_linux() -> Optional[Path]:
    for c in [Path.home() / ".local/bin/heroic", Path("/usr/bin/heroic")]:
        if c.exists():
            return c
    return None


@lru_cache(maxsize=1)
def _epic_manifests_path() -> Optional[Path]:
    if _is_windows():
        p = (
            Path(os.environ.get("PROGRAMDATA", "C:/ProgramData"))
            / "Epic/EpicGamesLauncher/Data/Manifests"
        )
    elif _is_mac():
        p = (
            Path.home()
            / "Library/Application Support/Epic/EpicGamesLauncher/Data/Manifests"
        )
    else:
        return None
    return p if p.exists() else None


def _get_epic_games() -> List[Dict]:
    manifests = _epic_manifests_path()
    if not manifests:
        return []
    games = []
    for item_file in manifests.glob("*.item"):
        try:
            data = json.loads(item_file.read_text(encoding="utf-8"))
            name = data.get("DisplayName") or data.get("AppName", "")
            if name:
                games.append({"id": data.get("AppName", ""), "name": name})
        except Exception:
            continue
    return games


def _is_epic_running() -> bool:
    try:
        if _is_windows():
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq EpicGamesLauncher.exe"],
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout
            return "epicgameslauncher.exe" in out.lower()
        proc = "EpicGamesLauncher" if _is_mac() else "heroic"
        out = subprocess.run(
            ["pgrep", "-x", proc], capture_output=True, text=True, timeout=3
        ).stdout
        return bool(out.strip())
    except Exception:
        return False


def _update_epic_games(epic_exe: Path, game_name: str = None) -> str:
    games = _get_epic_games()
    if game_name:
        name_lower = game_name.lower()
        matched = [g for g in games if name_lower in g["name"].lower()]
        if not matched:
            return f"'{game_name}' not found in Epic Games library."
        url = f"com.epicgames.launcher://apps/{matched[0]['id']}?action=launch&silent=true"
        try:
            if _is_mac():
                subprocess.Popen(["open", url])
            elif _is_linux():
                if epic_exe:
                    subprocess.Popen([str(epic_exe), url])
                else:
                    subprocess.Popen(["xdg-open", url])
            else:
                subprocess.Popen([str(epic_exe), url])
            return f"Update triggered for '{matched[0]['name']}' on Epic."
        except Exception as e:
            return f"Epic update failed: {e}"
    else:
        if _is_mac():
            subprocess.Popen(["open", "-a", "Epic Games Launcher"])
        elif _is_linux():
            if epic_exe:
                subprocess.Popen([str(epic_exe)])
            else:
                return (
                    "Epic Games Launcher not natively available on Linux. Use Heroic."
                )
        else:
            if _is_epic_running():
                for g in games[:10]:
                    subprocess.Popen(
                        [
                            str(epic_exe),
                            f"com.epicgames.launcher://apps/{g['id']}?action=launch&silent=true",
                        ]
                    )
                    time.sleep(0.5)
                return f"Update check triggered for {len(games)} Epic games."
            else:
                subprocess.Popen([str(epic_exe)])
        return "Epic Games Launcher opened."


# --------------------------------------------------------------------
# Scheduling helpers
# --------------------------------------------------------------------
def _schedule_daily_update(hour: int = 3, minute: int = 0) -> str:
    if _is_windows():
        return _schedule_windows(hour, minute)
    if _is_mac():
        return _schedule_mac(hour, minute)
    return _schedule_linux(hour, minute)


def _schedule_windows(hour: int, minute: int) -> str:
    task_name = "INDRA_GameUpdater"
    script_path = Path(__file__).resolve()
    subprocess.run(["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True)
    cmd = [
        "schtasks",
        "/Create",
        "/TN",
        task_name,
        "/TR",
        f'"{sys.executable}" "{script_path}" --scheduled',
        "/SC",
        "DAILY",
        "/ST",
        f"{hour:02d}:{minute:02d}",
        "/F",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        return f"Daily update scheduled at {hour:02d}:{minute:02d}."
    return f"Scheduling failed: {result.stderr.strip()}"


def _schedule_mac(hour: int, minute: int) -> str:
    plist_dir = Path.home() / "Library/LaunchAgents"
    plist_dir.mkdir(parents=True, exist_ok=True)
    plist_path = plist_dir / "com.INDRA.gameupdater.plist"
    script_path = Path(__file__).resolve()
    plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
    <key>Label</key><string>com.INDRA.gameupdater</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{script_path}</string>
        <string>--scheduled</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>{hour}</integer>
        <key>Minute</key><integer>{minute}</integer>
    </dict>
    <key>RunAtLoad</key><false/>
</dict></plist>"""
    try:
        plist_path.write_text(plist, encoding="utf-8")
        subprocess.run(["launchctl", "unload", str(plist_path)], capture_output=True)
        result = subprocess.run(
            ["launchctl", "load", str(plist_path)], capture_output=True, text=True
        )
        if result.returncode == 0:
            return f"Daily update scheduled at {hour:02d}:{minute:02d}."
        return f"Scheduling failed: {result.stderr.strip()}"
    except Exception as e:
        return f"Scheduling failed: {e}"


def _schedule_linux(hour: int, minute: int) -> str:
    script_path = Path(__file__).resolve()
    marker = "# INDRA_GameUpdater"
    cron_entry = (
        f"{minute} {hour} * * * {sys.executable} {script_path} --scheduled  {marker}"
    )
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = [
            l
            for l in existing.stdout.splitlines()
            if marker not in l and str(script_path) not in l
        ]
        lines.append(cron_entry)
        proc = subprocess.run(
            ["crontab", "-"],
            input="\n".join(lines) + "\n",
            text=True,
            capture_output=True,
        )
        if proc.returncode == 0:
            return f"Daily update scheduled at {hour:02d}:{minute:02d}."
        return f"Scheduling failed: {proc.stderr.strip()}"
    except Exception as e:
        return f"Scheduling failed: {e}"


def _cancel_scheduled_update() -> str:
    if _is_windows():
        result = subprocess.run(
            ["schtasks", "/Delete", "/TN", "INDRA_GameUpdater", "/F"],
            capture_output=True,
            text=True,
        )
        return (
            "Scheduled update cancelled."
            if result.returncode == 0
            else "No scheduled update found."
        )
    if _is_mac():
        plist_path = Path.home() / "Library/LaunchAgents/com.INDRA.gameupdater.plist"
        if plist_path.exists():
            subprocess.run(
                ["launchctl", "unload", str(plist_path)], capture_output=True
            )
            plist_path.unlink()
            return "Scheduled update cancelled."
        return "No scheduled update found."
    try:
        existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = [
            l for l in existing.stdout.splitlines() if "INDRA_GameUpdater" not in l
        ]
        subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True)
        return "Scheduled update cancelled."
    except Exception as e:
        return f"Cancel failed: {e}"


def _get_schedule_status() -> str:
    if _is_windows():
        result = subprocess.run(
            ["schtasks", "/Query", "/TN", "INDRA_GameUpdater", "/FO", "LIST"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return "No scheduled update."
        for line in result.stdout.splitlines():
            if "Next Run" in line or "Sonraki" in line or "Nächste" in line:
                return f"Update scheduled. {line.strip()}"
        return "Update is scheduled."
    if _is_mac():
        plist_path = Path.home() / "Library/LaunchAgents/com.INDRA.gameupdater.plist"
        return (
            "Update scheduled via launchd."
            if plist_path.exists()
            else "No scheduled update."
        )
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        if "INDRA_GameUpdater" in result.stdout:
            for line in result.stdout.splitlines():
                if "INDRA_GameUpdater" in line:
                    return f"Update scheduled: {line.split('#')[0].strip()}"
        return "No scheduled update."
    except Exception:
        return "No scheduled update."


# --------------------------------------------------------------------
# Main Controller (100% compatible with original)
# --------------------------------------------------------------------
def game_updater(parameters: dict, player=None, speak=None) -> str:
    """
    Parameters expected:
        action: "update", "install", "list", "download_status", "schedule", ...
        platform: "steam", "epic", or "both"
        game_name: (optional)
        app_id: (optional)
        hour, minute: for schedule
        shutdown_when_done: "true"/"false"
    """
    p = parameters or {}
    action = p.get("action", "update").lower().strip()
    platform = p.get("platform", "both").lower().strip()
    game_name = (p.get("game_name") or "").strip() or None
    app_id = (p.get("app_id") or "").strip() or None
    hour = int(p.get("hour", 3))
    minute = int(p.get("minute", 0))
    shutdown = str(p.get("shutdown_when_done", "false")).lower() == "true"

    results = []

    # Immediate actions
    if action == "schedule":
        return _schedule_daily_update(hour, minute)
    if action == "cancel_schedule":
        return _cancel_scheduled_update()
    if action == "schedule_status":
        return _get_schedule_status()

    if action == "list":
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if steam_path:
                games = _get_steam_games(steam_path)
                if games:
                    names = ", ".join(g["name"] for g in games[:8])
                    suffix = f" and {len(games)-8} more" if len(games) > 8 else ""
                    results.append(f"Steam ({len(games)}): {names}{suffix}.")
                else:
                    results.append("Steam: No games found.")
            else:
                results.append("Steam not installed.")
        if platform in ("epic", "both"):
            if _is_linux():
                results.append("Epic not natively supported on Linux.")
            else:
                games = _get_epic_games()
                if games:
                    names = ", ".join(g["name"] for g in games[:8])
                    suffix = f" and {len(games)-8} more" if len(games) > 8 else ""
                    results.append(f"Epic ({len(games)}): {names}{suffix}.")
                else:
                    results.append("Epic: No games found.")
        return " | ".join(results) or "No platforms found."

    if action == "download_status":
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if steam_path:
                results.append(_get_download_status(steam_path))
            else:
                results.append("Steam not installed.")
        if platform in ("epic", "both"):
            results.append("Epic download status not directly available.")
        return " ".join(results)

    if action in ("install", "update"):
        # Steam
        if platform in ("steam", "both"):
            steam_path = _find_steam_path()
            if not steam_path:
                results.append("Steam not installed.")
            else:
                if game_name:
                    # Smart decision: install if missing, else update
                    installed = _get_steam_games(steam_path)
                    name_lower = game_name.lower()
                    is_installed = any(
                        name_lower in g["name"].lower() for g in installed
                    )
                    if not is_installed and action == "install":
                        msg = _install_steam_game(
                            steam_path, game_name=game_name, app_id=app_id
                        )
                        if shutdown:
                            threading.Thread(
                                target=_watch_and_shutdown,
                                args=(steam_path, speak),
                                daemon=True,
                            ).start()
                            msg += " Auto‑shutdown enabled."
                        results.append(msg)
                    else:
                        results.append(
                            _update_steam_games(steam_path, game_name=game_name)
                        )
                else:
                    if action == "install":
                        results.append("Steam: please specify a game name to install.")
                    else:
                        results.append(_update_steam_games(steam_path))
                # Shutdown thread (for update all)
                if shutdown and action == "update" and not game_name:
                    threading.Thread(
                        target=_watch_and_shutdown,
                        args=(steam_path, speak),
                        daemon=True,
                    ).start()
                    results.append("Auto‑shutdown enabled.")

        # Epic
        if platform in ("epic", "both"):
            if _is_linux():
                results.append("Epic not natively supported on Linux.")
            else:
                epic_exe = _find_epic_exe()
                if epic_exe:
                    results.append(_update_epic_games(epic_exe, game_name=game_name))
                else:
                    results.append("Epic not installed.")

        output = " | ".join(results) or "No action taken."
        if player:
            player.write_log(f"[GameUpdater] {output[:100]}")
        if speak:
            speak(output)
        return output

    return f"Unknown action: '{action}'."


# --------------------------------------------------------------------
# Direct scheduled run entry point
# --------------------------------------------------------------------
if __name__ == "__main__":
    if "--scheduled" in sys.argv:
        print(f"[GameUpdater] Scheduled run at {datetime.now().strftime('%H:%M')}")
        result = game_updater({"action": "update", "platform": "both"})
        print(f"[GameUpdater] {result}")
