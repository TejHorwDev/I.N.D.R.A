# pylint: disable=all
# pylint: disable=C0114, C0115, C0116, C0103, C0301, C0302, W0611, W0718, R0902, R0903, R0904, R0911, R0912, R0913, R0914, R0915, R0801
"""
AutoPilot — Visual Autonomous Desktop Agent
============================================

This module drives a continuous "see -> decide -> act" loop on top of a
vision-capable Gemini model. On every step it:

    1. Captures the current screen (with optional downscaling for speed).
    2. Builds a prompt containing the goal, the screen size, and a rolling
       history of the last few actions (so the model doesn't repeat itself
       or forget what it already tried).
    3. Asks Gemini for exactly one next action as JSON.
    4. Robustly parses that JSON (tolerating markdown fences / stray text).
    5. Validates + clamps any coordinates to the real screen bounds.
    6. Executes the action with pyautogui.
    7. Records the result in a memory buffer used for both the next prompt
       and "stuck loop" detection (so the agent doesn't click the same
       button forever).
    8. Repeats until the model reports "done"/"fail", the loop gets stuck,
       or a configurable step budget runs out.

The original core building blocks (`_get_api_key`, the screenshot capture
approach, and the click / move / type / press / done action vocabulary) are
preserved exactly as designed — everything around them has been hardened
for reliability, accuracy, and observability.
"""

from __future__ import annotations

import io
import json
import logging
import re
import time
import traceback
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import mss
import mss.tools
import pyautogui
from google import genai
from PIL import Image, ImageDraw

# ---------------------------------------------------------------------------
# Global pyautogui safety configuration
# ---------------------------------------------------------------------------
# FAILSAFE lets a human abort instantly by slamming the mouse into a screen
# corner. PAUSE adds a tiny delay after every pyautogui call so rapid-fire
# actions don't get dropped by slower UIs.
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05

# ---------------------------------------------------------------------------
# Module-level logger (in addition to the caller-supplied callbacks)
# ---------------------------------------------------------------------------
logger = logging.getLogger("autopilot")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(
        logging.Formatter("[%(asctime)s] %(levelname)s autopilot: %(message)s", "%H:%M:%S")
    )
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO)


# ===========================================================================
# Constants
# ===========================================================================

DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_MAX_STEPS = 25
DEFAULT_MAX_API_RETRIES = 3
DEFAULT_API_RETRY_BACKOFF_SECONDS = 1.5
DEFAULT_ACTION_SETTLE_SECONDS = 1.0
DEFAULT_MAX_IMAGE_DIMENSION = 1568  # Gemini handles this efficiently without losing UI detail.
DEFAULT_HISTORY_WINDOW = 6
DEFAULT_STUCK_REPEAT_THRESHOLD = 3
DEFAULT_TYPE_INTERVAL_SECONDS = 0.02
DEFAULT_MOVE_DURATION_SECONDS = 0.2

VALID_ACTIONS = {
    "click",
    "double_click",
    "right_click",
    "move",
    "drag",
    "type",
    "press",
    "hotkey",
    "scroll",
    "wait",
    "done",
    "fail",
}


# ===========================================================================
# Exceptions
# ===========================================================================

class AutoPilotError(Exception):
    """Base class for all autopilot-specific errors."""


class ScreenCaptureError(AutoPilotError):
    """Raised when the screen cannot be captured."""


class ModelResponseError(AutoPilotError):
    """Raised when the vision model's response cannot be used."""


class ActionExecutionError(AutoPilotError):
    """Raised when a parsed action cannot be safely executed."""


# ===========================================================================
# Configuration
# ===========================================================================

@dataclass
class AutoPilotConfig:
    """Tunable parameters controlling the autopilot loop's behavior."""

    model: str = DEFAULT_MODEL
    max_steps: int = DEFAULT_MAX_STEPS
    max_api_retries: int = DEFAULT_MAX_API_RETRIES
    api_retry_backoff_seconds: float = DEFAULT_API_RETRY_BACKOFF_SECONDS
    action_settle_seconds: float = DEFAULT_ACTION_SETTLE_SECONDS
    max_image_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION
    history_window: int = DEFAULT_HISTORY_WINDOW
    stuck_repeat_threshold: int = DEFAULT_STUCK_REPEAT_THRESHOLD
    type_interval_seconds: float = DEFAULT_TYPE_INTERVAL_SECONDS
    move_duration_seconds: float = DEFAULT_MOVE_DURATION_SECONDS
    verify_with_diff: bool = True
    monitor_index: Optional[int] = None  # None => auto-pick (prefers monitor 1 if multiple)

    @classmethod
    def from_parameters(cls, parameters: Dict[str, Any]) -> "AutoPilotConfig":
        """Build a config, letting callers override any field via `parameters`."""
        cfg = cls()
        for key in cfg.__dataclass_fields__:
            if key in parameters:
                try:
                    setattr(cfg, key, type(getattr(cfg, key))(parameters[key]))
                except (TypeError, ValueError):
                    setattr(cfg, key, parameters[key])
        return cfg


# ===========================================================================
# Step / Memory bookkeeping
# ===========================================================================

@dataclass
class StepRecord:
    """A single executed (or attempted) step, used for prompting + stuck detection."""

    step_index: int
    action: str
    reason: str
    target_box: Optional[List[float]] = None
    detail: Optional[str] = None
    success: bool = True
    error: Optional[str] = None
    screen_changed: Optional[bool] = None

    def signature(self) -> str:
        """A coarse fingerprint used to detect repeated, non-progressing actions."""
        box_sig = ""
        if self.target_box:
            box_sig = ",".join(f"{v:.0f}" for v in self.target_box)
        return f"{self.action}|{box_sig}|{(self.detail or '')[:40]}"

    def to_prompt_line(self) -> str:
        status = "ok" if self.success else f"FAILED ({self.error})"
        changed = ""
        if self.screen_changed is False:
            changed = " [screen did not visibly change after this]"
        return f"Step {self.step_index}: {self.action} -> {status}{changed}. Reason given: {self.reason}"


class ActionMemory:
    """Rolling history of executed steps plus stuck-loop detection."""

    def __init__(self, history_window: int, stuck_repeat_threshold: int) -> None:
        self.history_window = history_window
        self.stuck_repeat_threshold = stuck_repeat_threshold
        self._records: List[StepRecord] = []

    def add(self, record: StepRecord) -> None:
        self._records.append(record)

    def recent(self) -> List[StepRecord]:
        return self._records[-self.history_window:]

    def all_records(self) -> List[StepRecord]:
        return list(self._records)

    def is_stuck(self) -> bool:
        """True if the last N actions are all (near-)identical, implying no progress."""
        if len(self._records) < self.stuck_repeat_threshold:
            return False
        last_n = self._records[-self.stuck_repeat_threshold:]
        signatures = {r.signature() for r in last_n}
        return len(signatures) == 1

    def render_history_block(self) -> str:
        recent = self.recent()
        if not recent:
            return "(no actions taken yet)"
        return "\n".join(r.to_prompt_line() for r in recent)


# ===========================================================================
# API key loading (kept intact — original core behavior)
# ===========================================================================

def _get_api_key() -> str:
    from pathlib import Path
    import sys
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent
    else:
        base = Path(__file__).resolve().parent.parent
    cfg_path = base / "config" / "api_keys.json"
    try:
        return json.loads(cfg_path.read_text(encoding="utf-8")).get("gemini_api_key", "")
    except Exception:
        return ""


# ===========================================================================
# Screen capture
# ===========================================================================

class ScreenCapture:
    """Handles taking, downscaling, and diffing screenshots."""

    def __init__(self, monitor_index: Optional[int] = None, max_dimension: int = DEFAULT_MAX_IMAGE_DIMENSION) -> None:
        self.monitor_index = monitor_index
        self.max_dimension = max_dimension

    def _select_monitor(self, monitors: List[Dict[str, int]]) -> Dict[str, int]:
        if self.monitor_index is not None and 0 <= self.monitor_index < len(monitors):
            return monitors[self.monitor_index]
        # monitors[0] is the "all monitors combined" virtual screen in mss;
        # prefer the first real monitor when present, matching original behavior.
        return monitors[1] if len(monitors) > 1 else monitors[0]

    def capture_native(self) -> Tuple[Image.Image, int, int]:
        """Capture at full native resolution. Returns (image, native_w, native_h)."""
        try:
            with mss.mss() as sct:
                target = self._select_monitor(sct.monitors)
                shot = sct.grab(target)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                return img, img.width, img.height
        except Exception as exc:
            raise ScreenCaptureError(f"Failed to capture screen: {exc}") from exc

    def capture_for_model(self) -> Tuple[Image.Image, int, int]:
        """
        Capture the screen and return an (optionally downscaled) image suitable
        for sending to the model, alongside the *native* screen dimensions.

        Coordinates returned by the model are always on a normalized 0-1000
        scale, so downscaling the image for transport never affects click
        accuracy — it only reduces upload size / latency.
        """
        img, native_w, native_h = self.capture_native()
        longest_side = max(img.width, img.height)
        if longest_side > self.max_dimension:
            scale = self.max_dimension / float(longest_side)
            new_size = (max(1, int(img.width * scale)), max(1, int(img.height * scale)))
            img = img.resize(new_size, Image.LANCZOS)
        return img, native_w, native_h

    @staticmethod
    def quick_diff_score(img_a: Image.Image, img_b: Image.Image, sample_grid: int = 16) -> float:
        """
        Cheap perceptual diff between two screenshots, used only to log whether
        an action visibly changed the screen (not used to block execution).
        Returns a 0.0-1.0 fraction of sampled points that differ meaningfully.
        """
        try:
            a = img_a.convert("RGB").resize((sample_grid, sample_grid))
            b = img_b.convert("RGB").resize((sample_grid, sample_grid))
            a_px = a.load()
            b_px = b.load()
            diffs = 0
            total = sample_grid * sample_grid
            for y in range(sample_grid):
                for x in range(sample_grid):
                    ar, ag, ab = a_px[x, y]
                    br, bg, bb = b_px[x, y]
                    if abs(ar - br) + abs(ag - bg) + abs(ab - bb) > 30:
                        diffs += 1
            return diffs / float(total)
        except Exception:
            return 0.0  # Non-fatal: diffing is purely informational.


# ===========================================================================
# Prompt construction
# ===========================================================================

class PromptBuilder:
    """Builds the per-step instruction prompt sent alongside the screenshot."""

    ACTION_SPEC = """\
Respond ONLY with a single valid JSON object. Do not include markdown formatting, \
backticks, or any text outside the JSON object.

Choose exactly one of the following action types:
1. Click:        {"action": "click", "box_2d": [ymin, xmin, ymax, xmax], "reason": "<string>"}
2. Double click: {"action": "double_click", "box_2d": [ymin, xmin, ymax, xmax], "reason": "<string>"}
3. Right click:  {"action": "right_click", "box_2d": [ymin, xmin, ymax, xmax], "reason": "<string>"}
4. Move:         {"action": "move", "box_2d": [ymin, xmin, ymax, xmax], "reason": "<string>"}
5. Drag:         {"action": "drag", "start_box_2d": [ymin, xmin, ymax, xmax], "end_box_2d": [ymin, xmin, ymax, xmax], "reason": "<string>"}
6. Type:         {"action": "type", "text": "<string>", "reason": "<string>"}
7. Press key:    {"action": "press", "key": "<string>", "reason": "<string>"}  (e.g. "enter", "win", "tab", "esc")
8. Hotkey combo: {"action": "hotkey", "keys": ["<string>", "..."], "reason": "<string>"}  (e.g. ["ctrl","c"])
9. Scroll:       {"action": "scroll", "direction": "up"|"down", "amount": <int>, "reason": "<string>"}
10. Wait:        {"action": "wait", "seconds": <number>, "reason": "<string>"}
11. Done:        {"action": "done", "reason": "<string>"}   (the goal is fully achieved)
12. Fail:        {"action": "fail", "reason": "<string>"}   (the goal cannot be achieved from here)

All bounding boxes use a 0-1000 scale where [0,0] is the top-left corner and \
[1000,1000] is the bottom-right corner of the screen, regardless of the actual \
screen resolution.
"""

    def __init__(self, memory: ActionMemory) -> None:
        self.memory = memory

    def build(self, goal: str, step_number: int, max_steps: int, persistent_memory: Any) -> str:
        history_block = self.memory.render_history_block()
        memory_block = ""
        if persistent_memory:
            try:
                memory_block = (
                    "\nRelevant persistent memory/context from prior sessions:\n"
                    f"{json.dumps(persistent_memory, ensure_ascii=False, default=str)[:2000]}\n"
                )
            except Exception:
                memory_block = f"\nRelevant persistent memory/context: {persistent_memory}\n"

        return f"""You are an autonomous computer-control agent operating a real desktop.

GOAL: "{goal}"

This is step {step_number} of a maximum of {max_steps}.

Recent action history (most recent last):
{history_block}
{memory_block}
Look carefully at the current screenshot before deciding. If the history shows \
the same action repeated without visible progress, try a different element, \
scroll to reveal more of the UI, or reconsider whether a dialog/popup needs \
dismissing first. If the goal already appears complete, respond with "done". \
If you are confident the goal is impossible from this screen state, respond \
with "fail" and explain why.

{self.ACTION_SPEC}
"""


# ===========================================================================
# Vision model client (with retries + robust parsing)
# ===========================================================================

# ===========================================================================
# Vision model client (with retries + robust parsing + rate limiting)
# ===========================================================================

class APIRateLimiter:
    def __init__(self, rpm_limit: int):
        self.min_interval = 60.0 / rpm_limit
        self.last_call = 0.0

    def wait(self):
        elapsed = time.time() - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.time()


class GeminiVisionClient:
    """Thin wrapper around the Gemini client adding retries and tolerant JSON parsing."""

    _FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)
    _OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)

    def __init__(self, api_key: str, model: str, max_retries: int, backoff_seconds: float) -> None:
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds

    def decide_next_action(self, image: Image.Image, prompt: str) -> Dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=[image, prompt],
                    config={"response_mime_type": "application/json"},
                )
                return self._parse_response_text(response.text)
            except Exception as exc:  # network errors, malformed JSON, etc.
                last_error = exc
                err_str = str(exc)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    logger.warning("API Quota Exceeded! You have hit the Gemini Free Tier limit (429).")
                    raise AutoPilotError("API Quota Exceeded (429). Please use a paid API key or wait for your quota to reset.")
                
                logger.warning("Gemini call attempt %d/%d failed: %s", attempt, self.max_retries, str(exc)[:200])
                if attempt < self.max_retries:
                    time.sleep(self.backoff_seconds * attempt)  # simple linear backoff
        raise ModelResponseError(f"Vision model call failed after {self.max_retries} attempts: {last_error}")

    def _parse_response_text(self, raw_text: Optional[str]) -> Dict[str, Any]:
        if not raw_text:
            raise ModelResponseError("Empty response from vision model.")

        text = raw_text.strip()

        # First attempt: parse as-is.
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Second attempt: strip markdown code fences the model sometimes adds anyway.
        stripped = self._FENCE_RE.sub("", text).strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

        # Third attempt: extract the first {...} blob found anywhere in the text.
        match = self._OBJECT_RE.search(stripped)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        raise ModelResponseError(f"Could not parse a JSON action from model output: {text[:300]!r}")


# ===========================================================================
# Action validation + execution
# ===========================================================================

class ActionExecutor:
    """Validates parsed actions against the real screen and executes them safely."""

    def __init__(self, screen_w: int, screen_h: int, config: AutoPilotConfig) -> None:
        self.screen_w = screen_w
        self.screen_h = screen_h
        self.config = config

    def _box_to_point(self, box: List[float]) -> Tuple[int, int]:
        if not box or len(box) != 4:
            return self.screen_w // 2, self.screen_h // 2
        ymin, xmin, ymax, xmax = box
        cx = (xmin + xmax) / 2.0
        cy = (ymin + ymax) / 2.0
        x = int((cx / 1000.0) * self.screen_w)
        y = int((cy / 1000.0) * self.screen_h)
        x = max(0, min(self.screen_w - 1, x))
        y = max(0, min(self.screen_h - 1, y))
        return x, y

    def execute(self, data: Dict[str, Any]) -> Tuple[str, Optional[List[float]], str]:
        """
        Execute one parsed action.
        Returns (human_readable_message, target_box_or_None, detail_string).
        Raises ActionExecutionError on invalid/unsafe input.
        """
        action = data.get("action")
        reason = data.get("reason", "")

        if action not in VALID_ACTIONS:
            raise ActionExecutionError(f"Unknown or missing action type: {action!r}")

        if action in ("click", "double_click", "right_click", "move"):
            box = data.get("box_2d")
            x, y = self._box_to_point(box)
            from actions.computer_control import computer_control
            params = {"action": action, "x": x, "y": y}
            computer_control(params, player=None)
            msg = f"AutoPilot executed {action} at ({x}, {y}). Reason: {reason}"
            return msg, box, f"({x},{y})"

        if action == "drag":
            start_box = data.get("start_box_2d")
            end_box = data.get("end_box_2d")
            if not start_box or not end_box:
                raise ActionExecutionError("drag action requires both start_box_2d and end_box_2d.")
            sx, sy = self._box_to_point(start_box)
            ex, ey = self._box_to_point(end_box)
            from actions.computer_control import computer_control
            params = {"action": "drag", "x1": sx, "y1": sy, "x2": ex, "y2": ey}
            computer_control(params, player=None)
            msg = f"AutoPilot dragged from ({sx},{sy}) to ({ex},{ey}). Reason: {reason}"
            return msg, end_box, f"({sx},{sy})->({ex},{ey})"

        if action == "type":
            text = data.get("text", "")
            if not isinstance(text, str):
                raise ActionExecutionError("type action requires a string 'text' field.")
            from actions.computer_control import computer_control
            params = {"action": "smart_type", "text": text}
            computer_control(params, player=None)
            msg = f"AutoPilot typed text successfully. Reason: {reason}"
            return msg, None, text[:60]

        if action == "press":
            key = data.get("key", "")
            if not key:
                raise ActionExecutionError("press action requires a non-empty 'key' field.")
            from actions.computer_control import computer_control
            params = {"action": "press", "keys": key}
            computer_control(params, player=None)
            msg = f"AutoPilot pressed key '{key}'. Reason: {reason}"
            return msg, None, key

        if action == "hotkey":
            keys = data.get("keys")
            if not keys or not isinstance(keys, list):
                raise ActionExecutionError("hotkey action requires a non-empty list of 'keys'.")
            from actions.computer_control import computer_control
            params = {"action": "hotkey", "keys": "+".join(keys)}
            computer_control(params, player=None)
            msg = f"AutoPilot pressed hotkey combo {'+'.join(keys)}. Reason: {reason}"
            return msg, None, "+".join(keys)

        if action == "scroll":
            direction = data.get("direction", "down")
            amount = int(data.get("amount", 5) or 5)
            clicks = amount if direction == "up" else -amount
            from actions.computer_control import computer_control
            params = {"action": "scroll", "clicks": clicks}
            computer_control(params, player=None)
            msg = f"AutoPilot scrolled {direction} by {amount}. Reason: {reason}"
            return msg, None, f"{direction}:{amount}"

        if action == "wait":
            seconds = float(data.get("seconds", 1.0) or 1.0)
            seconds = max(0.0, min(10.0, seconds))  # safety cap so a bad value can't stall the loop forever
            from actions.computer_control import computer_control
            params = {"action": "wait", "duration": seconds}
            computer_control(params, player=None)
            msg = f"AutoPilot waited {seconds:.1f}s. Reason: {reason}"
            return msg, None, f"{seconds:.1f}s"

        # "done" / "fail" are handled by the orchestrator, not here.
        raise ActionExecutionError(f"Action '{action}' should be handled by the orchestrator.")


# ===========================================================================
# Callback safety helpers
# ===========================================================================

def _safe_call(callback: Optional[Callable], *args: Any, **kwargs: Any) -> None:
    """Invoke a caller-supplied callback without ever letting it crash the loop."""
    if callback is None:
        return
    try:
        callback(*args, **kwargs)
    except TypeError:
        # Caller's callback may have a different arity — fall back to a single string.
        try:
            callback(" ".join(str(a) for a in args))
        except Exception:
            logger.debug("Callback %r could not be invoked even with fallback signature.", callback)
    except Exception:
        logger.debug("Callback %r raised an exception:\n%s", callback, traceback.format_exc())


def _fetch_persistent_memory(get_memory_callback: Optional[Callable], goal: str) -> Any:
    if get_memory_callback is None:
        return None
    try:
        return get_memory_callback(goal)
    except TypeError:
        try:
            return get_memory_callback()
        except Exception:
            return None
    except Exception:
        return None


# ===========================================================================
# Main entry point
# ===========================================================================

def autopilot(
    parameters: dict[str, Any],
    ui_callback,
    dashboard_callback,
    send_log_callback,
    get_memory_callback,
) -> str:
    """
    Executes a continuous visual autonomous loop to achieve a goal.

    This preserves the original signature and contract: a single string
    summary is returned describing how the run ended. Everything happening
    internally — looping, retries, history, validation, and the expanded
    action set — is new.
    """
    goal = (parameters.get("goal") or "").strip()
    if not goal:
        return "No goal provided for autopilot."

    api_key = _get_api_key()
    if not api_key:
        return "No Gemini API key found. Cannot run autopilot."

    config = AutoPilotConfig.from_parameters(parameters)

    try:
        vision_client = GeminiVisionClient(
            api_key=api_key,
            model=config.model,
            max_retries=config.max_api_retries,
            backoff_seconds=config.api_retry_backoff_seconds,
        )
    except Exception as exc:
        msg = f"Failed to initialize Gemini client: {exc}"
        _safe_call(ui_callback, msg)
        return msg

    capture = ScreenCapture(monitor_index=config.monitor_index, max_dimension=config.max_image_dimension)
    memory = ActionMemory(config.history_window, config.stuck_repeat_threshold)
    prompt_builder = PromptBuilder(memory)
    persistent_memory = _fetch_persistent_memory(get_memory_callback, goal)
    
    # Throttle requests to stay just under the 15 RPM Free Tier limit (14 RPM)
    rate_limiter = APIRateLimiter(rpm_limit=14)

    _safe_call(ui_callback, f"AutoPilot engaged. Goal: {goal}")
    _safe_call(send_log_callback, f"[AutoPilot] Starting run for goal: {goal!r} (max_steps={config.max_steps})")
    _safe_call(dashboard_callback, {"event": "start", "goal": goal, "max_steps": config.max_steps})

    pre_action_image: Optional[Image.Image] = None

    for step in range(1, config.max_steps + 1):
        try:
            # 1. Take a screenshot (downscaled for the model, native size for clicking).
            model_image, screen_w, screen_h = capture.capture_for_model()
            pre_action_image = model_image

            # 2. Build the prompt with rolling history + persistent memory context.
            prompt = prompt_builder.build(
                goal=goal,
                step_number=step,
                max_steps=config.max_steps,
                persistent_memory=persistent_memory,
            )

            # 3. Ask Gemini for exactly one next action (with rate limiting).
            rate_limiter.wait()
            data = vision_client.decide_next_action(model_image, prompt)
            action = data.get("action")
            reason = data.get("reason", "")

            log_msg = f"[AutoPilot Step {step}/{config.max_steps}] Action: {action} | Reason: {reason}"
            logger.info(log_msg)
            _safe_call(ui_callback, log_msg)
            _safe_call(send_log_callback, log_msg)
            _safe_call(dashboard_callback, {"event": "decision", "step": step, "action": action, "reason": reason})

            # 4. Terminal actions short-circuit the loop immediately.
            if action == "done":
                msg = f"AutoPilot completed successfully after {step} step(s). Reason: {reason}"
                _safe_call(ui_callback, msg)
                _safe_call(send_log_callback, msg)
                _safe_call(dashboard_callback, {"event": "done", "step": step, "reason": reason})
                return msg

            if action == "fail":
                msg = f"AutoPilot stopped after {step} step(s) — goal reported unreachable. Reason: {reason}"
                _safe_call(ui_callback, msg)
                _safe_call(send_log_callback, msg)
                _safe_call(dashboard_callback, {"event": "fail", "step": step, "reason": reason})
                return msg

            # 5. Validate + execute the action against the real screen.
            executor = ActionExecutor(screen_w, screen_h, config)
            try:
                exec_msg, target_box, detail = executor.execute(data)
                success = True
                error_text = None
            except ActionExecutionError as exec_err:
                exec_msg = f"Skipped invalid action '{action}': {exec_err}"
                target_box = data.get("box_2d")
                detail = str(exec_err)
                success = False
                error_text = str(exec_err)

            time.sleep(config.action_settle_seconds)  # let the UI react before the next screenshot

            # 6. Optionally measure whether the screen actually changed (diagnostic only).
            screen_changed: Optional[bool] = None
            if success and config.verify_with_diff and pre_action_image is not None:
                try:
                    post_image, _, _ = capture.capture_for_model()
                    diff_score = ScreenCapture.quick_diff_score(pre_action_image, post_image)
                    screen_changed = diff_score > 0.02
                except Exception:
                    screen_changed = None

            # 7. Record this step for history + stuck-loop detection.
            record = StepRecord(
                step_index=step,
                action=action,
                reason=reason,
                target_box=target_box,
                detail=detail,
                success=success,
                error=error_text,
                screen_changed=screen_changed,
            )
            memory.add(record)

            _safe_call(ui_callback, exec_msg)
            _safe_call(send_log_callback, exec_msg)
            _safe_call(
                dashboard_callback,
                {
                    "event": "executed",
                    "step": step,
                    "action": action,
                    "success": success,
                    "screen_changed": screen_changed,
                },
            )

            if not success:
                # Invalid action from the model — keep looping so it can self-correct
                # next step, but don't silently pretend it worked.
                continue

            # 8. Stuck-loop detection: stop wasting steps repeating a no-op action.
            if memory.is_stuck():
                msg = (
                    f"AutoPilot stopped after {step} step(s): detected a repeated, "
                    f"non-progressing action ({action}). The agent may need a different "
                    f"strategy or human intervention."
                )
                _safe_call(ui_callback, msg)
                _safe_call(send_log_callback, msg)
                _safe_call(dashboard_callback, {"event": "stuck", "step": step})
                return msg

        except (ScreenCaptureError, ModelResponseError) as known_err:
            err = f"AutoPilot encountered a recoverable error at step {step}: {known_err}"
            logger.warning(err)
            _safe_call(ui_callback, err)
            _safe_call(send_log_callback, err)
            _safe_call(dashboard_callback, {"event": "error", "step": step, "error": str(known_err)})
            # Recoverable: try again next iteration rather than aborting the whole run.
            continue
            
        except AutoPilotError as ap_err:
            # Cleanly catch explicitly raised AutoPilotErrors (like 429 Quota Exceeded)
            err = f"AutoPilot stopped: {ap_err}"
            logger.warning(err)
            _safe_call(ui_callback, err)
            _safe_call(send_log_callback, err)
            _safe_call(dashboard_callback, {"event": "fatal_error", "step": step, "error": str(ap_err)})
            return err

        except Exception as exc:  # truly unexpected — abort the run, matching original safety behavior
            err = f"AutoPilot encountered an unexpected error: {exc}"
            logger.error("%s\n%s", err, traceback.format_exc())
            _safe_call(ui_callback, err)
            _safe_call(send_log_callback, err)
            _safe_call(dashboard_callback, {"event": "fatal_error", "step": step, "error": str(exc)})
            return err

    msg = f"AutoPilot reached the maximum of {config.max_steps} steps without confirming completion."
    _safe_call(ui_callback, msg)
    _safe_call(send_log_callback, msg)
    _safe_call(dashboard_callback, {"event": "max_steps_reached", "max_steps": config.max_steps})
    return msg


# ===========================================================================
# Manual smoke test (does not run unless this file is executed directly)
# ===========================================================================

if __name__ == "__main__":
    def _demo_ui(msg: str) -> None:
        print(f"[UI] {msg}")

    def _demo_dashboard(payload: Any) -> None:
        print(f"[DASHBOARD] {payload}")

    def _demo_log(msg: str) -> None:
        print(f"[LOG] {msg}")

    def _demo_memory(goal: str) -> Any:
        return {"notes": "no prior context for this demo run", "goal": goal}

    result = autopilot(
        {"goal": "Open the Start menu", "max_steps": 5},
        ui_callback=_demo_ui,
        dashboard_callback=_demo_dashboard,
        send_log_callback=_demo_log,
        get_memory_callback=_demo_memory,
    )
    print("RESULT:", result)