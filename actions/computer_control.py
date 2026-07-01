                     
                                                                                                                                       
from __future__ import annotations

from core.utils import STATS, Config, get_gemini_client, log, synchronized_ui

"""
computer_control.py  ─  Peak-Performance Desktop Automation Module
═══════════════════════════════════════════════════════════════════
All original actions (type, smart_type, click, double_click,
right_click, move, drag, hotkey, press, scroll, copy, paste,
screenshot, wait, clear_field, focus_window, screen_find,
screen_click, random_data, user_data) are 100% preserved.

New actions added (zero breaking changes):
  middle_click, hover, type_in_field, screenshot_region,
  screen_type (find→click→type), action_chain, health_check,
  calibrate, reset_identity, deps, metrics

What changed internally (non-breaking):
  ▸ Structured logging     — rotating file + console; replaces print()
  ▸ Audit trail            — JSONL append at ~/.INDRA/logs/audit.jsonl
  ▸ Retry decorator        — exponential back-off, per-action config
  ▸ Config cache           — thread-safe, 60 s TTL re-read
  ▸ Memory cache           — thread-safe user-profile cache
  ▸ Bézier mouse           — cubic Bézier human-like movement curves
  ▸ Human typing           — variable speed + full Unicode via clipboard
  ▸ Multi-strategy clipboard — xclip/xsel/pbcopy/PowerShell fallbacks
  ▸ Window focus + verify  — confirm focus after each attempt
  ▸ screen_find cache      — 4 s TTL, bounds-checked
  ▸ Full param validation  — types, coordinate clamp, required fields
  ▸ Session-consistent IDs — same name/email across a form-fill session
  ▸ 25+ random data types  — Luhn-valid cards, realistic bios, etc.
  ▸ Dependency probe       — graceful degrade + install hints
  ▸ Per-action metrics     — wall-time, call counts, min/max/avg
"""

import functools
import hashlib
import io
import json
import logging
import math
import os
import platform
import random
import re
import string
import subprocess
import sys
import threading
import time
import traceback
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Union

                              


def _probe(pkg: str) -> bool:
    import importlib

    try:
        importlib.import_module(pkg)
        return True
    except ImportError:
        return False

_PYAUTOGUI_OK = _probe("pyautogui")
_PYPERCLIP_OK = _probe("pyperclip")
_PIL_OK = _probe("PIL")
_NUMPY_OK = _probe("numpy")

if _PYAUTOGUI_OK:
    import pyautogui

    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.02                              

if _PYPERCLIP_OK:
    import pyperclip

if _PIL_OK:
    from PIL import Image

                                                                      



def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

_BASE = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"
_MEMORY_PATH = _BASE / "memory" / "long_term.json"
_LOG_DIR = Path.home() / ".INDRA" / "logs"
_AUDIT_PATH = _LOG_DIR / "audit.jsonl"
_METRICS_PATH = _LOG_DIR / "metrics.json"

_LOG_DIR.mkdir(parents=True, exist_ok=True)

_SAFE_SCREENSHOT_ROOTS: Tuple[Path, ...] = (Path.home(),)

                                                                      



               


@dataclass
class RetryConfig:
    attempts: int = 3
    base_delay: float = 0.4
    max_delay: float = 8.0
    backoff: float = 2.0
    jitter: float = 0.1

@dataclass
class ActionResult:
    action: str
    success: bool
    output: str
    elapsed: float
    attempt: int = 1
    error: str = ""

@dataclass
class _CacheEntry:
    value: Any
    ts: float
    ttl: float

    def valid(self) -> bool:
        return (time.monotonic() - self.ts) < self.ttl

                                                                      



class _Cache:
    """Generic thread-safe key→value cache with per-entry TTL."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._store: Dict[str, _CacheEntry] = {}

    def get(self, key: str) -> Any | None:
        with self._lock:
            entry = self._store.get(key)
            if entry and entry.valid():
                return entry.value
            self._store.pop(key, None)
            return None

    def set(self, key: str, value: Any, ttl: float = 30.0) -> None:
        with self._lock:
            self._store[key] = _CacheEntry(value=value, ts=time.monotonic(), ttl=ttl)

    def invalidate(self, key: str) -> None:
        with self._lock:
            self._store.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

_cache = _Cache()

                                                                      



class _Metrics:
    """In-memory metrics collector; flushes to JSON on request."""

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()
        self._data: Dict[str, Dict[str, Any]] = {}

    def record(self, action: str, elapsed: float, success: bool) -> None:
        with self._lock:
            d = self._data.setdefault(
                action,
                {
                    "calls": 0,
                    "successes": 0,
                    "failures": 0,
                    "total_ms": 0.0,
                    "max_ms": 0.0,
                    "min_ms": float("inf"),
                },
            )
            ms = elapsed * 1_000
            d["calls"] += 1
            d["total_ms"] += ms
            d["max_ms"] = max(d["max_ms"], ms)
            d["min_ms"] = min(d["min_ms"], ms)
            if success:
                d["successes"] += 1
            else:
                d["failures"] += 1

    def summary(self) -> Dict[str, Any]:
        with self._lock:
            out: Dict[str, Any] = {}
            for action, d in self._data.items():
                calls = d["calls"] or 1
                out[action] = {
                    **d,
                    "avg_ms": round(d["total_ms"] / calls, 2),
                    "min_ms": round(d["min_ms"], 2),
                    "success_pct": round(100 * d["successes"] / calls, 1),
                }
            return out

    def flush(self) -> None:
        try:
            with open(_METRICS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.summary(), f, indent=2)
        except Exception:
            pass

_metrics = _Metrics()

                                                                      



def _audit(result: ActionResult, params: dict) -> None:
    """Append one JSONL entry per action call for full auditability."""
    try:
        safe_params = {k: str(v)[:120] for k, v in params.items() if k != "action"}
        entry: Dict[str, Any] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "action": result.action,
            "success": result.success,
            "elapsed": round(result.elapsed, 4),
            "output": result.output[:200],
            "params": safe_params,
        }
        if result.error:
            entry["error"] = result.error[:300]
        with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass

                                                                      


_DEFAULT_RETRY = RetryConfig()

def _with_retry(cfg: RetryConfig = _DEFAULT_RETRY) -> Callable:
    """Decorator factory — retry on any exception with exponential back-off."""

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Exception | None = None
            delay = cfg.base_delay
            for attempt in range(1, cfg.attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt == cfg.attempts:
                        break
                    jitter = random.uniform(-cfg.jitter, cfg.jitter) * delay
                    sleep = min(delay + jitter, cfg.max_delay)
                    log.warning(
                        "Retry %d/%d for %s after %.2fs — %s",
                        attempt,
                        cfg.attempts,
                        fn.__name__,
                        sleep,
                        exc,
                    )
                    time.sleep(sleep)
                    delay = min(delay * cfg.backoff, cfg.max_delay)
            raise last_exc                      

        return wrapper

    return decorator

                                                                      


_cfg_lock = threading.Lock()

def _load_config() -> dict:
    cached = _cache.get("config")
    if cached is not None:
        return cached
    with _cfg_lock:
        cached = _cache.get("config")                           
        if cached is not None:
            return cached
        try:
            data: dict = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
        except Exception:
            data = {}
        _cache.set("config", data, ttl=60.0)
        return data

def _platform_os() -> str:
    return {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
        platform.system(), "linux"
    )

def _get_os() -> str:
    return _load_config().get("os_system", _platform_os()).lower()

def _get_api_key() -> str:
    return _load_config().get("gemini_api_key", "")

def _get_screen_size() -> Tuple[int, int]:
    cached = _cache.get("screen_size")
    if cached:
        return cached
    if _PYAUTOGUI_OK:
        size = pyautogui.size()
        result = (int(size[0]), int(size[1]))
        _cache.set("screen_size", result, ttl=300.0)
        return result
    return 1920, 1080

                                                                      


_mem_lock = threading.Lock()

def _user_profile() -> dict:
    cached = _cache.get("user_profile")
    if cached is not None:
        return cached
    with _mem_lock:
        cached = _cache.get("user_profile")
        if cached is not None:
            return cached
        profile: dict = {}
        try:
            if _MEMORY_PATH.exists():
                data = json.loads(_MEMORY_PATH.read_text(encoding="utf-8"))
                identity = data.get("identity", {})
                profile = {k: v.get("value", "") for k, v in identity.items()}
        except Exception as e:
            log.warning("Could not read user profile: %s", e)
        _cache.set("user_profile", profile, ttl=120.0)
        return profile

def _invalidate_user_profile() -> None:
    _cache.invalidate("user_profile")

                                                                      



def _require_pyautogui() -> None:
    if not _PYAUTOGUI_OK:
        raise RuntimeError(
            "PyAutoGUI not installed.\n"
            "  Install: pip install pyautogui\n"
            "  Linux extra: sudo apt-get install python3-tk python3-dev scrot\n"
            "  macOS extra: grant Accessibility permission in System Preferences"
        )

def _check_deps() -> Dict[str, bool]:
    return {
        "pyautogui": _PYAUTOGUI_OK,
        "pyperclip": _PYPERCLIP_OK,
        "PIL": _PIL_OK,
        "numpy": _NUMPY_OK,
        "wmctrl": _cmd_exists("wmctrl"),
        "xdotool": _cmd_exists("xdotool"),
        "xclip": _cmd_exists("xclip"),
        "xsel": _cmd_exists("xsel"),
    }

def _cmd_exists(cmd: str) -> bool:
    """Check if a CLI tool is on PATH."""
    cached_key = f"cmd_exists:{cmd}"
    cached = _cache.get(cached_key)
    if cached is not None:
        return cached
    result = (
        subprocess.run(
            ["which", cmd] if _get_os() != "windows" else ["where", cmd],
            capture_output=True,
        ).returncode
        == 0
    )
    _cache.set(cached_key, result, ttl=600.0)
    return result

def _health_check() -> str:
    """Full system readiness report."""
    deps = _check_deps()
    lines = ["── Dependency Status ──"]
    for name, ok in deps.items():
        lines.append(f"  {'✓' if ok else '✗'} {name}")

    lines.append("── System Info ──")
    lines.append(f"  OS:       {platform.system()} {platform.release()}")
    lines.append(f"  Python:   {sys.version.split()[0]}")
    if _PYAUTOGUI_OK:
        w, h = _get_screen_size()
        lines.append(f"  Screen:   {w}×{h}")
    lines.append(f"  API key:  {'set' if _get_api_key() else 'MISSING'}")
    lines.append(f"  Config:   {'found' if _CONFIG_PATH.exists() else 'missing'}")
    lines.append(f"  Memory:   {'found' if _MEMORY_PATH.exists() else 'missing'}")
    lines.append(f"  Log dir:  {_LOG_DIR}")
    return "\n".join(lines)

                                                                      



def _validate_coords(x: Any, y: Any, *, label: str = "coordinate") -> Tuple[int, int]:
    try:
        xi, yi = int(x), int(y)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid {label}: x={x!r}, y={y!r} — {e}") from e
    w, h = _get_screen_size()
    xi = max(0, min(xi, w - 1))
    yi = max(0, min(yi, h - 1))
    return xi, yi

def _validate_str(
    val: Any,
    name: str,
    *,
    default: str = "",
    allow_empty: bool = True,
) -> str:
    if val is None:
        if not allow_empty:
            raise ValueError(f"'{name}' is required and cannot be empty")
        return default
    s = str(val)
    if not allow_empty and not s.strip():
        raise ValueError(f"'{name}' must not be blank")
    return s

def _validate_float(
    val: Any,
    name: str,
    *,
    lo: float = 0.0,
    hi: float = 1e9,
    default: float | None = None,
) -> float:
    if val is None and default is not None:
        return default
    try:
        f = float(val)
    except (TypeError, ValueError) as e:
        raise ValueError(f"'{name}' must be a number, got {val!r}") from e
    return max(lo, min(f, hi))

def _validate_int(
    val: Any,
    name: str,
    *,
    lo: int = 0,
    hi: int = 2**31,
    default: int | None = None,
) -> int:
    if val is None and default is not None:
        return default
    try:
        i = int(val)
    except (TypeError, ValueError) as e:
        raise ValueError(f"'{name}' must be an integer, got {val!r}") from e
    return max(lo, min(i, hi))

                                                                      



def _safe_screenshot_path(requested: str | None) -> Path:
    fallback = Path.home() / "Desktop" / "INDRA_screenshot.png"
    if not requested:
        return fallback
    try:
        p = Path(requested).expanduser().resolve()
        for root in _SAFE_SCREENSHOT_ROOTS:
            if p.is_relative_to(root.resolve()):
                p.parent.mkdir(parents=True, exist_ok=True)
                return p
    except Exception:
        pass
    log.warning("Unsafe screenshot path %r — using fallback", requested)
    return fallback

                                                                      



def _bezier_points(
    p0: Tuple[float, float],
    p3: Tuple[float, float],
    *,
    steps: int = 40,
    deviation: float = 0.22,
) -> List[Tuple[int, int]]:
    """
    Cubic Bézier path from p0 → p3 with two randomised control points.
    Returns `steps` intermediate pixel positions for smooth human-like motion.
    """
    x0, y0 = p0
    x3, y3 = p3
    dx = x3 - x0
    dy = y3 - y0
    dist = math.hypot(dx, dy) or 1.0
    base_angle = math.atan2(dy, dx)

    def rand_ctrl(frac: float) -> Tuple[float, float]:
        angle = base_angle + random.uniform(-0.4, 0.4)
        r = dist * frac * (1 + random.uniform(-deviation, deviation))
        return x0 + r * math.cos(angle), y0 + r * math.sin(angle)

    cp1 = rand_ctrl(0.33)
    cp2 = rand_ctrl(0.67)

    pts: List[Tuple[int, int]] = []
    for i in range(steps + 1):
        t = i / steps
        it = 1 - t
        x = it**3 * x0 + 3 * it**2 * t * cp1[0] + 3 * it * t**2 * cp2[0] + t**3 * x3
        y = it**3 * y0 + 3 * it**2 * t * cp1[1] + 3 * it * t**2 * cp2[1] + t**3 * y3
        pts.append((round(x), round(y)))
    return pts

                                                                      


_TIMING_MULTIPLIER: float = 1.0                              

def _calibrate() -> str:
    """
    Benchmark mouse and keyboard response time, then adjust
    _TIMING_MULTIPLIER to keep actions snappy on fast hardware
    and safe on slow hardware.
    """
    global _TIMING_MULTIPLIER
    if not _PYAUTOGUI_OK:
        return "Calibration skipped: PyAutoGUI not available"

    samples: List[float] = []
    try:
        cx, cy = pyautogui.position()
        for _ in range(5):
            t0 = time.monotonic()
            pyautogui.moveTo(cx + 1, cy + 1, duration=0)
            pyautogui.moveTo(cx, cy, duration=0)
            samples.append(time.monotonic() - t0)
    except Exception as e:
        return f"Calibration failed: {e}"

    avg_ms = (sum(samples) / len(samples)) * 1_000
    if avg_ms < 5:
        _TIMING_MULTIPLIER = 0.8                                 
    elif avg_ms < 20:
        _TIMING_MULTIPLIER = 1.0           
    else:
        _TIMING_MULTIPLIER = 1.4                                      

    log.info(
        "Calibration: avg move=%.1f ms → multiplier=%.1f", avg_ms, _TIMING_MULTIPLIER
    )
    return f"Calibrated: avg={avg_ms:.1f} ms, multiplier={_TIMING_MULTIPLIER:.1f}"

def _t(base: float) -> float:
    """Return calibration-adjusted delay."""
    return base * _TIMING_MULTIPLIER

                                                                      



@_with_retry(RetryConfig(attempts=2, base_delay=0.1))
def _move(
    x: int,
    y: int,
    duration: float = 0.3,
    *,
    human: bool = True,
) -> str:
    _require_pyautogui()
    x, y = _validate_coords(x, y)
    duration = _validate_float(duration, "duration", lo=0.0, hi=10.0)

    if human and duration > 0.05:
        cx, cy = pyautogui.position()
        n_steps = max(10, int(duration / 0.01))
        pts = _bezier_points((cx, cy), (x, y), steps=n_steps)
        step_t = _t(duration) / max(len(pts) - 1, 1)
        for px, py in pts[1:]:
            pyautogui.moveTo(px, py, duration=0)
            time.sleep(step_t)
    else:
        pyautogui.moveTo(x, y, duration=duration)

    log.debug("Mouse → (%d, %d)", x, y)
    return f"Moved mouse → ({x}, {y})"

@_with_retry(RetryConfig(attempts=3, base_delay=0.15))
def _click(
    x: int | None = None,
    y: int | None = None,
    button: str = "left",
    clicks: int = 1,
    *,
    move_duration: float = 0.25,
    pre_delay: float = 0.05,
    post_delay: float = 0.06,
) -> str:
    _require_pyautogui()
    button = button if button in ("left", "right", "middle") else "left"

    if x is not None and y is not None:
        x, y = _validate_coords(x, y)
        _move(x, y, duration=move_duration)

    time.sleep(_t(pre_delay))
    pyautogui.click(button=button, clicks=clicks, interval=0.08)
    time.sleep(_t(post_delay))

    pos = f"({x}, {y})" if x is not None else "current position"
    label = "Double-clicked" if clicks == 2 else "Clicked"
    log.debug("%s %s [%s]", label, pos, button)
    return f"{'Double-c' if clicks == 2 else 'C'}licked {pos} [{button}]"

@_with_retry(RetryConfig(attempts=2, base_delay=0.1))
def _hover(x: int, y: int, duration: float = 0.5) -> str:
    _require_pyautogui()
    x, y = _validate_coords(x, y)
    _move(x, y, duration=duration)
    time.sleep(_t(0.1))
    log.debug("Hover @ (%d, %d)", x, y)
    return f"Hovered at ({x}, {y})"

@_with_retry(RetryConfig(attempts=2, base_delay=0.15))
def _drag(
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration: float = 0.6,
) -> str:
    _require_pyautogui()
    x1, y1 = _validate_coords(x1, y1)
    x2, y2 = _validate_coords(x2, y2)
    duration = _validate_float(duration, "duration", lo=0.0, hi=15.0)

    _move(x1, y1, duration=0.25)
    time.sleep(_t(0.1))

    n_steps = max(15, int(duration / 0.01))
    pts = _bezier_points((x1, y1), (x2, y2), steps=n_steps)
    step_t = _t(duration) / max(len(pts) - 1, 1)

    pyautogui.mouseDown(button="left")
    for px, py in pts[1:]:
        pyautogui.moveTo(px, py, duration=0)
        time.sleep(step_t)
    pyautogui.mouseUp(button="left")

    log.debug("Drag (%d,%d) → (%d,%d)", x1, y1, x2, y2)
    return f"Dragged ({x1},{y1}) → ({x2},{y2})"

@_with_retry(RetryConfig(attempts=2, base_delay=0.1))
def _scroll(direction: str = "down", amount: int = 3) -> str:
    _require_pyautogui()
    direction = direction.lower().strip()
    if direction not in ("up", "down", "left", "right"):
        direction = "down"
    amount = _validate_int(amount, "amount", lo=1, hi=50)

    if direction in ("up", "down"):
        pyautogui.scroll(amount if direction == "up" else -amount)
    else:
        pyautogui.hscroll(amount if direction == "right" else -amount)

    log.debug("Scroll %s ×%d", direction, amount)
    return f"Scrolled {direction} ×{amount}"

                                                                      


                                                         
_TYPEWRITE_SAFE = frozenset(
    string.ascii_letters + string.digits + string.punctuation + " \t"
)

def _can_typewrite(text: str) -> bool:
    return all(c in _TYPEWRITE_SAFE for c in text)

                                
_KEY_ALIASES: Dict[str, str] = {
    "enter": "enter",
    "return": "enter",
    "esc": "escape",
    "escape": "escape",
    "del": "delete",
    "backspace": "backspace",
    "tab": "tab",
    "space": "space",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pgup": "pageup",
    "pgdn": "pagedown",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "f1": "f1",
    "f2": "f2",
    "f3": "f3",
    "f4": "f4",
    "f5": "f5",
    "f6": "f6",
    "f7": "f7",
    "f8": "f8",
    "f9": "f9",
    "f10": "f10",
    "f11": "f11",
    "f12": "f12",
}

def _resolve_key(key: str) -> str:
    return _KEY_ALIASES.get(key.lower(), key.lower())

def _os_clipboard_set(text: str) -> bool:
    """Platform-native clipboard write — fallback when pyperclip absent."""
    os_name = _get_os()
    try:
        if os_name == "mac":
            subprocess.run(
                ["pbcopy"], input=text.encode("utf-8"), check=True, timeout=3
            )
            return True
        if os_name == "linux":
            for cmd in (
                ["xclip", "-selection", "clipboard"],
                ["xsel", "--clipboard", "--input"],
            ):
                try:
                    subprocess.run(
                        cmd, input=text.encode("utf-8"), check=True, timeout=3
                    )
                    return True
                except (FileNotFoundError, subprocess.CalledProcessError):
                    continue
        if os_name == "windows":
            escaped = text.replace("'", "''")
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Set-Clipboard -Value '{escaped}'",
                ],
                capture_output=True,
                timeout=5,
            )
            return True
    except Exception as e:
        log.warning("OS clipboard write failed: %s", e)
    return False

def _os_clipboard_get() -> str:
    """Platform-native clipboard read — fallback when pyperclip absent."""
    os_name = _get_os()
    try:
        if os_name == "mac":
            r = subprocess.run(["pbpaste"], capture_output=True, timeout=3)
            return r.stdout.decode("utf-8", errors="replace")
        if os_name == "linux":
            for cmd in (
                ["xclip", "-selection", "clipboard", "-o"],
                ["xsel", "--clipboard", "--output"],
            ):
                try:
                    r = subprocess.run(cmd, capture_output=True, timeout=3)
                    if r.returncode == 0:
                        return r.stdout.decode("utf-8", errors="replace")
                except FileNotFoundError:
                    continue
        if os_name == "windows":
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                timeout=5,
            )
            return r.stdout.decode("utf-8", errors="replace").strip()
    except Exception as e:
        log.warning("OS clipboard read failed: %s", e)
    return ""

def _paste_key() -> str:
    return "command" if _get_os() == "mac" else "ctrl"

def _type_via_clipboard(text: str) -> None:
    """Paste text from clipboard — handles all Unicode, faster for long strings."""
    if _PYPERCLIP_OK:
        pyperclip.copy(text)
    else:
        _os_clipboard_set(text)
    time.sleep(_t(0.08))
    pyautogui.hotkey(_paste_key(), "v")
    time.sleep(_t(0.07))

def _type_chars_variable(text: str, base_interval: float) -> None:
    """
    Character-by-character with variable speed and unicode fallback.
    Accumulates safe chars into chunks for performance.
    """
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in _TYPEWRITE_SAFE:
                                         
            j = i + 1
            while j < len(text) and text[j] in _TYPEWRITE_SAFE:
                j += 1
            chunk = text[i:j]
            interval = base_interval + random.uniform(-0.005, 0.012)
            pyautogui.typewrite(chunk, interval=max(0.01, interval))
            i = j
        else:
                                                    
            if _PYPERCLIP_OK:
                pyperclip.copy(ch)
                pyautogui.hotkey(_paste_key(), "v")
                time.sleep(_t(0.05))
            i += 1

@_with_retry(RetryConfig(attempts=2, base_delay=0.2))
def _type(text: str, interval: float = 0.03) -> str:
    _require_pyautogui()
    text = _validate_str(text, "text", allow_empty=False)
    interval = _validate_float(interval, "interval", lo=0.005, hi=1.0, default=0.03)
    time.sleep(_t(0.25))
    if not _can_typewrite(text):
        _type_via_clipboard(text)
    else:
        _type_chars_variable(text, interval)
    snippet = text[:60] + ("…" if len(text) > 60 else "")
    log.debug("Typed: %s", snippet)
    return f"Typed: {snippet}"

def _clear_field() -> str:
    _require_pyautogui()
    sel_key = "command" if _get_os() == "mac" else "ctrl"
    pyautogui.hotkey(sel_key, "a")
    time.sleep(_t(0.08))
    pyautogui.press("delete")
    time.sleep(_t(0.05))
    log.debug("Field cleared")
    return "Field cleared"

@_with_retry(RetryConfig(attempts=2, base_delay=0.2))
def _smart_type(text: str, clear_first: bool = True) -> str:
    _require_pyautogui()
    text = _validate_str(text, "text", allow_empty=False)
    if clear_first:
        _clear_field()
        time.sleep(_t(0.12))
                                                        
    if len(text) > 15 or not _can_typewrite(text):
        _type_via_clipboard(text)
    else:
        _type_chars_variable(text, 0.04)
    snippet = text[:60] + ("…" if len(text) > 60 else "")
    log.debug("Smart-typed: %s", snippet)
    return f"Smart-typed: {snippet}"

@_with_retry(RetryConfig(attempts=2, base_delay=0.1))
def _hotkey(*keys: str) -> str:
    _require_pyautogui()
    if not keys:
        raise ValueError("hotkey requires at least one key")
    resolved = [_resolve_key(k) for k in keys]
    pyautogui.hotkey(*resolved)
    combo = "+".join(keys)
    log.debug("Hotkey: %s", combo)
    return f"Hotkey: {combo}"

@_with_retry(RetryConfig(attempts=2, base_delay=0.1))
def _press(key: str) -> str:
    _require_pyautogui()
    key = _validate_str(key, "key", allow_empty=False)
    resolved = _resolve_key(key)
    pyautogui.press(resolved)
    log.debug("Pressed: %s", resolved)
    return f"Pressed: {key}"

                                                                      



def _clipboard_get() -> str:
    if _PYPERCLIP_OK:
        return pyperclip.paste()
    return _os_clipboard_get()

def _clipboard_paste(text: str) -> str:
    text = _validate_str(text, "text")
    ok = False
    if _PYPERCLIP_OK:
        pyperclip.copy(text)
        ok = True
    else:
        ok = _os_clipboard_set(text)
    if ok and _PYAUTOGUI_OK:
        time.sleep(_t(0.1))
        pyautogui.hotkey(_paste_key(), "v")
        snippet = text[:60] + ("…" if len(text) > 60 else "")
        return f"Pasted: {snippet}"
    return "Clipboard paste failed — no pyperclip and OS fallback unavailable"

                                                                      



@_with_retry(RetryConfig(attempts=3, base_delay=0.3))
def _screenshot(save_path: str | None = None) -> str:
    _require_pyautogui()
    path = _safe_screenshot_path(save_path)
    img = pyautogui.screenshot()
    img.save(str(path), format="PNG", optimize=False)
    kb = path.stat().st_size // 1024
    log.info("Screenshot saved: %s (%d KB)", path, kb)
    return f"Screenshot saved: {path} ({kb} KB)"

@_with_retry(RetryConfig(attempts=2, base_delay=0.3))
def _screenshot_region(
    x: int,
    y: int,
    width: int,
    height: int,
    save_path: str | None = None,
) -> str:
    _require_pyautogui()
    x, y = _validate_coords(x, y)
    width = _validate_int(width, "width", lo=1, hi=_get_screen_size()[0])
    height = _validate_int(height, "height", lo=1, hi=_get_screen_size()[1])
    path = _safe_screenshot_path(save_path)
    img = pyautogui.screenshot(region=(x, y, width, height))
    img.save(str(path), format="PNG", optimize=False)
    kb = path.stat().st_size // 1024
    log.info("Region screenshot saved: %s (%d KB)", path, kb)
    return f"Region screenshot saved: {path} ({kb} KB)"

                                                                      



def _verify_focus(title: str, *, timeout: float = 1.0) -> bool:
    """
    Best-effort confirmation that a window containing `title` is now active.
    Polls until timeout. Returns True on success, False if unverifiable.
    """
    os_name = _get_os()
    deadline = time.monotonic() + timeout
    tl = title.lower()

    while time.monotonic() < deadline:
        try:
            if os_name == "linux":
                r = subprocess.run(
                    ["xdotool", "getactivewindow", "getwindowname"],
                    capture_output=True,
                    timeout=2,
                )
                if tl in r.stdout.decode(errors="replace").lower():
                    return True
            elif os_name == "mac":
                script = (
                    'tell application "System Events" to get name of front window '
                    "of (first process whose frontmost is true)"
                )
                r = subprocess.run(
                    ["osascript", "-e", script], capture_output=True, timeout=2
                )
                if tl in r.stdout.decode(errors="replace").lower():
                    return True
            elif os_name == "windows":
                r = subprocess.run(
                    [
                        "powershell",
                        "-NoProfile",
                        "-Command",
                        "[System.Windows.Forms.Form]::ActiveForm.Text",
                    ],
                    capture_output=True,
                    timeout=3,
                )
                if tl in r.stdout.decode(errors="replace").lower():
                    return True
        except Exception:
            pass
        time.sleep(0.1)
    return False

def _focus_window(title: str) -> str:
    title = _validate_str(title, "title", allow_empty=False)
    os_name = _get_os()
    log.debug("Focus window: %r [%s]", title, os_name)

    if os_name == "windows":
        try:
            script = f'(New-Object -ComObject WScript.Shell).AppActivate("{title}")'
            subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                capture_output=True,
                timeout=5,
            )
            time.sleep(_t(0.35))
            return f"Focused window: {title}"
        except Exception as e:
            return f"focus_window (Windows) failed: {e}"

    if os_name == "mac":
                                                                      
        for script in (
            f'tell application "{title}" to activate',
            (
                'tell application "System Events" to set frontmost of '
                f'(first process whose name contains "{title}") to true'
            ),
        ):
            try:
                r = subprocess.run(
                    ["osascript", "-e", script],
                    capture_output=True,
                    timeout=5,
                )
                if r.returncode == 0:
                    time.sleep(_t(0.35))
                    return f"Focused window: {title}"
            except Exception:
                continue
        return f"focus_window (macOS): could not focus '{title}'"

    if os_name == "linux":
        strategies = [
            ["wmctrl", "-a", title],
            ["xdotool", "search", "--name", title, "windowactivate", "--sync"],
            ["xdotool", "search", "--class", title, "windowactivate", "--sync"],
        ]
        for cmd in strategies:
            try:
                r = subprocess.run(cmd, capture_output=True, timeout=5)
                if r.returncode == 0:
                    time.sleep(_t(0.35))
                    confirmed = _verify_focus(title, timeout=0.6)
                    log.debug(
                        "Focus %s: %s",
                        title,
                        "confirmed" if confirmed else "unverified",
                    )
                    return f"Focused window: {title}"
            except FileNotFoundError:
                log.debug("Tool not on PATH: %s", cmd[0])
            except Exception as e:
                log.debug("Focus strategy %r failed: %s", cmd[0], e)
        return (
            f"focus_window (Linux): no strategy succeeded for '{title}'. "
            "Install wmctrl or xdotool: sudo apt-get install wmctrl xdotool"
        )

    return f"focus_window: unsupported OS '{os_name}'"

                                                                      


_SCREEN_FIND_TTL: float = 4.0                           

@_with_retry(RetryConfig(attempts=2, base_delay=0.5))
def _screen_find(description: str) -> Tuple[int, int] | None:
    description = _validate_str(description, "description", allow_empty=False)

    cache_key = f"sf:{hashlib.md5(description.encode()).hexdigest()}"
    cached = _cache.get(cache_key)
    if cached is not None:
        log.debug("screen_find cache hit: %r → %s", description, cached)
        return cached

    api_key = _get_api_key()
    if not api_key:
        log.warning("screen_find: no Gemini API key in config")
        return None

    try:
        from google import genai
        from google.genai import types as gtypes

        _require_pyautogui()
        w, h = pyautogui.size()
        img = pyautogui.screenshot()
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        client = genai.Client(api_key=api_key)
        prompt = (
            f"This is a screenshot of a {w}×{h} pixel display. "
            f"Locate the center of the UI element described as: '{description}'. "
            "Reply with ONLY two integers separated by a comma: x,y "
            "(pixel coordinates of the element center). "
            "If the element is not visible on screen, reply exactly: NOT_FOUND"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=[
                gtypes.Part.from_bytes(data=image_bytes, mime_type="image/png"),
                prompt,
            ],
        )
        text = (response.text or "").strip()
        log.debug("screen_find response: %r", text)

        if "NOT_FOUND" in text.upper():
            return None

        match = re.search(r"(\d{1,5})\s*,\s*(\d{1,5})", text)
        if match:
            rx, ry = int(match.group(1)), int(match.group(2))
            if 0 <= rx < w and 0 <= ry < h:
                result = (rx, ry)
                _cache.set(cache_key, result, ttl=_SCREEN_FIND_TTL)
                log.info("screen_find: '%s' → %s", description, result)
                return result
            log.warning(
                "screen_find: coords out of bounds (%d,%d) for %dx%d screen",
                rx,
                ry,
                w,
                h,
            )

    except Exception as e:
        log.error("screen_find failed: %s", e)

    return None

def _screen_find_any(descriptions: List[str]) -> Tuple[int, int] | None:
    """
    Try multiple descriptions in order, return first match.
    Useful for elements with varying labels across OS themes or languages.
    """
    for desc in descriptions:
        coords = _screen_find(desc)
        if coords:
            log.debug("screen_find_any matched: %r", desc)
            return coords
    return None

                                                                      



def _type_in_field(
    x: int | None,
    y: int | None,
    text: str,
    clear_first: bool = True,
) -> str:
    """Click a field at (x,y), optionally clear it, then type text."""
    if x is not None and y is not None:
        _click(x, y, "left", 1)
        time.sleep(_t(0.15))
    return _smart_type(text, clear_first=clear_first)

def _screen_type(description: str, text: str, clear_first: bool = True) -> str:
    """
    AI-find an element, click it, then type.
    Combined screen_find + click + smart_type in one atomic action.
    """
    coords = _screen_find(description)
    if not coords:
        return f"Element not found: '{description}'"
    _click(coords[0], coords[1])
    time.sleep(_t(0.2))
    return _smart_type(text, clear_first=clear_first)

def _action_chain(actions: List[dict]) -> str:
    """
    Execute a sequence of actions from a list of parameter dicts.
    Each dict uses the same schema as computer_control(parameters).
    Returns a multi-line summary of results.
    """
    results: List[str] = []
    for i, params in enumerate(actions, 1):
        if not isinstance(params, dict):
            results.append(f"[{i}] SKIP — not a dict: {params!r}")
            continue
        action = params.get("action", "")
        out = computer_control(params)
        results.append(f"[{i}] {action}: {out[:100]}")
                                              
        delay = float(params.get("chain_delay", 0.0))
        if delay > 0:
            time.sleep(delay)
    return "\n".join(results)

                                                                      



def _wait(seconds: float = 1.0) -> str:
    seconds = _validate_float(seconds, "seconds", lo=0.0, hi=30.0)
    time.sleep(seconds)
    log.debug("Waited %.2fs", seconds)
    return f"Waited {seconds:.2f}s"

                                                                      


_FIRST_NAMES = [
    "Alex",
    "Jordan",
    "Taylor",
    "Morgan",
    "Casey",
    "Riley",
    "Drew",
    "Quinn",
    "Avery",
    "Blake",
    "Cameron",
    "Dakota",
    "Emerson",
    "Finley",
    "Harper",
    "Jesse",
    "Kendall",
    "Logan",
    "Parker",
    "Peyton",
    "Reagan",
    "Reese",
    "Robin",
    "Ryan",
    "Sage",
    "Sam",
    "Skylar",
    "Spencer",
    "Sydney",
    "Terry",
]
_LAST_NAMES = [
    "Smith",
    "Johnson",
    "Williams",
    "Brown",
    "Jones",
    "Garcia",
    "Miller",
    "Davis",
    "Wilson",
    "Moore",
    "Taylor",
    "Anderson",
    "Thomas",
    "Jackson",
    "White",
    "Harris",
    "Martin",
    "Thompson",
    "Young",
    "Allen",
    "King",
    "Wright",
    "Scott",
    "Green",
    "Baker",
    "Adams",
    "Nelson",
    "Carter",
    "Mitchell",
    "Perez",
    "Roberts",
    "Turner",
    "Phillips",
    "Campbell",
]
_DOMAINS = [
    "gmail.com",
    "yahoo.com",
    "outlook.com",
    "proton.me",
    "mail.com",
    "icloud.com",
]
_STREETS = [
    "Main St",
    "Oak Ave",
    "Park Blvd",
    "Elm St",
    "Cedar Ln",
    "Maple Dr",
    "Pine Rd",
    "Lake Ct",
    "River Way",
    "Hill Rd",
    "Forest Ave",
    "Valley Rd",
    "Sunset Blvd",
    "Ocean Dr",
    "Mountain View",
]
_CITIES = [
    "New York",
    "Los Angeles",
    "Chicago",
    "Houston",
    "Phoenix",
    "Philadelphia",
    "San Antonio",
    "San Diego",
    "Dallas",
    "San Jose",
    "Austin",
    "Jacksonville",
    "San Francisco",
    "Columbus",
    "Charlotte",
    "Seattle",
    "Denver",
    "Boston",
    "Nashville",
    "Portland",
]
_STATE_MAP = {
    "New York": "NY",
    "Los Angeles": "CA",
    "Chicago": "IL",
    "Houston": "TX",
    "Phoenix": "AZ",
    "Philadelphia": "PA",
    "San Antonio": "TX",
    "San Diego": "CA",
    "Dallas": "TX",
    "San Jose": "CA",
    "Austin": "TX",
    "Jacksonville": "FL",
    "San Francisco": "CA",
    "Columbus": "OH",
    "Charlotte": "NC",
    "Seattle": "WA",
    "Denver": "CO",
    "Boston": "MA",
    "Nashville": "TN",
    "Portland": "OR",
}
_COMPANIES = [
    "Apex Corp",
    "Blue Ridge LLC",
    "NovaTech",
    "Sterling Group",
    "Pinnacle Inc",
    "Horizon Labs",
    "Summit Co",
    "Vertex Systems",
    "Bright Path",
    "Clearwater Solutions",
    "Iron Gate Industries",
]
_JOB_TITLES = [
    "Software Engineer",
    "Product Manager",
    "UX Designer",
    "Data Analyst",
    "Consultant",
    "Full-Stack Developer",
    "Solutions Architect",
    "Director",
    "Marketing Manager",
    "DevOps Engineer",
    "QA Engineer",
    "Project Manager",
]
_COUNTRIES = [
    "United States",
    "United Kingdom",
    "Canada",
    "Australia",
    "Germany",
    "France",
    "Japan",
    "Singapore",
    "Netherlands",
    "Sweden",
]
_HOBBIES = [
    "photography",
    "hiking",
    "reading",
    "cooking",
    "gaming",
    "cycling",
    "travelling",
    "painting",
    "music production",
    "yoga",
]

_session_identity: Dict[str, str] = {}
_identity_lock = threading.Lock()

def _session_value(key: str, generator: Callable[[], str]) -> str:
    """Return a cached session value, generating it once if missing."""
    with _identity_lock:
        if key not in _session_identity:
            _session_identity[key] = generator()
        return _session_identity[key]

def _reset_session_identity() -> None:
    """Clear session identity pool — call before starting a new form fill."""
    with _identity_lock:
        _session_identity.clear()
    log.info("Session identity pool cleared")

def _luhn_complete(partial: str) -> str:
    """Append Luhn checksum digit to a partial card number."""
    total = 0
    for i, ch in enumerate(reversed(partial)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    check = (10 - (total % 10)) % 10
    return partial + str(check)

def _random_data(data_type: str) -> str:                                           
    """
    Generate realistic fake data for the given type.
    Values are consistent within a session (same name / email everywhere).

    Supported types:
      first_name, last_name, name, email, username, password,
      phone, birthday / dob / date_of_birth, address, zip_code,
      city, state, country, company, job_title, gender,
      card_number / credit_card, cvv / cvc, expiry,
      url / website, bio / about, age, ssn, ip_address,
      color_hex, language, timezone, user_agent
    """
    dt = data_type.lower().strip()

    if dt == "first_name":
        return _session_value("first_name", lambda: random.choice(_FIRST_NAMES))

    if dt == "last_name":
        return _session_value("last_name", lambda: random.choice(_LAST_NAMES))

    if dt == "name":
        fn = _session_value("first_name", lambda: random.choice(_FIRST_NAMES))
        ln = _session_value("last_name", lambda: random.choice(_LAST_NAMES))
        return f"{fn} {ln}"

    if dt == "email":
        fn = _session_value("first_name", lambda: random.choice(_FIRST_NAMES)).lower()
        ln = _session_value("last_name", lambda: random.choice(_LAST_NAMES)).lower()
        num = _session_value("email_num", lambda: str(random.randint(10, 999)))
        dom = _session_value("email_dom", lambda: random.choice(_DOMAINS))
        return f"{fn}.{ln}{num}@{dom}"

    if dt == "username":
        fn = _session_value("first_name", lambda: random.choice(_FIRST_NAMES)).lower()
        num = _session_value("uname_num", lambda: str(random.randint(100, 9999)))
        return f"{fn}{num}"

    if dt == "password":

        def _gen_pw() -> str:
            chars = string.ascii_letters + string.digits + "!@#$%^&*()"
            raw = (
                random.choice(string.ascii_uppercase)
                + random.choice(string.ascii_lowercase)
                + random.choice(string.digits)
                + random.choice("!@#$%")
                + "".join(random.choices(chars, k=9))
            )
            return "".join(random.sample(raw, len(raw)))

        return _session_value("password", _gen_pw)

    if dt == "phone":

        def _gen_phone() -> str:
            area = random.randint(201, 989)
            exch = random.randint(200, 989)
            sub = random.randint(1000, 9999)
            return f"+1{area}{exch}{sub}"

        return _session_value("phone", _gen_phone)

    if dt in ("birthday", "dob", "date_of_birth"):

        def _gen_dob() -> str:
            y = random.randint(1975, 2001)
            m = random.randint(1, 12)
            d = random.randint(1, 28)
            return f"{m:02d}/{d:02d}/{y}"

        return _session_value("birthday", _gen_dob)

    if dt == "age":
        dob = _session_value("birthday", lambda: _random_data("birthday"))
        try:
            year = int(dob.split("/")[-1])
            return str(time.localtime().tm_year - year)
        except Exception:
            return str(random.randint(22, 45))

    if dt == "address":
        num = _session_value("addr_num", lambda: str(random.randint(100, 9999)))
        street = _session_value("addr_street", lambda: random.choice(_STREETS))
        return f"{num} {street}"

    if dt == "zip_code":
        return _session_value("zip_code", lambda: str(random.randint(10000, 99999)))

    if dt == "city":
        return _session_value("city", lambda: random.choice(_CITIES))

    if dt == "state":
        city = _session_value("city", lambda: random.choice(_CITIES))
        return _STATE_MAP.get(city, "CA")

    if dt == "country":
        return _session_value("country", lambda: random.choice(_COUNTRIES))

    if dt == "company":
        return _session_value("company", lambda: random.choice(_COMPANIES))

    if dt == "job_title":
        return _session_value("job_title", lambda: random.choice(_JOB_TITLES))

    if dt == "gender":
        return _session_value(
            "gender", lambda: random.choice(["Male", "Female", "Non-binary"])
        )

    if dt in ("card_number", "credit_card"):

        def _gen_card() -> str:
            prefix = random.choice(["4", "51", "52", "53", "54", "55"])
            length = 16
            partial = prefix + "".join(
                random.choices(string.digits, k=length - len(prefix) - 1)
            )
            return _luhn_complete(partial)

        return _session_value("card_number", _gen_card)

    if dt in ("cvv", "cvc"):
        return _session_value("cvv", lambda: str(random.randint(100, 999)))

    if dt == "expiry":

        def _gen_expiry() -> str:
            m = random.randint(1, 12)
            yy = (time.localtime().tm_year % 100) + random.randint(1, 5)
            return f"{m:02d}/{yy:02d}"

        return _session_value("expiry", _gen_expiry)

    if dt in ("url", "website"):
        fn = _session_value("first_name", lambda: random.choice(_FIRST_NAMES)).lower()
        ln = _session_value("last_name", lambda: random.choice(_LAST_NAMES)).lower()
        tld = random.choice([".com", ".net", ".io", ".co", ".dev"])
        return f"https://www.{fn}{ln}{tld}"

    if dt in ("bio", "about"):
        fn = _session_value("first_name", lambda: random.choice(_FIRST_NAMES))
        job = _session_value("job_title", lambda: random.choice(_JOB_TITLES))
        city = _session_value("city", lambda: random.choice(_CITIES))
        hobby = _session_value("hobby", lambda: random.choice(_HOBBIES))
        return (
            f"Hi, I'm {fn} — a {job} based in {city}. "
            f"Outside of work I enjoy {hobby} and learning new things."
        )

    if dt == "ssn":

        def _gen_ssn() -> str:
            area = random.randint(100, 899)
            group = random.randint(10, 99)
            seq = random.randint(1000, 9999)
            return f"{area:03d}-{group:02d}-{seq:04d}"

        return _session_value("ssn", _gen_ssn)

    if dt == "ip_address":
        return _session_value(
            "ip_address",
            lambda: ".".join(str(random.randint(1, 254)) for _ in range(4)),
        )

    if dt == "color_hex":
        return _session_value(
            "color_hex",
            lambda: "#" + "".join(random.choices("0123456789ABCDEF", k=6)),
        )

    if dt == "language":
        return _session_value(
            "language",
            lambda: random.choice(
                ["English", "Spanish", "French", "German", "Japanese"]
            ),
        )

    if dt == "timezone":
        return _session_value(
            "timezone",
            lambda: random.choice(
                [
                    "America/New_York",
                    "America/Los_Angeles",
                    "America/Chicago",
                    "Europe/London",
                    "Europe/Berlin",
                    "Asia/Tokyo",
                    "Asia/Singapore",
                ]
            ),
        )

    if dt == "user_agent":
        return _session_value(
            "user_agent",
            lambda: random.choice(
                [
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 "
                    "(KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
                    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
                ]
            ),
        )

    log.warning(
        "Unknown random_data type: %r — returning generic placeholder", data_type
    )
    return f"random_{data_type}_{random.randint(1000, 9999)}"

                                                                      



def computer_control(
    parameters: dict,
    response: Any = None,
    player: Any = None,
    session_memory: Any = None,
) -> str:
    """
    Unified dispatcher for all desktop automation actions.

    ──────────────────────────────────────────────────────
    PARAMETERS  (all optional unless noted)
    ──────────────────────────────────────────────────────
    action          (required) — one of the actions listed below
    text            — text to type or paste
    x, y            — screen coordinates (clamped to screen bounds)
    x1,y1,x2,y2    — drag start / end coordinates
    width, height   — region dimensions for screenshot_region
    button          — 'left' | 'right' | 'middle'  (default: left)
    keys            — hotkey string e.g. 'ctrl+c'
    key             — single key name e.g. 'enter'
    direction       — 'up' | 'down' | 'left' | 'right'
    amount          — scroll amount (default: 3)
    seconds         — wait duration (capped at 30 s)
    interval        — per-key typing interval (default: 0.03 s)
    duration        — mouse move / drag duration in seconds
    title           — window title fragment for focus_window
    description     — natural-language element for screen_find / click
    descriptions    — list of descriptions for screen_find_any
    type            — data type for random_data
    field           — memory field name for user_data
    clear_first     — bool, clear field before typing (default: true)
    path            — save path for screenshot (must be under home dir)
    human           — bool, use Bézier mouse movement (default: true)
    reset_identity  — bool, clear session identity pool before random_data
    actions         — list of param dicts for action_chain
    move_duration   — seconds for cursor travel before a click (default: 0.25)
    chain_delay     — seconds between steps inside action_chain

    ──────────────────────────────────────────────────────
    ACTIONS
    ──────────────────────────────────────────────────────
    Mouse:
      click           left click at (x,y) or current cursor position
      double_click    double left click
      right_click     right click
      middle_click    middle / scroll-wheel click
      move            move cursor (Bézier curve when human=true)
      hover           move to (x,y) and pause
      drag            Bézier click-drag between (x1,y1) and (x2,y2)
      scroll          scroll wheel in a direction

    Keyboard:
      type            type text at cursor (unicode-safe)
      smart_type      clear field then type (clipboard-backed)
      hotkey          key combination e.g. ctrl+c
      press           single key press
      clear_field     select-all + delete

    Clipboard:
      copy            read clipboard content
      paste           write text to clipboard and paste it

    Screen:
      screenshot      full-screen PNG (safe path only)
      screenshot_region  region PNG at (x,y,width,height)

    System:
      wait            sleep N seconds (max 30)
      focus_window    bring a window to the foreground

    AI Vision:
      screen_find     return x,y of element or NOT_FOUND
      screen_click    find element then click it
      screen_type     find element, click it, then type text

    Composite:
      type_in_field   click (x,y) + clear + smart_type
      action_chain    run a list of action dicts sequentially

    Data:
      random_data     generate realistic fake form data (25+ types)
      user_data       pull real data from long-term memory

    Meta:
      health_check    full dependency + system readiness report
      calibrate       benchmark + adjust timing multiplier
      deps            one-line dependency status
      metrics         performance metrics JSON
      reset_identity  clear session identity pool
    ──────────────────────────────────────────────────────
    """
    params = parameters or {}
    action = _validate_str(params.get("action", ""), "action").lower().strip()

    if not action:
        return "Error: 'action' key is required in parameters."

    t0 = time.monotonic()
    with suppress(Exception):
        if player:
            player.write_log(f"[Computer] {action}")

    log.info("▶ %s  %s", action, {k: v for k, v in params.items() if k != "action"})

    output = ""
    success = True

    try:
                                                                 
        if action in ("click", "left_click"):
            output = _click(
                params.get("x"),
                params.get("y"),
                "left",
                1,
                move_duration=float(params.get("move_duration", 0.25)),
            )

        elif action == "double_click":
            output = _click(params.get("x"), params.get("y"), "left", 2)

        elif action == "right_click":
            output = _click(params.get("x"), params.get("y"), "right", 1)

        elif action == "middle_click":
            output = _click(params.get("x"), params.get("y"), "middle", 1)

        elif action == "move":
            output = _move(
                int(params.get("x", 0)),
                int(params.get("y", 0)),
                duration=float(params.get("duration", 0.3)),
                human=bool(params.get("human", True)),
            )

        elif action == "hover":
            output = _hover(
                int(params.get("x", 0)),
                int(params.get("y", 0)),
                duration=float(params.get("duration", 0.5)),
            )

        elif action == "drag":
            output = _drag(
                int(params.get("x1", 0)),
                int(params.get("y1", 0)),
                int(params.get("x2", 0)),
                int(params.get("y2", 0)),
                duration=float(params.get("duration", 0.6)),
            )

        elif action == "scroll":
            output = _scroll(
                direction=str(params.get("direction", "down")),
                amount=int(params.get("amount", 3)),
            )

        elif action == "type":
            output = _type(
                params.get("text", ""),
                interval=float(params.get("interval", 0.03)),
            )

        elif action == "smart_type":
            output = _smart_type(
                params.get("text", ""),
                clear_first=bool(params.get("clear_first", True)),
            )

        elif action == "hotkey":
            raw = params.get("keys", "")
            keys = (
                [k.strip() for k in raw.split("+")]
                if isinstance(raw, str)
                else list(raw)
            )
            output = _hotkey(*keys)

        elif action == "press":
            output = _press(str(params.get("key", "enter")))

        elif action == "clear_field":
            output = _clear_field()

        elif action == "copy":
            output = _clipboard_get()

        elif action == "paste":
            output = _clipboard_paste(params.get("text", ""))

        elif action == "screenshot":
            output = _screenshot(params.get("path"))

        elif action == "screenshot_region":
            output = _screenshot_region(
                int(params.get("x", 0)),
                int(params.get("y", 0)),
                int(params.get("width", 400)),
                int(params.get("height", 300)),
                params.get("path"),
            )

        elif action == "wait":
            output = _wait(float(params.get("seconds", 1.0)))

        elif action == "focus_window":
            output = _focus_window(str(params.get("title", "")))

        elif action == "screen_find":
            coords = _screen_find(str(params.get("description", "")))
            output = f"{coords[0]},{coords[1]}" if coords else "NOT_FOUND"

        elif action == "screen_click":
            desc = str(params.get("description", ""))
            coords = _screen_find(desc)
            if coords:
                time.sleep(_t(0.2))
                _click(x=coords[0], y=coords[1])
                output = f"Clicked '{desc}' at {coords}"
            else:
                output = f"Element not found on screen: '{desc}'"
                success = False

        elif action == "screen_type":
            output = _screen_type(
                str(params.get("description", "")),
                str(params.get("text", "")),
                clear_first=bool(params.get("clear_first", True)),
            )

        elif action == "type_in_field":
            output = _type_in_field(
                params.get("x"),
                params.get("y"),
                str(params.get("text", "")),
                clear_first=bool(params.get("clear_first", True)),
            )

        elif action == "action_chain":
            chain = params.get("actions", [])
            if not isinstance(chain, list):
                raise ValueError("'actions' must be a list of parameter dicts")
            output = _action_chain(chain)

        elif action == "random_data":
            if params.get("reset_identity"):
                _reset_session_identity()
            dt = str(params.get("type", "name"))
            result = _random_data(dt)
            log.info("🎲 random %s → %s", dt, result)
            output = result

        elif action == "user_data":
            field = str(params.get("field", "name"))
            profile = _user_profile()
            value = profile.get(field, "")
            if not value:
                value = _random_data(field)
                log.warning("No '%s' in memory, using random: %s", field, value)
            output = value

        elif action == "health_check":
            output = _health_check()

        elif action == "calibrate":
            output = _calibrate()

        elif action == "deps":
            d = _check_deps()
            output = "  ".join(f"{'✓' if v else '✗'} {k}" for k, v in d.items())

        elif action == "metrics":
            _metrics.flush()
            output = json.dumps(_metrics.summary(), indent=2)

        elif action == "reset_identity":
            _reset_session_identity()
            output = "Session identity pool cleared"

        else:
            output = f"Unknown action: '{action}'"
            success = False
            log.warning("Unknown action: %r", action)

    except (ValueError, RuntimeError) as exc:
        output = f"Error in '{action}': {exc}"
        success = False
        log.error("%s", output)

    except Exception as exc:
        output = f"Unexpected error in '{action}': {exc}"
        success = False
        log.exception("Unhandled exception in action '%s'", action)

    elapsed = time.monotonic() - t0
    _metrics.record(action, elapsed, success)

    result = ActionResult(
        action=action,
        success=success,
        output=output,
        elapsed=elapsed,
    )
    _audit(result, params)

    level = log.info if success else log.error
    level(
        "%s %s (%.0f ms): %s",
        "✓" if success else "✗",
        action,
        elapsed * 1_000,
        output[:120],
    )

    return output
