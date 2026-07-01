import os
import re

utils_code = """import functools
import json
import logging
import logging.handlers
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

_LOGGER_NAME = "INDRA"

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

def build_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(threadName)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(fmt)
    logger.addHandler(console_handler)
    try:
        log_dir = _get_base_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / "INDRA.log",
            maxBytes=2 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception as exc:
        logger.warning("Could not attach file log handler: %s", exc)
    logger.propagate = False
    return logger

log = build_logger()

class Config:
    _instance: Optional["Config"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}
        self._load()

    @classmethod
    def instance(cls) -> "Config":
        with cls._lock:
            if cls._instance is None:
                cls._instance = Config()
            return cls._instance

    def _config_path(self) -> Path:
        return _get_base_dir() / "config" / "settings.json"

    def _load(self) -> None:
        path = self._config_path()
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if isinstance(user_cfg, dict):
                self._data.update(user_cfg)
        except Exception as exc:
            log.error("Failed to load config from %s: %s", path, exc)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

@dataclass
class ActionRecord:
    action: str
    success: bool
    elapsed_seconds: float
    timestamp: float = field(default_factory=time.time)

class StatsTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._history: list[ActionRecord] = []
        self._success_counts: dict[str, int] = {}
        self._failure_counts: dict[str, int] = {}

    def record(self, action: str, elapsed: float, success: bool) -> None:
        with self._lock:
            self._history.append(ActionRecord(action, success, elapsed))
            if success:
                self._success_counts[action] = self._success_counts.get(action, 0) + 1
            else:
                self._failure_counts[action] = self._failure_counts.get(action, 0) + 1

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total = len(self._history)
            successes = sum(1 for r in self._history if r.success)
            avg_ms = (
                sum(r.elapsed_seconds for r in self._history) / total * 1000
                if total
                else 0.0
            )
            return {
                "total_calls": total,
                "successes": successes,
                "failures": total - successes,
                "success_rate": round(successes / total, 3) if total else None,
                "avg_duration_ms": round(avg_ms, 2),
                "top_actions": sorted(
                    self._success_counts.items(), key=lambda kv: -kv[1]
                )[:10],
            }

STATS = StatsTracker()

_ui_lock = threading.Lock()
def synchronized_ui(func: Callable) -> Callable:
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _ui_lock:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start
                STATS.record(func.__name__, elapsed, success=True)
                log.debug("%s completed in %.1fms", func.__name__, elapsed * 1000)
                return result
            except Exception as exc:
                elapsed = time.perf_counter() - start
                STATS.record(func.__name__, elapsed, success=False)
                log.error(
                    "%s failed after %.1fms: %s", func.__name__, elapsed * 1000, exc
                )
                raise
    return wrapper

_gemini_client_lock = threading.Lock()
_gemini_client = None

def get_api_key() -> str:
    path = _get_base_dir() / "config" / "api_keys.json"
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]

def get_gemini_client():
    global _gemini_client
    with _gemini_client_lock:
        if _gemini_client is not None:
            return _gemini_client
        from google import genai as _genai
        _gemini_client = _genai.Client(api_key=get_api_key())
        return _gemini_client
"""

with open("d:/PROJECTS/AI/core/utils.py", "w", encoding="utf-8") as f:
    f.write(utils_code)

def refactor_file(path):
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    if "def _build_logger()" in content or "class StatsTracker:" in content or "class Config:" in content:

                                
        content = re.sub(r'def _build_logger\(\) -> logging\.Logger:.*?log = _build_logger\(\)', '', content, flags=re.DOTALL)
        content = re.sub(r'def _build_logger\(\).*?log = _build_logger\(\)', '', content, flags=re.DOTALL)

        content = re.sub(r'class Config:.*?def get\(self, key: str, default: Any = None\) -> Any:\s*return self._data\.get\(key, default\)', '', content, flags=re.DOTALL)

        content = re.sub(r'@dataclass\s*class ActionRecord:.*?STATS = StatsTracker\(\)', '', content, flags=re.DOTALL)
        content = re.sub(r'class StatsTracker:.*?STATS = StatsTracker\(\)', '', content, flags=re.DOTALL)

        content = re.sub(r'def synchronized_ui\(func: Callable\) -> Callable:.*?return wrapper', '', content, flags=re.DOTALL)

        content = re.sub(r'def _get_gemini_client\(\).*?return _gemini_client', '', content, flags=re.DOTALL)

        import_stmt = "from core.utils import log, Config, STATS, synchronized_ui, get_gemini_client\n"
        content = import_stmt + content

        content = content.replace("_get_gemini_client()", "get_gemini_client()")
        
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        print(f"Refactored {path}")

for root, _, files in os.walk("d:/PROJECTS/AI/actions"):
    for file in files:
        if file.endswith(".py"):
            refactor_file(os.path.join(root, file))

