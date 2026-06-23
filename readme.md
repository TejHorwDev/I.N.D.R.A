# I.N.D.R.A
**Intelligent Neural Dynamic Response Assistant**

A JARVIS-style AI assistant built with Google Gemini Live API, PyQt6, and Python.

## Features
- Voice-activated AI with real-time audio streaming
- Animated HUD with floating widget panels (System Monitor, Activity Log, Time Panel, Vision, etc.)
- Voice commands to open/close UI panels
- Remote dashboard via Ngrok
- Tool system: open apps, search web, control media, run autopilot tasks, and much more
- Camera vision, file processing, email agent, and more

## Setup
1. Install requirements: `pip install -r requirements.txt`
2. Add your Gemini API key to `config/api_keys.json`
3. Run: `python main.py`

## Voice Commands (examples)
- "Open the activity log"
- "Open system monitor"
- "Open the time panel"
- "Show webcam"
- "Open all panels"
- "Bye INDRA" — shuts down

## Tech Stack
- Google Gemini Live API (native audio)
- PyQt6 (animated UI)
- FastAPI + Uvicorn (remote dashboard)
- sounddevice / soundfile (audio I/O)
- psutil, OpenCV, pynput, pyautogui