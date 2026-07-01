<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:1a0033,50:2d0a4e,100:3d1466&height=260&section=header&text=I.N.D.R.A.&fontSize=75&fontColor=D9A5FF&animation=fadeIn&fontAlignY=36&desc=Intelligent%20Neural%20Dynamic%20Response%20Assistant&descAlignY=58&descSize=18" width="100%"/>

<img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=600&size=22&duration=3000&pause=800&color=C084FC&center=true&vCenter=true&width=750&lines=A+JARVIS-style+AI+assistant+for+your+desktop;Real-time+voice%2C+vision%2C+and+system+control;Built+on+Google+Gemini+Live+API+%2B+PyQt6;Say+the+word.+I.N.D.R.A.+listens." alt="Typing SVG" />

<br/>

<img src="https://img.shields.io/badge/PYTHON-3.10+-8B5CF6?style=for-the-badge&logo=python&logoColor=white&labelColor=1a0033"/>
<img src="https://img.shields.io/badge/PyQt6-UI%20FRAMEWORK-C084FC?style=for-the-badge&logo=qt&logoColor=white&labelColor=1a0033"/>
<img src="https://img.shields.io/badge/Gemini%20Live%20API-VOICE%20ENGINE-D9A5FF?style=for-the-badge&logo=google&logoColor=white&labelColor=1a0033"/>
<img src="https://img.shields.io/badge/STATUS-ACTIVE%20DEVELOPMENT-8B5CF6?style=for-the-badge&labelColor=1a0033"/>

</div>

<br/>

## 🌌 Overview

**I.N.D.R.A.** is a JARVIS-inspired AI assistant that lives on your desktop — not a chatbot in a browser tab, but a full animated system with a floating HUD, real-time voice conversation, vision, and deep OS-level control. Built around Google's Gemini Live API for native audio streaming, wrapped in a PyQt6 interface designed to feel like something out of a sci-fi command center.

Speak to it. It listens, responds in real time, opens panels, checks your system, watches through your webcam, browses the web, and runs tasks — all through natural voice commands.

<br/>

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

**🎙️ Voice-Activated Core**
Real-time audio streaming powered by Gemini Live API — natural, low-latency conversation, no typing required.

</td>
<td width="50%" valign="top">

**🖥️ Animated HUD**
Floating widget panels — System Monitor, Activity Log, Time Panel, Vision — that open and close on command with smooth animation.

</td>
</tr>
<tr>
<td width="50%" valign="top">

**🌐 Remote Dashboard**
Access I.N.D.R.A.'s dashboard from anywhere via Ngrok tunneling — monitor and interact remotely.

</td>
<td width="50%" valign="top">

**🛠️ Tool System**
Open apps, search the web, control media playback, run autopilot task sequences, and extend with custom tools.

</td>
</tr>
<tr>
<td width="50%" valign="top">

**📷 Camera Vision**
Real-time webcam feed integration — I.N.D.R.A. can see and respond to what's in front of it.

</td>
<td width="50%" valign="top">

**📁 File & Email Agent**
Built-in file processing and email handling agents for hands-free task automation.

</td>
</tr>
</table>

<br/>

## 🛠️ Tech Stack

<div align="center">

| Layer | Technology |
|---|---|
| **Voice Engine** | Google Gemini Live API (native audio) |
| **UI Framework** | PyQt6 — animated, frameless HUD |
| **Remote Access** | FastAPI + Uvicorn + Ngrok |
| **Audio I/O** | sounddevice / soundfile |
| **System Control** | psutil, pyautogui, pynput |
| **Vision** | OpenCV |

</div>

<br/>

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- A Google Gemini API key

### Installation

```bash
# Clone the repository
git clone https://github.com/TejHorwDev/INDRA.git
cd INDRA

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Add your Gemini API key to `config/api_keys.json`:

```json
{
  "gemini_api_key": "YOUR_API_KEY_HERE"
}
```

### Run

```bash
python main.py
```

<br/>

## 🎙️ Voice Commands

<div align="center">

| Command | Action |
|---|---|
| `"Open the activity log"` | Opens the Activity Log panel |
| `"Open system monitor"` | Opens the System Monitor panel |
| `"Open the time panel"` | Opens the Time Panel |
| `"Show webcam"` | Activates the Vision panel |
| `"Open all panels"` | Opens the full HUD |
| `"Bye INDRA"` | Shuts down the assistant |

</div>

<br/>

## 🗺️ Roadmap

- [ ] Expand tool system with plugin support
- [ ] Add persistent memory across sessions
- [ ] Mobile companion app for remote control
- [ ] Custom wake-word detection

<br/>

## 📜 License

2026 INDRA COPORATION RIGHT RESERVED

<br/>

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:3d1466,50:2d0a4e,100:1a0033&height=120&section=footer" width="100%"/>

**Built with 💜 by [Tej_horw](https://github.com/TejHorwDev)**

</div>
