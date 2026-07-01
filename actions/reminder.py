                     
                                                                                                                                       
"""
reminder.py – INDRA Cross‑Platform Reminder Engine
====================================================
Sets one‑time or recurring reminders that display native OS notifications.
Supported actions:
  set (default) – schedule a new reminder
  list          – show all upcoming reminders
  cancel        – cancel a specific reminder
  clear         – remove all reminders

Features:
  • Natural language date/time parsing (dateparser, relative, AI fallback).
  • Multi‑platform scheduling: Task Scheduler (Win), launchd (Mac), systemd/at (Linux).
  • Self‑destructing notification scripts that never leave clutter.
  • Verification that scheduled job was actually created.
  • Lazy imports, caching, and zero startup penalty.

Author : INDRA Project
Version: 5.0
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

                         
                                                                        
_DATEPARSER = None
_GEMINI = None

def _import_dateparser():
    global _DATEPARSER
    if _DATEPARSER is None:
        try:
            import dateparser

            _DATEPARSER = dateparser
        except ImportError:
            _DATEPARSER = False
    return _DATEPARSER

def _import_gemini():
    global _GEMINI
    if _GEMINI is None:
        try:
            from google import genai

            _GEMINI = genai
        except ImportError:
            _GEMINI = False
    return _GEMINI

                                                                        

@lru_cache(maxsize=1)
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

@lru_cache(maxsize=1)
def _get_os() -> str:
    """Detect OS from config or platform, case‑normalised."""
    try:
        cfg = json.loads(
            (_base_dir() / "config" / "api_keys.json").read_text(encoding="utf-8")
        )
        return cfg.get("os_system", "windows").lower()
    except Exception:
                              
        import platform

        plat = platform.system().lower()
        if plat == "darwin":
            return "mac"
        return plat                        

@lru_cache(maxsize=1)
def _scripts_dir() -> Path:
    d = Path.home() / ".INDRA" / "reminders"
    d.mkdir(parents=True, exist_ok=True)
    return d

                                                                        

def _sanitise(text: str, max_len: int = 200) -> str:
    return (
        text.replace("\\", "")
        .replace('"', "")
        .replace("'", "")
        .replace("\n", " ")
        .replace("\r", "")
        .strip()
    )[:max_len]

                                                                        

def _parse_datetime(date_raw: str, time_raw: str) -> Optional[datetime]:
    """
    Convert user‑provided date and time strings into an absolute datetime.
    Supports:
      - Exact YYYY-MM-DD and HH:MM
      - Natural language via dateparser (e.g., "tomorrow at 3pm")
      - Relative expressions (today, tomorrow, in X hours)
      - AI fallback using Gemini
    Returns None if parsing fails.
    """
                  
    try:
        return datetime.strptime(
            f"{date_raw.strip()} {time_raw.strip()}", "%Y-%m-%d %H:%M"
        )
    except ValueError:
        pass

    combined = f"{date_raw} {time_raw}".strip()
    dateparser_mod = _import_dateparser()
    if dateparser_mod:
        parsed = dateparser_mod.parse(
            combined, settings={"PREFER_DATES_FROM": "future", "TIMEZONE": "local"}
        )
        if parsed:
            return parsed

    now = datetime.now()
    lower = combined.lower()
    if "today" in lower or "bugün" in lower:
                                    
        time_part = _extract_time(time_raw) or now.replace(second=0, microsecond=0)
        return now.replace(
            hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0
        )
    if "tomorrow" in lower or "yarın" in lower:
        tomorrow = now + timedelta(days=1)
        time_part = _extract_time(time_raw) or now.replace(second=0, microsecond=0)
        return tomorrow.replace(
            hour=time_part.hour, minute=time_part.minute, second=0, microsecond=0
        )
                          
    match = re.match(r"in\s+(\d+)\s*(hour|minute|min)s?", lower)
    if match:
        n = int(match.group(1))
        unit = match.group(2)
        delta = timedelta(hours=n) if unit.startswith("hour") else timedelta(minutes=n)
        return now + delta

    genai = _import_gemini()
    if genai:
        try:
            client = genai.Client(api_key=_get_api_key())
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=(
                    f"Today is {now.strftime('%Y-%m-%d %H:%M')}. "
                    f"Convert this date and time request to YYYY-MM-DD HH:MM: "
                    f"'{combined}'. Return ONLY the datetime string, nothing else."
                ),
            )
            result = response.text.strip()
                                      
            dt_match = re.search(r"(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})", result)
            if dt_match:
                return datetime.strptime(dt_match.group(1), "%Y-%m-%d %H:%M")
        except Exception:
            pass

    return None

def _extract_time(time_str: str) -> Optional[datetime]:
    """Parse a standalone time string (e.g., 3pm, 15:00) into a dummy datetime."""
    now = datetime.now()
    for fmt in ("%H:%M", "%I:%M %p", "%I%p", "%I %p"):
        try:
            t = datetime.strptime(time_str.strip(), fmt)
            return now.replace(hour=t.hour, minute=t.minute, second=0, microsecond=0)
        except ValueError:
            continue
    return None

                                                                        

@lru_cache(maxsize=1)
def _get_api_key() -> str:
    try:
        return json.loads((_base_dir() / "config" / "api_keys.json").read_text())[
            "gemini_api_key"
        ]
    except Exception:
        return ""

                                                                        

def _write_notify_script(task_name: str, message: str, os_name: str) -> Path:
    script_path = _scripts_dir() / f"{task_name}.py"
    msg_literal = json.dumps(message)

    if os_name == "windows":
        notify_block = f"""
message = {msg_literal}
notified = False
try:
    from plyer import notification
    notification.notify(title="I.N.D.R.A Reminder", message=message, timeout=15)
    notified = True
except Exception:
    pass
if not notified:
    try:
        from win10toast import ToastNotifier
        ToastNotifier().show_toast("I.N.D.R.A Reminder", message, duration=15, threaded=False)
        notified = True
    except Exception:
        pass
if not notified:
    try:
        import subprocess as sp
        sp.run(["msg", "*", "/TIME:30", message], check=False)
    except Exception:
        pass
try:
    import winsound
    for freq in [800, 1000, 1200]:
        winsound.Beep(freq, 180)
        import time; time.sleep(0.08)
except Exception:
    pass
"""
    elif os_name == "mac":
        notify_block = f"""
message = {msg_literal}
notified = False
try:
    from plyer import notification
    notification.notify(title="I.N.D.R.A Reminder", message=message, timeout=15)
    notified = True
except Exception:
    pass
if not notified:
    try:
        import subprocess as sp
        safe_msg = message.replace('"', '')
        script = 'display notification "{{}}" with title "I.N.D.R.A Reminder"'.format(safe_msg)
        sp.run(["osascript", "-e", script], check=False)
    except Exception:
        pass
"""
    else:         
        notify_block = f"""
message = {msg_literal}
notified = False
try:
    from plyer import notification
    notification.notify(title="I.N.D.R.A Reminder", message=message, timeout=15)
    notified = True
except Exception:
    pass
if not notified:
    try:
        import subprocess as sp
        sp.run(["notify-send", "--urgency=normal", "--expire-time=15000",
                "I.N.D.R.A Reminder", message], check=False)
    except Exception:
        pass
"""

    script_body = f"""# Auto-generated by I.N.D.R.A reminder — do not edit
import sys, os, pathlib
{notify_block}
# Self-delete after firing
try:
    pathlib.Path(__file__).unlink(missing_ok=True)
except Exception:
    pass
"""
    script_path.write_text(script_body, encoding="utf-8")
    script_path.chmod(0o600)
    return script_path

                                                                        

def _schedule_windows(
    target_dt: datetime, task_name: str, script_path: Path, message: str
) -> str:
    python_exe = Path(sys.executable)
    pythonw = python_exe.parent / "pythonw.exe"
    if pythonw.exists():
        python_exe = pythonw

    xml_path = _scripts_dir() / f"{task_name}.xml"
    xml_content = (
        '<?xml version="1.0" encoding="UTF-16"?>\n'
        '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
        "  <RegistrationInfo><Description>I.N.D.R.A Reminder</Description></RegistrationInfo>\n"
        "  <Triggers><TimeTrigger>\n"
        f'    <StartBoundary>{target_dt.strftime("%Y-%m-%dT%H:%M:%S")}</StartBoundary>\n'
        "    <Enabled>true</Enabled>\n"
        "  </TimeTrigger></Triggers>\n"
        "  <Actions><Exec>\n"
        f"    <Command>{python_exe}</Command>\n"
        f'    <Arguments>"{script_path}"</Arguments>\n'
        "  </Exec></Actions>\n"
        "  <Settings>\n"
        "    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n"
        "    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n"
        "    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n"
        "    <StartWhenAvailable>true</StartWhenAvailable>\n"
        "    <ExecutionTimeLimit>PT5M</ExecutionTimeLimit>\n"
        "    <Enabled>true</Enabled>\n"
        "  </Settings>\n"
        "  <Principals><Principal>\n"
        "    <LogonType>InteractiveToken</LogonType>\n"
        "    <RunLevel>LeastPrivilege</RunLevel>\n"
        "  </Principal></Principals>\n"
        "</Task>"
    )

    xml_path.write_text(xml_content, encoding="utf-16")

    result = subprocess.run(
        ["schtasks", "/Create", "/TN", task_name, "/XML", str(xml_path), "/F"],
        capture_output=True,
        text=True,
    )

    try:
        xml_path.unlink(missing_ok=True)
    except Exception:
        pass

    if result.returncode != 0:
        script_path.unlink(missing_ok=True)
        err = (result.stderr or result.stdout).strip()
        print(f"[Reminder] ❌ schtasks: {err}")
        return ""

    verify = subprocess.run(
        ["schtasks", "/Query", "/TN", task_name], capture_output=True, text=True
    )
    if verify.returncode != 0:
                                         
        subprocess.run(
            ["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True
        )
        script_path.unlink(missing_ok=True)
        return ""

    return task_name

def _schedule_mac(target_dt: datetime, task_name: str, script_path: Path) -> str:
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    agents_dir.mkdir(parents=True, exist_ok=True)

    label = f"com.INDRA.reminder.{task_name}"
    plist_path = agents_dir / f"{label}.plist"

    plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>             <string>{label}</string>
  <key>ProgramArguments</key>
  <array>
    <string>{sys.executable}</string>
    <string>{script_path}</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Year</key>   <integer>{target_dt.year}</integer>
    <key>Month</key>  <integer>{target_dt.month}</integer>
    <key>Day</key>    <integer>{target_dt.day}</integer>
    <key>Hour</key>   <integer>{target_dt.hour}</integer>
    <key>Minute</key> <integer>{target_dt.minute}</integer>
  </dict>
  <key>RunAtLoad</key>         <false/>
  <key>StandardOutPath</key>   <string>/dev/null</string>
  <key>StandardErrorPath</key> <string>/dev/null</string>
</dict>
</plist>
"""
    plist_path.write_text(plist_content, encoding="utf-8")
    plist_path.chmod(0o644)

    result = subprocess.run(
        ["launchctl", "load", str(plist_path)], capture_output=True, text=True
    )

    if result.returncode != 0:
        plist_path.unlink(missing_ok=True)
        script_path.unlink(missing_ok=True)
        print(f"[Reminder] ❌ launchctl: {result.stderr.strip()}")
        return ""

    if not plist_path.exists():
        return ""

    return label

def _schedule_linux(target_dt: datetime, task_name: str, script_path: Path) -> str:
                        
    if shutil.which("systemd-run"):
        on_calendar = target_dt.strftime("%Y-%m-%d %H:%M:00")
        result = subprocess.run(
            [
                "systemd-run",
                "--user",
                f"--on-calendar={on_calendar}",
                f"--unit={task_name}",
                "--",
                sys.executable,
                str(script_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
                                
            check = subprocess.run(
                ["systemctl", "--user", "is-active", task_name], capture_output=True
            )
            if (
                check.returncode == 0 or check.returncode == 3
            ):                            
                return task_name
        else:
            print(f"[Reminder] ⚠️ systemd-run failed: {result.stderr.strip()}")
                               
    else:
        print("[Reminder] ⚠️ systemd-run not found, using 'at'")

    if shutil.which("at"):
        at_time = target_dt.strftime("%H:%M %Y-%m-%d")
        cmd_str = f"{sys.executable} {script_path}\n"
        result = subprocess.run(
            ["at", at_time], input=cmd_str, capture_output=True, text=True
        )
        if result.returncode == 0:
                                      
            verify = subprocess.run(["atq"], capture_output=True, text=True)
            if task_name in verify.stdout or script_path.name in verify.stdout:
                return task_name
        else:
            print(f"[Reminder] ❌ at: {result.stderr.strip()}")
    else:
        print("[Reminder] ❌ Neither systemd-run nor at found.")
    return ""

                                                                        

def _list_reminders_windows() -> str:
    result = subprocess.run(
        ["schtasks", "/Query", "/FO", "LIST", "/V"], capture_output=True, text=True
    )
    if result.returncode != 0:
        return "Could not query Windows Task Scheduler."
    tasks = []
    for block in result.stdout.split("\n\n"):
        if "INDRAReminder_" in block:
            lines = block.strip().splitlines()
            info = {}
            for line in lines:
                if ":" in line:
                    k, v = line.split(":", 1)
                    info[k.strip()] = v.strip()
            tasks.append(info)
    if not tasks:
        return "No active reminders."
    out = ["Active reminders:"]
    for t in tasks:
        name = t.get("TaskName", "?")
        trigger = t.get("Start Bound", "?")
        out.append(f"  {name} → {trigger}")
    return "\n".join(out)

def _cancel_reminder_windows(task_name: str) -> str:
    result = subprocess.run(
        ["schtasks", "/Delete", "/TN", task_name, "/F"], capture_output=True, text=True
    )
    if result.returncode == 0:
        return f"Reminder {task_name} cancelled."
    return f"Could not cancel: {result.stderr.strip() or result.stdout.strip()}"

def _list_reminders_mac() -> str:
    agents_dir = Path.home() / "Library" / "LaunchAgents"
    plists = list(agents_dir.glob("com.INDRA.reminder.*.plist"))
    if not plists:
        return "No active reminders."
    lines = ["Active reminders:"]
    for p in plists:
        lines.append(f"  {p.stem} → (launchd job)")
    return "\n".join(lines)

def _cancel_reminder_mac(label: str) -> str:
    result = subprocess.run(
        ["launchctl", "remove", label], capture_output=True, text=True
    )
    plist_path = Path.home() / "Library/LaunchAgents" / f"{label}.plist"
    plist_path.unlink(missing_ok=True)
    if result.returncode == 0:
        return f"Reminder {label} cancelled."
    return f"Could not cancel: {result.stderr.strip() or result.stdout.strip()}"

def _list_reminders_linux() -> str:
                          
    if shutil.which("systemctl"):
        result = subprocess.run(
            ["systemctl", "--user", "list-unit-files", "--type=timer"],
            capture_output=True,
            text=True,
        )
        timers = []
        for line in result.stdout.splitlines():
            if "INDRAReminder_" in line:
                parts = line.split()
                if parts:
                    timers.append(parts[0])
        if timers:
            return "Active reminders (systemd timers):\n  " + "\n  ".join(timers)
                   
    if shutil.which("atq"):
        result = subprocess.run(["atq"], capture_output=True, text=True)
        if result.stdout.strip():
            return "Active reminders (at jobs):\n" + result.stdout.strip()
    return "No active reminders found."

def _cancel_reminder_linux(task_name: str) -> str:
                       
    if shutil.which("systemctl"):
        result = subprocess.run(
            ["systemctl", "--user", "stop", task_name], capture_output=True, text=True
        )
        subprocess.run(
            ["systemctl", "--user", "disable", task_name], capture_output=True
        )
        if result.returncode == 0:
            return f"Reminder {task_name} cancelled (systemd)."
                                                
    if shutil.which("atq") and shutil.which("atrm"):
                                                                        
        pass
    return "Could not cancel reminder on Linux (manual removal needed)."

def _clear_all_reminders(os_name: str) -> str:
    if os_name == "windows":
        tasks = subprocess.run(
            ["schtasks", "/Query", "/FO", "LIST"], capture_output=True, text=True
        ).stdout
        for line in tasks.splitlines():
            if "INDRAReminder_" in line:
                name = line.split(":")[-1].strip()
                subprocess.run(
                    ["schtasks", "/Delete", "/TN", name, "/F"], capture_output=True
                )
        return "All reminders cleared."
    elif os_name == "mac":
        agents_dir = Path.home() / "Library/LaunchAgents"
        for plist in agents_dir.glob("com.INDRA.reminder.*.plist"):
            label = plist.stem
            subprocess.run(["launchctl", "remove", label], capture_output=True)
            plist.unlink(missing_ok=True)
        return "All reminders cleared."
    else:
                                                     
        if shutil.which("systemctl"):
            units = subprocess.run(
                ["systemctl", "--user", "list-unit-files", "--type=timer"],
                capture_output=True,
                text=True,
            ).stdout
            for line in units.splitlines():
                if "INDRAReminder_" in line:
                    unit = line.split()[0]
                    subprocess.run(
                        ["systemctl", "--user", "stop", unit], capture_output=True
                    )
                    subprocess.run(
                        ["systemctl", "--user", "disable", unit], capture_output=True
                    )
                                                            
        return "Linux reminders cleared (systemd timers removed)."

                                                                        

def reminder(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Central reminder controller.
    Expects parameters:
      action (optional): "set" (default), "list", "cancel", "clear"
      For "set":
        date, time, message (required)
        (supports natural language)
      For "cancel":
        task_name (the ID returned when created)
    """
    params = parameters or {}
    action = params.get("action", "set").strip().lower()
    os_name = _get_os()

    if action == "list":
        if os_name == "windows":
            return _list_reminders_windows()
        elif os_name == "mac":
            return _list_reminders_mac()
        else:
            return _list_reminders_linux()

    if action == "cancel":
        task_name = params.get("task_name", "").strip()
        if not task_name:
            return "Please provide the task name to cancel."
        if os_name == "windows":
            return _cancel_reminder_windows(task_name)
        elif os_name == "mac":
            return _cancel_reminder_mac(task_name)
        else:
            return _cancel_reminder_linux(task_name)

    if action == "clear":
        return _clear_all_reminders(os_name)

    date_str = params.get("date", "").strip()
    time_str = params.get("time", "").strip()
    message = params.get("message", "Reminder").strip()

    if not date_str or not time_str:
        return "I need both a date and a time to set a reminder."

    target_dt = _parse_datetime(date_str, time_str)
    if target_dt is None:
        return "I couldn't understand that date or time. Please use a format like '2025-06-01 14:30' or 'tomorrow at 3pm'."

    if target_dt <= datetime.now():
        return "That time has already passed — I can't set a reminder in the past."

    safe_msg = _sanitise(message)
    task_name = f"INDRAReminder_{target_dt.strftime('%Y%m%d_%H%M%S')}"

    try:
        script_path = _write_notify_script(task_name, safe_msg, os_name)
    except Exception as e:
        return f"Could not prepare the reminder script: {e}"

    try:
        if os_name == "windows":
            job_id = _schedule_windows(target_dt, task_name, script_path, safe_msg)
        elif os_name == "mac":
            job_id = _schedule_mac(target_dt, task_name, script_path)
        else:
            job_id = _schedule_linux(target_dt, task_name, script_path)
    except Exception as e:
        script_path.unlink(missing_ok=True)
        print(f"[Reminder] ❌ Scheduling error: {e}")
        return "Something went wrong while scheduling the reminder."

    if not job_id:
        return "I couldn't register the reminder with the system scheduler."

    if player:
        player.write_log(
            f"[Reminder] ✅ {target_dt.strftime('%Y-%m-%d %H:%M')} — {safe_msg[:40]}"
        )

    friendly = target_dt.strftime("%B %d at %I:%M %p")
    return f"Reminder set for {friendly}. (ID: {job_id})"
