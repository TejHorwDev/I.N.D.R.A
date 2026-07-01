import asyncio
import os
import re
import sys
import json
import threading
import traceback
from datetime import datetime
from pathlib import Path

# pylint: disable=all

import hashlib



# --- Frozen / noconsole stdout guard ---
if getattr(sys, "frozen", False):
    _devnull = open(os.devnull, "w")
    sys.stdout = _devnull
    sys.stderr = _devnull
    sys.stdin = open(os.devnull, "r")

    # Suppress ALL console windows from any subprocess spawned by the frozen app
    import subprocess as _sp
    _orig_popen = _sp.Popen.__init__
    def _silent_popen(self, *args, **kwargs):
        kwargs.setdefault("creationflags", 0)
        kwargs["creationflags"] |= 0x08000000  # CREATE_NO_WINDOW
        _orig_popen(self, *args, **kwargs)
    _sp.Popen.__init__ = _silent_popen

os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "1"
os.environ["QT_LOGGING_RULES"] = "qt.qpa.window=false;qt.text.font.*=false"
os.environ["QT_OPENGL"] = "desktop" # Force hardware acceleration to prevent software rendering CPU spike
os.environ["QT_SCALE_FACTOR"] = "1"

# Elevate process priority to bypass Windows background app throttling (fixes 5s audio lag in --noconsole)
import psutil
try:
    psutil.Process(os.getpid()).nice(psutil.HIGH_PRIORITY_CLASS)
except Exception:
    pass

import sounddevice as sd
from google import genai
from google.genai import types

from actions.browser_control import browser_control
from actions.code_helper import code_helper
from actions.computer_control import computer_control
from actions.computer_settings import computer_settings
from actions.desktop import desktop_control
from actions.dev_agent import dev_agent
from actions.file_controller import file_controller
from actions.file_processor import file_processor
from actions.flight_finder import flight_finder
from actions.game_updater import game_updater
from actions.open_app import open_app
from actions.reminder import reminder
from actions.screen_processor import screen_process
from actions.send_message import send_message
from actions.weather_report import weather_action
from actions.web_search import web_search as web_search_action
from actions.youtube_video import youtube_video
from actions.system_monitor import system_monitor
from actions.media_control import media_control
from actions.autopilot import autopilot
from actions.clipboard_tool import clipboard_tool
from actions.window_controller import window_controller
from actions.memory_manager import memory_manager as db_memory_manager
from actions.intelligence_agent import intelligence_agent
from actions.system_diagnostics import system_diagnostics
from actions.email_agent import email_agent
from actions.camera_vision import camera_vision
from actions.document_maker import document_maker
from actions.image_editor import image_editor
from actions.terminal_controller import terminal_controller
from actions.spotify_controller import spotify_controller
from actions.agent_cron import agent_cron
from actions.python_executor import python_executor
from actions.network_scanner import network_scanner
from memory.memory_manager import (format_memory_for_prompt, load_memory,
                                   update_memory)
from ui import INDRAUI


def get_base_dir():
    """Source directory for read-only bundled assets."""
    if getattr(sys, "frozen", False):
        # sys._MEIPASS = the temp folder where PyInstaller extracts bundled data
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    return Path(__file__).resolve().parent


def get_user_data_dir():
    """Writable persistent user-data directory (config, memory, logs)."""
    if getattr(sys, "frozen", False):
        appdata = Path(os.environ.get("APPDATA", Path.home()))
        user_dir = appdata / "INDRA"
        user_dir.mkdir(parents=True, exist_ok=True)
        return user_dir
    return Path(__file__).resolve().parent


BASE_DIR = get_base_dir()
USER_DIR = get_user_data_dir()

# On first frozen run, copy bundled config to user dir if it doesn't exist yet
if getattr(sys, "frozen", False):
    _bundled_cfg = BASE_DIR / "config" / "api_keys.json"
    _user_cfg = USER_DIR / "config" / "api_keys.json"
    if _bundled_cfg.exists() and not _user_cfg.exists():
        _user_cfg.parent.mkdir(parents=True, exist_ok=True)
        import shutil as _shutil
        _shutil.copy2(_bundled_cfg, _user_cfg)

API_CONFIG_PATH = USER_DIR / "config" / "api_keys.json"
PROMPT_PATH = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL = "models/gemini-2.5-flash-native-audio-preview-12-2025"
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024
# Larger playback blocksize = fewer underruns = smoother voice
_PLAY_BLOCKSIZE = 4096   # ~170ms per block at 24 kHz — smooth and stable
_PLAY_BUFFER_SEC = 0.3  # Pre-fill 300ms of audio before starting playback


def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


def _load_system_prompt() -> str:
    try:
        return PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        return (
            "You are INDRA, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )


_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)


def _clean_transcript(text: str) -> str:
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


TOOL_DECLARATIONS = [
    {
        "name": "game_scanner",
        "description": "Scans the system for installed games via Registry and common game directories.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "open_api_settings",
        "description": "Opens the settings page for the user to insert optional API keys for ElevenLabs, Vision, and OpenWeather.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        },
    },
    {
        "name": "open_app",
        "description": (
            "Opens any application on the computer. "
            "Use this whenever the user asks to open, launch, or start any app, "
            "website, or program. Always call this tool — never just say you opened it."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')",
                }
            },
            "required": ["app_name"],
        },
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {"type": "STRING", "description": "Search query"},
                "mode": {
                    "type": "STRING",
                    "description": "search (default) or compare",
                },
                "items": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Items to compare",
                },
                "aspect": {"type": "STRING", "description": "price | specs | reviews"},
            },
            "required": ["query"],
        },
    },
    {
        "name": "weather_report",
        "description": "Gives the weather report to user",
        "parameters": {
            "type": "OBJECT",
            "properties": {"city": {"type": "STRING", "description": "City name"}},
            "required": ["city"],
        },
    },
    {
        "name": "send_message",
        "description": "Sends a text message via WhatsApp, Telegram, or other messaging platform.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver": {"type": "STRING", "description": "Recipient contact name"},
                "message_text": {
                    "type": "STRING",
                    "description": "The message to send",
                },
                "platform": {
                    "type": "STRING",
                    "description": "Platform: WhatsApp, Telegram, etc.",
                },
            },
            "required": ["receiver", "message_text", "platform"],
        },
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder using Task Scheduler.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date": {"type": "STRING", "description": "Date in YYYY-MM-DD format"},
                "time": {"type": "STRING", "description": "Time in HH:MM format (24h)"},
                "message": {"type": "STRING", "description": "Reminder message text"},
            },
            "required": ["date", "time", "message"],
        },
    },
    {
        "name": "youtube_video",
        "description": (
            "Controls YouTube. Use for: playing videos, summarizing a video's content, "
            "getting video info, or showing trending videos."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "play | summarize | get_info | trending (default: play)",
                },
                "query": {
                    "type": "STRING",
                    "description": "Search query for play action",
                },
                "save": {
                    "type": "BOOLEAN",
                    "description": "Save summary to Notepad (summarize only)",
                },
                "region": {
                    "type": "STRING",
                    "description": "Country code for trending e.g. TR, US",
                },
                "url": {
                    "type": "STRING",
                    "description": "Video URL for get_info action",
                },
            },
            "required": [],
        },
    },
    {
        "name": "screen_process",
        "description": (
            "Captures and analyzes the screen or webcam image. "
            "CRITICAL WEBCAM RULE: If the user asks 'what am I holding', 'what is this', 'look at me', or anything referencing the physical world or webcam, YOU ABSOLUTELY MUST USE THIS TOOL with angle='camera'. DO NOT USE AUTOPILOT! "
            "If you need to click, type, or interact with a visual element on the computer screen, DO NOT use this tool! "
            "Instead, immediately call the `autopilot` tool which handles the visual search and interaction automatically."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {
                    "type": "STRING",
                    "description": "'screen' to capture display, 'camera' for webcam. Default: 'screen'",
                },
                "text": {
                    "type": "STRING",
                    "description": "The question or instruction about the captured image",
                },
            },
            "required": ["text"],
        },
    },
    {
        "name": "computer_settings",
        "description": (
            "Controls the computer: volume, brightness, window management, keyboard shortcuts, "
            "typing text on screen, closing apps, fullscreen, dark mode, WiFi, restart, shutdown, "
            "scrolling, tab management, zoom, screenshots, lock screen, refresh/reload page. "
            "Use for ANY single computer control command."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "The action to perform"},
                "description": {
                    "type": "STRING",
                    "description": "Natural language description of what to do",
                },
                "value": {
                    "type": "STRING",
                    "description": "Optional value: volume level, text to type, etc.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "browser_control",
        "description": (
            "Controls any web browser. Use for: opening websites, searching the web, "
            "clicking elements, filling forms, scrolling, screenshots, navigation, any web-based task. "
            "Always pass the 'browser' parameter when the user specifies a browser (e.g. 'open in Edge', "
            "'use Firefox', 'open Chrome'). Multiple browsers can run simultaneously."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all",
                },
                "browser": {
                    "type": "STRING",
                    "description": "Target browser: chrome | edge | firefox | opera | operagx | brave | vivaldi | safari. Omit to use the currently active browser.",
                },
                "url": {
                    "type": "STRING",
                    "description": "URL for go_to / new_tab action",
                },
                "query": {
                    "type": "STRING",
                    "description": "Search query for search action",
                },
                "engine": {
                    "type": "STRING",
                    "description": "Search engine: google | bing | duckduckgo | yandex (default: google)",
                },
                "selector": {
                    "type": "STRING",
                    "description": "CSS selector for click/type",
                },
                "text": {"type": "STRING", "description": "Text to click or type"},
                "description": {
                    "type": "STRING",
                    "description": "Element description for smart_click/smart_type",
                },
                "direction": {"type": "STRING", "description": "up | down for scroll"},
                "amount": {
                    "type": "INTEGER",
                    "description": "Scroll amount in pixels (default: 500)",
                },
                "key": {
                    "type": "STRING",
                    "description": "Key name for press action (e.g. Enter, Escape, F5)",
                },
                "path": {"type": "STRING", "description": "Save path for screenshot"},
                "incognito": {
                    "type": "BOOLEAN",
                    "description": "Open in private/incognito mode",
                },
                "clear_first": {
                    "type": "BOOLEAN",
                    "description": "Clear field before typing (default: true)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "file_controller",
        "description": "Manages files and folders: list, create, delete, move, copy, rename, read, write, find, disk usage.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info",
                },
                "path": {
                    "type": "STRING",
                    "description": "File/folder path or shortcut: desktop, downloads, documents, home",
                },
                "destination": {
                    "type": "STRING",
                    "description": "Destination path for move/copy",
                },
                "new_name": {"type": "STRING", "description": "New name for rename"},
                "content": {
                    "type": "STRING",
                    "description": "Content for create_file/write",
                },
                "name": {"type": "STRING", "description": "File name to search for"},
                "extension": {
                    "type": "STRING",
                    "description": "File extension to search (e.g. .pdf)",
                },
                "count": {
                    "type": "INTEGER",
                    "description": "Number of results for largest",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "desktop_control",
        "description": "Controls the desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task",
                },
                "path": {"type": "STRING", "description": "Image path for wallpaper"},
                "url": {"type": "STRING", "description": "Image URL for wallpaper_url"},
                "mode": {
                    "type": "STRING",
                    "description": "by_type or by_date for organize",
                },
                "task": {
                    "type": "STRING",
                    "description": "Natural language desktop task",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code files.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "write | edit | explain | run | build | auto (default: auto)",
                },
                "description": {
                    "type": "STRING",
                    "description": "What the code should do or what change to make",
                },
                "language": {
                    "type": "STRING",
                    "description": "Programming language (default: python)",
                },
                "output_path": {
                    "type": "STRING",
                    "description": "Where to save the file",
                },
                "file_path": {
                    "type": "STRING",
                    "description": "Path to existing file for edit/explain/run/build",
                },
                "code": {
                    "type": "STRING",
                    "description": "Raw code string for explain",
                },
                "args": {
                    "type": "STRING",
                    "description": "CLI arguments for run/build",
                },
                "timeout": {
                    "type": "INTEGER",
                    "description": "Execution timeout in seconds (default: 30)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "dev_agent",
        "description": "Builds complete multi-file projects from scratch: plans, writes files, installs deps, opens VSCode, runs and fixes errors.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description": {
                    "type": "STRING",
                    "description": "What the project should do",
                },
                "language": {
                    "type": "STRING",
                    "description": "Programming language (default: python)",
                },
                "project_name": {
                    "type": "STRING",
                    "description": "Optional project folder name",
                },
                "timeout": {
                    "type": "INTEGER",
                    "description": "Run timeout in seconds (default: 30)",
                },
            },
            "required": ["description"],
        },
    },
    {
        "name": "computer_control",
        "description": "Direct computer control (blind execution). CRITICAL: DO NOT USE this tool if you need to visually find something on the screen. If the user asks you to click a specific icon, app, or UI element, use the 'autopilot' tool instead!",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data",
                },
                "text": {"type": "STRING", "description": "Text to type or paste"},
                "x": {"type": "INTEGER", "description": "X coordinate"},
                "y": {"type": "INTEGER", "description": "Y coordinate"},
                "keys": {
                    "type": "STRING",
                    "description": "Key combination e.g. 'ctrl+c'",
                },
                "key": {"type": "STRING", "description": "Single key e.g. 'enter'"},
                "direction": {
                    "type": "STRING",
                    "description": "up | down | left | right",
                },
                "amount": {
                    "type": "INTEGER",
                    "description": "Scroll amount (default: 3)",
                },
                "seconds": {"type": "NUMBER", "description": "Seconds to wait"},
                "title": {
                    "type": "STRING",
                    "description": "Window title for focus_window",
                },
                "description": {
                    "type": "STRING",
                    "description": "Element description for screen_find/screen_click",
                },
                "type": {"type": "STRING", "description": "Data type for random_data"},
                "field": {
                    "type": "STRING",
                    "description": "Field for user_data: name|email|city",
                },
                "clear_first": {
                    "type": "BOOLEAN",
                    "description": "Clear field before typing (default: true)",
                },
                "path": {"type": "STRING", "description": "Save path for screenshot"},
            },
            "required": ["action"],
        },
    },
    {
        "name": "game_updater",
        "description": (
            "THE ONLY tool for ANY Steam or Epic Games request. "
            "Use for: installing, downloading, updating games, listing installed games, "
            "checking download status, scheduling updates. "
            "ALWAYS call directly for any Steam/Epic/game request. "
            "NEVER use browser_control or web_search for Steam/Epic."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status (default: update)",
                },
                "platform": {
                    "type": "STRING",
                    "description": "steam | epic | both (default: both)",
                },
                "game_name": {
                    "type": "STRING",
                    "description": "Game name (partial match supported)",
                },
                "app_id": {
                    "type": "STRING",
                    "description": "Steam AppID for install (optional)",
                },
                "hour": {
                    "type": "INTEGER",
                    "description": "Hour for scheduled update 0-23 (default: 3)",
                },
                "minute": {
                    "type": "INTEGER",
                    "description": "Minute for scheduled update 0-59 (default: 0)",
                },
                "shutdown_when_done": {
                    "type": "BOOLEAN",
                    "description": "Shut down PC when download finishes",
                },
            },
            "required": [],
        },
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights and speaks the best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin": {
                    "type": "STRING",
                    "description": "Departure city or airport code",
                },
                "destination": {
                    "type": "STRING",
                    "description": "Arrival city or airport code",
                },
                "date": {
                    "type": "STRING",
                    "description": "Departure date (any format)",
                },
                "return_date": {
                    "type": "STRING",
                    "description": "Return date for round trips",
                },
                "passengers": {
                    "type": "INTEGER",
                    "description": "Number of passengers (default: 1)",
                },
                "cabin": {
                    "type": "STRING",
                    "description": "economy | premium | business | first",
                },
                "save": {"type": "BOOLEAN", "description": "Save results to Notepad"},
            },
            "required": ["origin", "destination", "date"],
        },
    },

    {
        "name": "file_processor",
        "description": (
            "Processes any file that the user has uploaded or dropped onto the interface. "
            "Use this when the user refers to an uploaded file and wants an action on it. "
            "Supports: images (describe/ocr/resize/compress/convert), "
            "PDFs (summarize/extract_text/to_word), "
            "Word docs & text files (summarize/fix/reformat/translate), "
            "CSV/Excel (analyze/stats/filter/sort/convert), "
            "JSON/XML (validate/format/analyze), "
            "code files (explain/review/fix/optimize/run/document/test), "
            "audio (transcribe/trim/convert/info), "
            "video (trim/extract_audio/extract_frame/compress/transcribe/info), "
            "archives (list/extract), "
            "presentations (summarize/extract_text). "
            "ALWAYS call this tool when a file has been uploaded and the user gives a command about it. "
            "If the user's command is ambiguous, pick the most logical action for that file type."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {
                    "type": "STRING",
                    "description": "Full path to the uploaded file. Leave empty to use the currently uploaded file.",
                },
                "action": {
                    "type": "STRING",
                    "description": (
                        "What to do with the file. Examples by type:\n"
                        "image: describe | ocr | resize | compress | convert | info\n"
                        "pdf: summarize | extract_text | to_word | info\n"
                        "docx/txt: summarize | fix | reformat | translate_hint | word_count | to_bullet\n"
                        "csv/excel: analyze | stats | filter | sort | convert | info\n"
                        "json: validate | format | analyze | to_csv\n"
                        "code: explain | review | fix | optimize | run | document | test\n"
                        "audio: transcribe | trim | convert | info\n"
                        "video: trim | extract_audio | extract_frame | compress | transcribe | info | convert\n"
                        "archive: list | extract\n"
                        "pptx: summarize | extract_text | analyze"
                    ),
                },
                "instruction": {
                    "type": "STRING",
                    "description": "Free-form instruction if action doesn't cover it. E.g. 'translate this to Turkish', 'find all email addresses'",
                },
                "format": {
                    "type": "STRING",
                    "description": "Target format for conversion. E.g. 'mp3', 'pdf', 'csv', 'png'",
                },
                "width": {
                    "type": "INTEGER",
                    "description": "Target width for image resize",
                },
                "height": {
                    "type": "INTEGER",
                    "description": "Target height for image resize",
                },
                "scale": {
                    "type": "NUMBER",
                    "description": "Scale factor for image resize (e.g. 0.5)",
                },
                "quality": {
                    "type": "INTEGER",
                    "description": "Quality 1-100 for image/video compress",
                },
                "start": {
                    "type": "STRING",
                    "description": "Start time for trim: seconds or HH:MM:SS",
                },
                "end": {
                    "type": "STRING",
                    "description": "End time for trim: seconds or HH:MM:SS",
                },
                "timestamp": {
                    "type": "STRING",
                    "description": "Timestamp for video frame extraction HH:MM:SS",
                },
                "column": {
                    "type": "STRING",
                    "description": "Column name for CSV filter/sort",
                },
                "value": {
                    "type": "STRING",
                    "description": "Filter value for CSV filter",
                },
                "condition": {
                    "type": "STRING",
                    "description": "Filter condition: equals|contains|gt|lt",
                },
                "ascending": {
                    "type": "BOOLEAN",
                    "description": "Sort order for CSV sort (default: true)",
                },
                "save": {
                    "type": "BOOLEAN",
                    "description": "Save result to file (default: true)",
                },
                "destination": {
                    "type": "STRING",
                    "description": "Output folder for archive extract",
                },
            },
            "required": [],
        },
    },
    {
        "name": "save_memory",
        "description": (
            "Save an important personal fact about the user to long-term memory. "
            "Call this silently whenever the user reveals something worth remembering: "
            "name, age, city, job, preferences, hobbies, relationships, projects, or future plans. "
            "Do NOT call for: weather, reminders, searches, or one-time commands. "
            "Do NOT announce that you are saving — just call it silently. "
            "Values must be in English regardless of the conversation language."
        ),
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {
                    "type": "STRING",
                    "description": (
                        "identity — name, age, birthday, city, job, language, nationality | "
                        "preferences — favorite food/color/music/film/game/sport, hobbies | "
                        "projects — active projects, goals, things being built | "
                        "relationships — friends, family, partner, colleagues | "
                        "wishes — future plans, things to buy, travel dreams | "
                        "notes — habits, schedule, anything else worth remembering"
                    ),
                },
                "key": {
                    "type": "STRING",
                    "description": "Short snake_case key (e.g. name, favorite_food, sister_name)",
                },
                "value": {
                    "type": "STRING",
                    "description": "Concise value in English (e.g. Fatih, pizza, older sister)",
                },
            },
            "required": ["category", "key", "value"],
        },
    },
    {
        "name": "system_monitor",
        "description": "Retrieves system hardware stats (CPU, RAM, Disk, Battery).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "full_report | get_cpu | get_ram | get_disk | get_battery"
                }
            },
            "required": ["action"],
        },
    },
    {
        "name": "media_control",
        "description": "Controls OS media playback and volume.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "play_pause | next_track | previous_track | volume_up | volume_down | mute"
                }
            },
            "required": ["action"],
        },
    },
    {
        "name": "autopilot",
        "description": "The ultimate visual automation agent. Call this tool ONLY WHENEVER you need to visually locate an element on the computer screen and interact with it (click, type, move mouse). DO NOT use this if the user asks 'what am I holding' or asks you to look at their camera (use screen_process for that)! Just provide the goal (e.g. 'move mouse to C drive', 'click the start button') and it will autonomously use visual bounding boxes to locate and click with 100% precision. CRITICAL: After executing this tool, DO NOT give a verbal reply describing what you did. Remain completely SILENT so the user isn't annoyed by constant voice confirmations.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal": {
                    "type": "STRING",
                    "description": "The exact goal the user wants to accomplish."
                }
            },
            "required": ["goal"],
        },
    },
    {
        "name": "clipboard_tool",
        "description": "Reads from or writes to the system clipboard. Use this when the user says 'explain what I just copied' or 'copy this to my clipboard'.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "read | write",
                },
                "text": {
                    "type": "STRING",
                    "description": "Text to write to the clipboard (only needed for write).",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "window_controller",
        "description": "Manages active application windows on the desktop.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "list | focus | close | minimize | minimize_all",
                },
                "title": {
                    "type": "STRING",
                    "description": "Title of the window to interact with (partial match supported).",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "db_memory_manager",
        "description": "Proactive memory tool using a local SQLite database. Use this to permanently store preferences, facts, or query stored info.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "store | query | forget",
                },
                "key": {
                    "type": "STRING",
                    "description": "A unique identifier for the memory.",
                },
                "value": {
                    "type": "STRING",
                    "description": "The information to store (only needed for store).",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "intelligence_agent",
        "description": "Fetches real-time market data (stocks/crypto via yfinance) or breaking news headlines via RSS.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "market | news",
                },
                "symbol": {
                    "type": "STRING",
                    "description": "Ticker symbol (e.g., AAPL, BTC-USD). Required for 'market' action.",
                },
                "topic": {
                    "type": "STRING",
                    "description": "News topic to search for (default: world). Used for 'news' action.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "system_diagnostics",
        "description": "Runs system diagnostics: laptop battery status, ping tests, Wi-Fi status, or internet speed tests.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "battery | speedtest | ping | wifi",
                },
                "target": {
                    "type": "STRING",
                    "description": "IP or domain to ping (e.g., 8.8.8.8). Used only for 'ping'.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "email_agent",
        "description": "Drafts an email by opening the system's default mail client with pre-filled fields. Use this when the user asks to write an email.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "to": {
                    "type": "STRING",
                    "description": "Recipient email address (optional).",
                },
                "subject": {
                    "type": "STRING",
                    "description": "Email subject (optional).",
                },
                "body": {
                    "type": "STRING",
                    "description": "The full drafted body of the email.",
                },
            },
            "required": ["body"],
        },
    },
    {
        "name": "camera_vision",
        "description": "Takes a physical photo using the system's default webcam and saves it to the desktop. Use this when the user asks you to look at something physically.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "capture",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "document_maker",
        "description": "Creates and saves a completely formatted Word document (.docx) or Text file (.txt).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "format": {
                    "type": "STRING",
                    "description": "docx | txt",
                },
                "filename": {
                    "type": "STRING",
                    "description": "The name of the file to save.",
                },
                "title": {
                    "type": "STRING",
                    "description": "The title or header inside the document.",
                },
                "content": {
                    "type": "STRING",
                    "description": "The full, rich text content of the document.",
                },
            },
            "required": ["format", "filename", "content"],
        },
    },
    {
        "name": "image_editor",
        "description": "Edits an existing local image (resize, crop, blur, black-and-white, convert).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "resize | blur | bw | convert",
                },
                "source_path": {
                    "type": "STRING",
                    "description": "Full absolute path to the image.",
                },
                "format": {
                    "type": "STRING",
                    "description": "Format to convert to (e.g., jpg, png). Only needed for 'convert'.",
                },
                "width": {
                    "type": "INTEGER",
                    "description": "New width. Only needed for 'resize'.",
                },
                "height": {
                    "type": "INTEGER",
                    "description": "New height. Only needed for 'resize'.",
                },
            },
            "required": ["action", "source_path"],
        },
    },
    {
        "name": "ui_controller",
        "description": "Controls the INDRA User Interface. Use this when the user asks you to open/close widgets, or to OPEN THE ATLAS MAP. If they ask to show a specific country, city, street, or landmark on the map, use the 'locate_place' action and provide the target_place.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "switch_vayu | switch_indra | switch_agni | open_logs | close_logs | open_sys | close_sys | open_vision | close_vision | open_webcam | close_webcam | open_agents | close_agents | open_remote | open_time | close_time | open_title | close_title | open_status | close_status | open_controls | close_controls | open_upload | close_upload | open_cmd | close_cmd | open_games | close_games | open_all | close_all | fullscreen_on | fullscreen_off | hide_to_tray | show_from_tray | quit_app | open_atlas | close_atlas | locate_place",
                },
                "target_place": {
                    "type": "STRING",
                    "description": "The name of the country, city, or place to locate when using the locate_place action.",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "terminal_controller",
        "description": "Executes raw shell commands on the host OS via PowerShell/bash. Use this to install packages, run scripts, ping servers, manage files natively, or any low-level system task. YOU HAVE GOD-MODE ACCESS. Use it wisely.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "STRING",
                    "description": "The shell command to execute.",
                },
                "timeout": {
                    "type": "INTEGER",
                    "description": "Execution timeout in seconds (default 60).",
                },
            },
            "required": ["command"],
        },
    },
    {
        "name": "spotify_controller",
        "description": "Controls Spotify to search and play a specific song, artist, or playlist. Use this whenever the user asks to play music.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query": {
                    "type": "STRING",
                    "description": "The song, artist, or playlist to search for.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "agent_cron",
        "description": "Schedules the AI to perform a specific task periodically or after a delay. The AI will wake up autonomously and execute the task as if you typed it.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "task": {
                    "type": "STRING",
                    "description": "The exact command you want the AI to run.",
                },
                "interval_minutes": {
                    "type": "NUMBER",
                    "description": "How many minutes to wait before running (or repeating).",
                },
                "repeat": {
                    "type": "BOOLEAN",
                    "description": "If true, it will run forever every interval_minutes.",
                },
            },
            "required": ["task", "interval_minutes", "repeat"],
        },
    },
    {
        "name": "python_executor",
        "description": "Instantly executes arbitrary Python code in a secure sandbox and returns the STDOUT/STDERR. Use this for quick math, data scraping, calculating hashes, or writing quick scripts.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "code": {
                    "type": "STRING",
                    "description": "The exact Python code to run.",
                },
            },
            "required": ["code"],
        },
    },
    {
        "name": "network_scanner",
        "description": "Scans the local network for devices, IPs, and open IoT ports.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "arp | ping_sweep",
                },
                "base_ip": {
                    "type": "STRING",
                    "description": "The base IP for ping sweep (e.g., 192.168.1).",
                },
            },
            "required": ["action"],
        },
    },
]

# --- Plugin system ---



class INDRALive:

    def __init__(self, ui: INDRAUI):
        self.ui = ui
        self.session = None
        self.audio_in_queue = None
        self.out_queue = None
        self._loop = None
        self._is_speaking = False
        self._speaking_lock = threading.Lock()
        self._phone_active = False  # True while phone mic is streaming; pauses PC mic
        self.ui.on_text_command = self._on_text_command
        self.ui.on_remote_clicked = self._make_remote_key
        self._turn_done_event: asyncio.Event | None = None
        self._dashboard = None
        self.spatial_memory = {}

    def _make_remote_key(self):
        """Called from Qt main thread when user presses Remote Control."""
        if self._dashboard is None:
            self.ui.write_log(
                "SYS: Dashboard unavailable. "
                'Run: pip install fastapi "uvicorn[standard]" cryptography'
            )
            return None
        key = self._dashboard.new_key()
        url = self._dashboard.get_url()
        manual = self._dashboard.get_manual_url()
        return url, key, f"{url}/auto-login?key={key}", manual

    def _on_text_command(self, text: str):
        if not self._loop or not self.session:
            return
        
        # Intercept trigger phrases instantly
        t = text.lower()
        if "vayu activate" in t or "activate vayu" in t:
            self.ui._win._ui_cmd_sig.emit("switch_vayu")
        elif "indra activate" in t or "activate indra" in t or "deactivate vayu" in t:
            self.ui._win._ui_cmd_sig.emit("switch_indra")

        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns=[types.Content(role="user", parts=[types.Part.from_text(text=text)])], turn_complete=True
            ),
            self._loop,
        )

    def set_speaking(self, value: bool):
        with self._speaking_lock:
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
        elif not self.ui.muted:
            self.ui.set_state("LISTENING")

    def speak(self, text: str):
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send_client_content(
                turns=[types.Content(role="user", parts=[types.Part.from_text(text=text)])], turn_complete=True
            ),
            self._loop,
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        memory = load_memory()
        mem_str = format_memory_for_prompt(memory)
        sys_prompt = _load_system_prompt()

        now = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
            f"[SYSTEM ARCHITECTURE]\n"
            f"Your source code is located at: {BASE_DIR}\n"
            f"You have explicit permission to use the `code_helper` tool to modify your own source code (like main.py or add new tools in the actions/ folder). You are a self-improving God AI.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
            
        try:
            from actions.memory_manager import get_all_memory
            db_mem = get_all_memory()
            if db_mem:
                parts.append(db_mem)
        except Exception as e:
            pass
            
        parts.append(sys_prompt)

        return types.LiveConnectConfig(
            # response_modalities omitted
            output_audio_transcription={},
            input_audio_transcription={},
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[INDRA] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")




        if name == "save_memory":
            category = args.get("category", "notes")
            key = args.get("key", "")
            value = args.get("value", "")
            if key and value:
                update_memory({category: {key: {"value": value}}})
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name, response={"result": "ok", "silent": True}
            )

        loop = asyncio.get_event_loop()
        result = "Done."

        try:
            if name == "open_api_settings":
                self.ui._safe_cmd("API_KEYS")
                result = "Opened API Keys settings overlay."

            elif name == "open_app":
                r = await loop.run_in_executor(
                    None,
                    lambda: open_app(parameters=args, response=None, player=self.ui),
                )
                result = r or f"Opened {args.get('app_name')}."

            elif name == "weather_report":
                r = await loop.run_in_executor(
                    None, lambda: weather_action(parameters=args, player=self.ui)
                )
                result = r or "Weather delivered."
            elif name == "system_monitor":
                r = await loop.run_in_executor(
                    None, lambda: system_monitor(parameters=args, ui_callback=self.ui.write_log, dashboard_callback=None, send_log_callback=self.ui.write_log, get_memory_callback=lambda: "")
                )
                result = r or "System status retrieved."
            elif name == "media_control":
                r = await loop.run_in_executor(
                    None, lambda: media_control(parameters=args, ui_callback=self.ui.write_log, dashboard_callback=None, send_log_callback=self.ui.write_log, get_memory_callback=lambda: "")
                )
                result = r or "Media command executed."
            elif name == "autopilot":
                r = await loop.run_in_executor(
                    None, lambda: autopilot(parameters=args, ui_callback=self.ui.write_log, dashboard_callback=None, send_log_callback=self.ui.write_log, get_memory_callback=lambda: self.spatial_memory)
                )
                result = r or "AutoPilot goal finished."
            elif name == "clipboard_tool":
                r = await loop.run_in_executor(
                    None, lambda: clipboard_tool(parameters=args, player=self.ui)
                )
                result = r or "Clipboard accessed."
            elif name == "window_controller":
                r = await loop.run_in_executor(
                    None, lambda: window_controller(parameters=args, player=self.ui)
                )
                result = r or "Window manipulated."
            elif name == "db_memory_manager":
                r = await loop.run_in_executor(
                    None, lambda: db_memory_manager(parameters=args, player=self.ui)
                )
                result = r or "Memory accessed."
            elif name == "intelligence_agent":
                r = await loop.run_in_executor(
                    None, lambda: intelligence_agent(parameters=args, player=self.ui)
                )
                result = r or "Intelligence data fetched."
            elif name == "system_diagnostics":
                r = await loop.run_in_executor(
                    None, lambda: system_diagnostics(parameters=args, player=self.ui)
                )
                result = r or "Diagnostics complete."
            elif name == "email_agent":
                r = await loop.run_in_executor(
                    None, lambda: email_agent(parameters=args, player=self.ui)
                )
                result = r or "Email draft opened."
            elif name == "camera_vision":
                r = await loop.run_in_executor(
                    None, lambda: camera_vision(parameters=args, player=self.ui)
                )
                result = r or "Webcam captured."
            elif name == "document_maker":
                r = await loop.run_in_executor(
                    None, lambda: document_maker(parameters=args, player=self.ui)
                )
                result = r or "Document generated."
            elif name == "image_editor":
                r = await loop.run_in_executor(
                    None, lambda: image_editor(parameters=args, player=self.ui)
                )
                result = r or "Image edited."
            elif name == "terminal_controller":
                r = await loop.run_in_executor(
                    None, lambda: terminal_controller(parameters=args, player=self.ui)
                )
                result = r or "Command executed."
            elif name == "spotify_controller":
                r = await loop.run_in_executor(
                    None, lambda: spotify_controller(parameters=args, player=self.ui)
                )
                result = r or "Spotify command executed."
            elif name == "agent_cron":
                r = await loop.run_in_executor(
                    None, lambda: agent_cron(parameters=args, player=self.ui, on_text_command=self.ui.on_text_command)
                )
                result = r or "Cron agent scheduled."
            elif name == "python_executor":
                r = await loop.run_in_executor(
                    None, lambda: python_executor(parameters=args, player=self.ui)
                )
                result = r or "Python execution complete."
            elif name == "network_scanner":
                r = await loop.run_in_executor(
                    None, lambda: network_scanner(parameters=args, player=self.ui)
                )
                result = r or "Network scan complete."

            elif name == "game_scanner":
                try:
                    import actions.game_scanner as game_scanner_mod
                    import importlib
                    importlib.reload(game_scanner_mod)
                    r = await loop.run_in_executor(None, game_scanner_mod.scan_games)
                    result = r or "No games found."
                except Exception as e:
                    result = f"Failed to scan games: {e}"

            elif name == "ui_controller":
                action = args.get("action", "")
                if action == "switch_vayu":
                    self.ui._win._ui_cmd_sig.emit("switch_vayu")
                    result = "Vayu interface activated."
                elif action == "switch_agni":
                    self.ui._win._ui_cmd_sig.emit("switch_agni")
                    result = "Agni interface activated."
                elif action == "switch_indra":
                    self.ui._win._ui_cmd_sig.emit("switch_indra")
                    result = "Indra interface restored."
                elif action == "open_logs" or action == "close_logs":
                    self.ui.toggle_activity_log()
                    result = "Activity log toggled."
                elif action == "open_sys" or action == "close_sys":
                    self.ui.toggle_sys_monitor()
                    result = "System monitor toggled."
                elif action == "open_vision" or action == "close_vision":
                    self.ui.toggle_vision_monitor()
                    result = "Vision system toggled."
                elif action == "open_webcam" or action == "close_webcam":
                    self.ui.toggle_webcam_panel()
                    result = "Live Webcam feed toggled."
                elif action == "open_agents" or action == "close_agents":
                    self.ui.toggle_agents_panel()
                    result = "Active agents panel toggled."
                elif action == "open_games" or action == "close_games":
                    self.ui._win._ui_cmd_sig.emit("games")
                    result = "Games panel toggled."
                elif action == "open_remote":
                    self.ui.open_remote()
                    result = "Remote control panel opened."
                elif action == "open_time" or action == "close_time":
                    self.ui.toggle_time_panel()
                    result = "Time panel toggled."
                elif action == "open_title" or action == "close_title":
                    self.ui.toggle_title_panel()
                    result = "Title panel toggled."
                elif action == "open_status" or action == "close_status":
                    self.ui.toggle_status_panel()
                    result = "Status panel toggled."
                elif action == "open_controls" or action == "close_controls":
                    self.ui.toggle_controls_panel()
                    result = "Controls panel toggled."
                elif action == "open_upload" or action == "close_upload":
                    self.ui.toggle_upload_panel()
                    result = "File upload widget toggled."
                elif action == "open_cmd" or action == "close_cmd":
                    self.ui.toggle_cmd_panel()
                    result = "Command input widget toggled."
                elif action == "fullscreen_on" or action == "fullscreen_off":
                    self.ui.set_fullscreen(action == "fullscreen_on")
                    result = f"Fullscreen {'enabled' if action == 'fullscreen_on' else 'disabled'}."
                elif action == "hide_to_tray":
                    self.ui._win._ui_cmd_sig.emit("hide_to_tray")
                    result = "INDRA hidden to background system tray."
                elif action == "show_from_tray":
                    self.ui._win._ui_cmd_sig.emit("show_from_tray")
                    result = "INDRA restored from system tray to fullscreen."
                elif action == "open_atlas":
                    self.ui._win._ui_cmd_sig.emit("open_atlas")
                    result = "Atlas interface opened."
                elif action == "close_atlas":
                    self.ui._win._ui_cmd_sig.emit("close_atlas")
                    result = "Atlas interface closed."
                elif action == "locate_place":
                    target = args.get("target_place", "")
                    self.ui._win._ui_cmd_sig.emit(f"locate_place|{target}")
                    result = f"Locating {target} on the Atlas."
                elif action == "quit_app":
                    result = "Shutting down. Goodbye, sir."
                    # Schedule hard exit after 2 seconds so farewell audio can play
                    import threading as _t
                    def _do_exit():
                        import time as _time
                        _time.sleep(2.0)
                        import os as _os
                        _os._exit(0)
                    _t.Thread(target=_do_exit, daemon=True).start()
                elif action == "open_all" or action == "close_all":
                    self.ui.toggle_all_panels()
                    result = "All panels toggled."
                else:
                    result = f"Unknown action: {action}"

            elif name == "browser_control":
                r = await loop.run_in_executor(
                    None, lambda: browser_control(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "file_controller":
                r = await loop.run_in_executor(
                    None, lambda: file_controller(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "send_message":
                r = await loop.run_in_executor(
                    None,
                    lambda: send_message(
                        parameters=args,
                        response=None,
                        player=self.ui,
                        session_memory=None,
                    ),
                )
                result = r or f"Message sent to {args.get('receiver')}."

            elif name == "reminder":
                r = await loop.run_in_executor(
                    None,
                    lambda: reminder(parameters=args, response=None, player=self.ui),
                )
                result = r or "Reminder set."

            elif name == "youtube_video":
                r = await loop.run_in_executor(
                    None,
                    lambda: youtube_video(
                        parameters=args, response=None, player=self.ui
                    ),
                )
                result = r or "Done."

            elif name == "screen_process":
                if args.get("angle", "screen") == "camera" and hasattr(self.ui, "latest_webcam_frame") and self.ui.latest_webcam_frame:
                    args["_precaptured_image"] = self.ui.latest_webcam_frame
                    args["_precaptured_mime"] = "image/jpeg"
                    
                r = await loop.run_in_executor(
                    None,
                    lambda: screen_process(
                        parameters=args,
                        response=None,
                        player=self.ui,
                        session_memory=None,
                        speak=getattr(self, "speak", None),
                    ),
                )
                result = r or "Image analyzed."

            elif name == "computer_settings":
                r = await loop.run_in_executor(
                    None,
                    lambda: computer_settings(
                        parameters=args, response=None, player=self.ui
                    ),
                )
                result = r or "Done."

            elif name == "desktop_control":
                r = await loop.run_in_executor(
                    None, lambda: desktop_control(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "code_helper":
                r = await loop.run_in_executor(
                    None,
                    lambda: code_helper(
                        parameters=args, player=self.ui, speak=self.speak
                    ),
                )
                result = r or "Done."

            elif name == "dev_agent":
                r = await loop.run_in_executor(
                    None,
                    lambda: dev_agent(
                        parameters=args, player=self.ui, speak=self.speak
                    ),
                )
                result = r or "Done."

            elif name == "web_search":
                r = await loop.run_in_executor(
                    None, lambda: web_search_action(parameters=args, player=self.ui)
                )
                result = r or "Done."
            elif name == "file_processor":
                if not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                r = await loop.run_in_executor(
                    None,
                    lambda: file_processor(
                        parameters=args, player=self.ui, speak=self.speak
                    ),
                )
                result = r or "Done."

            elif name == "computer_control":
                r = await loop.run_in_executor(
                    None, lambda: computer_control(parameters=args, player=self.ui)
                )
                result = r or "Done."

            elif name == "game_updater":
                r = await loop.run_in_executor(
                    None,
                    lambda: game_updater(
                        parameters=args, player=self.ui, speak=self.speak
                    ),
                )
                result = r or "Done."

            elif name == "flight_finder":
                r = await loop.run_in_executor(
                    None, lambda: flight_finder(parameters=args, player=self.ui)
                )
                result = r or "Done."


            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[INDRA] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(id=fc.id, name=name, response={"result": result})

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            await self.session.send_realtime_input(audio=msg)

    async def _listen_audio(self):
        print("[INDRA] 🎤 Mic started")
        loop = asyncio.get_event_loop()
        import webrtcvad
        
        vad = webrtcvad.Vad(3) # 3 is most aggressive at filtering non-human noise
        _audio_buffer = bytearray()
        _speech_detected = False

        def callback(indata, frames, time_info, status):
            nonlocal _audio_buffer, _speech_detected
            with self._speaking_lock:
                INDRA_speaking = self._is_speaking
                
            if not INDRA_speaking and not self.ui.muted and not self._phone_active:
                raw_bytes = indata.tobytes()
                try:
                    if vad.is_speech(raw_bytes, 16000):
                        _speech_detected = True
                except Exception:
                    pass

                _audio_buffer.extend(raw_bytes)

                # Send ~270ms chunks to avoid flooding WebSocket (9 * 30ms)
                if len(_audio_buffer) >= 8640:
                    if _speech_detected:
                        data_to_send = bytes(_audio_buffer)
                    else:
                        data_to_send = b'\x00' * len(_audio_buffer)

                    loop.call_soon_threadsafe(
                        self.out_queue.put_nowait, {"data": data_to_send, "mime_type": "audio/pcm;rate=16000"}
                    )
                    _audio_buffer.clear()
                    _speech_detected = False

        try:
            with sd.InputStream(
                samplerate=SEND_SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                callback=callback,
                blocksize=480, # Exactly 30ms at 16000Hz for WebRTC VAD
                latency='low',
            ):
                print("[INDRA] 🎤 Mic stream open")
                while True:
                    await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[INDRA] ❌ Mic: {e}")
            raise

    async def _receive_audio(self):
        print("[INDRA] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if getattr(response, "data", None):
                        pass # Removed to avoid duplicate audio or garbage data

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)
                                
                        if sc.model_turn:
                            for part in sc.model_turn.parts:
                                if part.inline_data:
                                    if self._turn_done_event and self._turn_done_event.is_set():
                                        self._turn_done_event.clear()
                                    self.audio_in_queue.put_nowait(part.inline_data.data)
                                if part.text:
                                    txt = _clean_transcript(part.text)
                                    if txt:
                                        if getattr(part, 'thought', False):
                                            out_buf.append(f"[Thinking: {txt}]")
                                        else:
                                            out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                                if self._dashboard:
                                    asyncio.create_task(
                                        self._dashboard.broadcast(
                                            {
                                                "type": "log",
                                                "speaker": "user",
                                                "text": full_in,
                                                "ts": datetime.now().isoformat(),
                                            }
                                        )
                                    )
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"INDRA: {full_out}")
                                if self._dashboard:
                                    asyncio.create_task(
                                        self._dashboard.broadcast(
                                            {
                                                "type": "log",
                                                "speaker": "INDRA",
                                                "text": full_out,
                                                "ts": datetime.now().isoformat(),
                                            }
                                        )
                                    )
                            out_buf = []

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[INDRA] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[INDRA] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        """High-quality, jitter-buffered audio playback engine.
        
        Uses a dedicated background thread with a ring buffer to decouple
        network arrival timing from playback timing, eliminating clicks/stutters.
        """
        import threading
        import collections
        print("[INDRA] 🔊 Play started")

        # ── Find best output device: prefer WASAPI for lowest latency ──────
        device_idx = None
        try:
            devices = sd.query_devices()
            # Prefer Headphones WASAPI for best sound quality
            for priority_name in ["Headphones (Realtek(R) Audio), Windows WASAPI",
                                   "Speakers (Realtek(R) Audio), Windows WASAPI",
                                   "Headphones (Realtek(R) Audio)",
                                   "Speakers (Realtek(R) Audio)"]:
                for i, d in enumerate(devices):
                    if d['name'] == priority_name and d['max_output_channels'] > 0:
                        device_idx = i
                        break
                if device_idx is not None:
                    break
        except Exception:
            pass

        # ── Shared ring buffer between async receiver and sync player ───────
        # Each entry is a raw bytes chunk from the AI
        _buf: collections.deque = collections.deque()
        _buf_lock = threading.Lock()
        _buf_ready = threading.Event()   # signals the player thread
        _stop_event = threading.Event()

        # bytes per play block (2 bytes per int16 sample, mono)
        _block_bytes = _PLAY_BLOCKSIZE * 2
        _silence_block = b'\x00' * _block_bytes

        # ── Producer: move chunks from asyncio queue → ring buffer ──────────
        async def _produce():
            while not _stop_event.is_set():
                try:
                    chunk = await asyncio.wait_for(self.audio_in_queue.get(), timeout=0.2)
                    with _buf_lock:
                        _buf.append(chunk)
                    _buf_ready.set()
                    self.set_speaking(True)
                except asyncio.TimeoutError:
                    # No new audio — check if turn is done
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                        and len(_buf) == 0
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()

        def _consume():
            try:
                stream_kwargs = dict(
                    samplerate=RECEIVE_SAMPLE_RATE,
                    channels=CHANNELS,
                    dtype="int16",
                    latency='low'
                )
                if device_idx is not None:
                    stream_kwargs["device"] = device_idx

                with sd.RawOutputStream(**stream_kwargs) as stream:
                    stream.start()

                    while not _stop_event.is_set():
                        _buf_ready.wait(timeout=0.1)
                        _buf_ready.clear()

                        raw = b''
                        with _buf_lock:
                            if _buf:
                                raw = b''.join(_buf)
                                _buf.clear()

                        if raw:
                            stream.write(raw)

            except Exception as e:
                print(f"[INDRA] ❌ Play thread: {e}")

        # ── Start consumer thread, then run producer in event loop ──────────
        t = threading.Thread(target=_consume, daemon=True, name="IndraAudioPlayer")
        t.start()
        try:
            await _produce()
        except Exception as e:
            print(f"[INDRA] ❌ Play: {e}")
            raise
        finally:
            _stop_event.set()
            _buf_ready.set()  # wake sleeping consumer so it can exit
            self.set_speaking(False)

    async def _relay_phone_audio(self) -> None:
        """Forward phone mic PCM chunks from dashboard queue into the Gemini Live session."""
        q = self._dashboard._phone_audio_queue
        while True:
            try:
                chunk = await asyncio.wait_for(q.get(), timeout=1.0)
            except asyncio.TimeoutError:
                # No audio for 1 s → phone mic inactive, give PC mic back
                self._phone_active = False
                continue
            self._phone_active = True  # phone is streaming — silence PC mic
            with self._speaking_lock:
                speaking = self._is_speaking
            if not speaking and not self.ui.muted:
                try:
                    self.out_queue.put_nowait(chunk)
                except asyncio.QueueFull:
                    pass

    def _on_phone_connected(self) -> None:
        self.ui.write_log("SYS: Phone connected via Remote Dashboard.")
        self.ui.notify_phone_connected()


    # ── dashboard command relay ─────────────────────────────────────────────

    async def _process_dashboard_commands(self) -> None:
        while True:
            try:
                text = await asyncio.wait_for(
                    self._dashboard._command_queue.get(), timeout=0.5
                )
                if not text:
                    continue
                # Wait up to 8s for session to become ready after a wake
                for _ in range(80):
                    if self.session:
                        break
                    await asyncio.sleep(0.1)
                if self.session:
                    await self.session.send_client_content(
                        turns=[types.Content(role="user", parts=[types.Part.from_text(text=text)])],
                        turn_complete=True,
                    )
                    self.ui.write_log(f"[Web]: {text}")
                else:
                    print(f"[Dashboard] Dropped command (no session): {text}")
            except asyncio.TimeoutError:
                pass
            except Exception as e:
                print(f"[Dashboard] Command error: {e}")
                await asyncio.sleep(0.5)

    # ── main loop ───────────────────────────────────────────────────────────

    async def run(self):
        self._loop = asyncio.get_event_loop()

        client = genai.Client(
            api_key=_get_api_key(), http_options={"api_version": "v1beta"}
        )

        # Start dashboard (optional — needs: pip install fastapi "uvicorn[standard]" cryptography)
        try:
            from dashboard.server import DashboardServer

            self._dashboard = DashboardServer()
            self._dashboard.set_connect_callback(self._on_phone_connected)
            asyncio.create_task(self._dashboard.serve())
            # Runs for the whole lifetime, not just inside an active session
            asyncio.create_task(self._process_dashboard_commands())
        except Exception as e:
            print(f"[Dashboard] Disabled: {e}")
            self._dashboard = None

        while True:
            try:
                print("[INDRA] Connecting...")
                self.ui.set_state("STARTING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session = session
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue = asyncio.Queue(maxsize=200)
                    self._turn_done_event = asyncio.Event()

                    print("[INDRA] Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: INDRA online.")

                    # Proactive AI Greeting
                    greeting_prompt = (
                        "System Boot Sequence Complete. You are INDRA. "
                        "Give a short, cool, slightly sci-fi greeting to the user (e.g. 'Welcome back sir' or 'Systems online') "
                        "and ask what's on their mind today. Do not mention that this is a prompt. YOU MUST ALWAYS address the user as 'sir'."
                    )
                    await self.session.send_client_content(turns=[types.Content(role="user", parts=[types.Part.from_text(text=greeting_prompt)])], turn_complete=True)

                    if self._dashboard:
                        await self._dashboard.broadcast(
                            {"type": "status", "state": "active"}
                        )

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())
                    if self._dashboard:
                        tg.create_task(self._relay_phone_audio())

            except Exception as e:
                err_str = str(e)
                if "1006" in err_str or "unhandled errors in a TaskGroup" in err_str or "timeout" in err_str.lower() or "timed out" in err_str.lower() or "WinError 64" in err_str or "WinError 10054" in err_str:
                    print(f"[INDRA] Connection dropped: {e} (Reconnecting...)")
                else:
                    print(f"[INDRA] Error: {e}")
                    traceback.print_exc()
            finally:
                self.session = None

            self.set_speaking(False)
            self.ui.set_state("SLEEPING")

            if self._dashboard:
                await self._dashboard.broadcast({"type": "status", "state": "sleeping"})

            print("[INDRA] Reconnecting in 3s...")
            await asyncio.sleep(3)


def main():
    ui = INDRAUI("face.png")

    def runner():
        ui.wait_for_api_key()
        INDRA = INDRALive(ui)
        try:
            asyncio.run(INDRA.run())
        except KeyboardInterrupt:
            print("\n🔴 Shutting down...")

    threading.Thread(target=runner, daemon=True).start()
    ui.root.mainloop()


if __name__ == "__main__":
    main()
