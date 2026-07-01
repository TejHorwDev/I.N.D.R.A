                     

import json
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus

import numpy as np                                                       
import pyautogui

try:
    import requests

    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    from youtube_transcript_api import YouTubeTranscriptApi

    _TRANSCRIPT_OK = True
except ImportError:
    _TRANSCRIPT_OK = False

from config import get_os, is_linux, is_mac, is_windows

def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

_YT_VIDEO_FILTER = "EgIQAQ%3D%3D"                                

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]

                                                                        

def _open_url(url: str) -> None:
    try:
        if is_mac():
            subprocess.Popen(["open", url])
        elif is_linux():
            subprocess.Popen(["xdg-open", url])
        else:
            subprocess.Popen(["cmd", "/c", "start", "", url], shell=False)
    except Exception as e:
        print(f"[YouTube] ⚠️ open_url failed: {e}")

def _extract_video_id(url: str) -> Optional[str]:
    match = re.search(
        r"(?:v=|\/v\/|youtu\.be\/|\/embed\/|\/shorts\/)([A-Za-z0-9_-]{11})", url
    )
    return match.group(1) if match else None

def _is_valid_youtube_url(url: str) -> bool:
    return bool(re.search(r"(youtube\.com|youtu\.be)", url or ""))

def _ask_for_url(prompt_text: str = "YouTube video URL:") -> Optional[str]:
    try:
        import tkinter as tk
        from tkinter import simpledialog

        root = tk._default_root
        if root is None:
            root = tk.Tk()
            root.withdraw()

        url = simpledialog.askstring("I.N.D.R.A", prompt_text, parent=root)
        return url.strip() if url else None
    except Exception as e:
        print(f"[YouTube] ⚠️ URL dialog failed: {e}")
        return None

                                                                        

def _scrape_first_video_url(query: str) -> Optional[str]:
    """Return the URL of the first non‑Shorts video for a query."""
    if not _REQUESTS_OK:
        return None
    search_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )
    try:
        r = requests.get(search_url, headers=HEADERS, timeout=10)
        html = r.text
        video_ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
        seen = set()
        for vid in video_ids:
            if vid in seen:
                continue
            seen.add(vid)
            if f"/shorts/{vid}" in html:
                continue
            return f"https://www.youtube.com/watch?v={vid}"
    except Exception as e:
        print(f"[YouTube] ⚠️ scrape_first_video_url failed: {e}")
    return None

def _scrape_search_results(query: str, max_results: int = 5) -> list[dict]:
    """Return a list of dicts with title, url, channel, views, duration for top results."""
    if not _REQUESTS_OK:
        return []
    search_url = (
        f"https://www.youtube.com/results"
        f"?search_query={quote_plus(query)}"
        f"&sp={_YT_VIDEO_FILTER}"
    )
    try:
        r = requests.get(search_url, headers=HEADERS, timeout=10)
        html = r.text
    except Exception as e:
        print(f"[YouTube] ⚠️ search results fetch failed: {e}")
        return []

    results = []

                                                                            
                                                                                           
    video_ids = re.findall(r'"videoId":"([A-Za-z0-9_-]{11})"', html)
    titles = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"', html)

                                                   
    pattern = (
        r'"videoId":"(?P<id>[A-Za-z0-9_-]{11})".*?'
        r'"title":\{"runs":\[\{"text":"(?P<title>[^"]+)"'
    )
    matches = re.finditer(pattern, html, re.DOTALL)
    seen_ids = set()
    for m in matches:
        vid = m.group("id")
        if vid in seen_ids:
            continue
        seen_ids.add(vid)
        title = m.group("title")
                                              
        channel_m = re.search(
            rf'"videoId":"{vid}".*?' r'"ownerText":\{"runs":\[\{"text":"([^"]+)"',
            html,
            re.DOTALL,
        )
        channel = channel_m.group(1) if channel_m else "Unknown"
               
        views_m = re.search(
            rf'"videoId":"{vid}".*?'
            r'"shortViewCountText":\{"runs":\[\{"text":"([^"]+)"',
            html,
            re.DOTALL,
        ) or re.search(
            rf'"videoId":"{vid}".*?' r'"viewCountText":\{"simpleText":"([^"]+)"',
            html,
            re.DOTALL,
        )
        views = views_m.group(1) if views_m else "?"
                  
        dur_m = re.search(
            rf'"videoId":"{vid}".*?' r'"lengthText":\{"simpleText":"([^"]+)"',
            html,
            re.DOTALL,
        ) or re.search(
            rf'"videoId":"{vid}".*?' r'"lengthText":\{"runs":\[\{"text":"([^"]+)"',
            html,
            re.DOTALL,
        )
        duration = dur_m.group(1) if dur_m else "?"
        results.append(
            {
                "title": title,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "channel": channel,
                "views": views,
                "duration": duration,
            }
        )
        if len(results) >= max_results:
            break
    return results

def _scrape_video_info(video_id: str) -> dict:
    """Return dict of title, channel, views, duration, likes for a video."""
    if not _REQUESTS_OK:
        return {}
    url = f"https://www.youtube.com/watch?v={video_id}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text
        info = {}
        for key, pattern in [
            ("title", r'"title":\{"runs":\[\{"text":"([^"]+)"'),
            ("channel", r'"ownerChannelName":"([^"]+)"'),
            ("views", r'"viewCount":"(\d+)"'),
            ("duration", r'"lengthSeconds":"(\d+)"'),
            ("likes", r'"label":"([0-9,]+ likes)"'),
        ]:
            match = re.search(pattern, html)
            if match:
                raw = match.group(1)
                if key == "views":
                    info[key] = f"{int(raw):,}"
                elif key == "duration":
                    secs = int(raw)
                    info[key] = f"{secs // 60}:{secs % 60:02d}"
                else:
                    info[key] = raw
        return info
    except Exception as e:
        print(f"[YouTube] ⚠️ Info scrape failed: {e}")
        return {}

def _scrape_trending(region: str = "TR", max_results: int = 8) -> list[dict]:
    if not _REQUESTS_OK:
        return []
    url = f"https://www.youtube.com/feed/trending?gl={region.upper()}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        html = r.text
        titles = re.findall(r'"title":\{"runs":\[\{"text":"([^"]+)"\}\]', html)
        channels = re.findall(r'"ownerText":\{"runs":\[\{"text":"([^"]+)"', html)

        results, seen = [], set()
        for i, title in enumerate(titles):
            if title in seen or len(title) < 5:
                continue
            seen.add(title)
            channel = channels[i] if i < len(channels) else "Unknown"
            results.append(
                {"rank": len(results) + 1, "title": title, "channel": channel}
            )
            if len(results) >= max_results:
                break
        return results
    except Exception as e:
        print(f"[YouTube] ⚠️ Trending scrape failed: {e}")
        return []

                                                                        

def _get_transcript(video_id: str) -> Optional[str]:
    if not _TRANSCRIPT_OK:
        return None
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None
        lang_priority = [
            "en",
            "tr",
            "de",
            "fr",
            "es",
            "it",
            "pt",
            "ru",
            "ja",
            "ko",
            "ar",
            "zh",
        ]
        try:
            transcript = transcript_list.find_manually_created_transcript(lang_priority)
        except Exception:
            pass
        if transcript is None:
            try:
                transcript = transcript_list.find_generated_transcript(lang_priority)
            except Exception:
                for t in transcript_list:
                    transcript = t
                    break
        if transcript is None:
            return None
        fetched = transcript.fetch()
        return " ".join(entry["text"] for entry in fetched)
    except Exception as e:
        print(f"[YouTube] ⚠️ Transcript fetch failed: {e}")
        return None

def _summarize_with_gemini(transcript: str, video_url: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=(
            "You are INDRA, an AI assistant. "
            "Summarize YouTube video transcripts clearly and concisely. "
            "Structure: 1-sentence overview, then 3-5 key points. "
            "Be direct. Address the user as 'sir'. "
            "Match the language of the transcript."
        ),
    )
    max_chars = 80000
    truncated = transcript[:max_chars] + ("..." if len(transcript) > max_chars else "")
    response = model.generate_content(
        f"Please summarize this YouTube video transcript:\n\n{truncated}"
    )
    return response.text.strip()

def _save_text(content: str, prefix: str) -> str:
    """Save content to Desktop with a timestamped filename."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{ts}.txt"
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename
    filepath.write_text(content, encoding="utf-8")
                                 
    try:
        if is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[YouTube] ⚠️ Could not open text editor: {e}")
    return str(filepath)

def _save_summary(content: str, video_url: str) -> str:
    header = (
        f"INDRA — YouTube Summary\n"
        f"{'─' * 50}\n"
        f"URL    : {video_url}\n"
        f"Date   : {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
        f"{'─' * 50}\n\n"
    )
    full = header + content
    return _save_text(full, "youtube_summary")

                                                                        

def _download_video(
    video_url: str,
    format_type: str = "video",
    quality: str = "best",
    output_dir: Optional[str] = None,
) -> str:
    """Download video or audio using yt-dlp."""
    ytdlp = shutil.which("yt-dlp") or shutil.which("youtube-dl")
    if not ytdlp:
        return "yt-dlp (or youtube-dl) is not installed. Please install it to enable downloads."
    if not _is_valid_youtube_url(video_url):
        return "Invalid YouTube URL."
    if output_dir:
        out = Path(output_dir).expanduser()
    else:
        out = Path.home() / "Desktop"
    out.mkdir(parents=True, exist_ok=True)

    cmd = [ytdlp, video_url, "-o", str(out / "%(title)s.%(ext)s")]
    if format_type == "audio":
        cmd += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        if quality and quality != "best":
            cmd += [
                "-f",
                f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]",
            ]
        else:
            cmd += ["-f", "bestvideo+bestaudio/best"]
    try:
                                                                                        
        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return f"Download completed. File saved to {out}."
    except subprocess.CalledProcessError as e:
        return f"Download failed: {e.stderr[:200]}"
    except FileNotFoundError:
        return "yt-dlp not found."
    except Exception as e:
        return f"Download error: {e}"

                                                                        

def _handle_play(parameters: dict, player) -> str:
    """Play a video: if url given, open directly; else search and play top result."""
    url = parameters.get("url", "").strip()
    if url:
        if not _is_valid_youtube_url(url):
            return "That doesn't look like a valid YouTube URL."
        _open_url(url)
        return f"Opening: {url}"

    query = parameters.get("query", "").strip()
    if not query:
        return "Please tell me what you'd like to watch, sir."

    if player:
        player.write_log(f"[YouTube] Searching: {query}")
    print(f"[YouTube] 🔍 Searching for first video: {query}")

    video_url = _scrape_first_video_url(query)
    if video_url:
        print(f"[YouTube] ▶️ Opening: {video_url}")
        _open_url(video_url)
        return f"Playing: {query}"

    print(f"[YouTube] ⚠️ Scrape failed, opening search page")
    fallback = f"https://www.youtube.com/results?search_query={quote_plus(query)}&sp={_YT_VIDEO_FILTER}"
    _open_url(fallback)
    return f"Opened YouTube search for: {query} (manual selection required)"

def _handle_play_url(parameters: dict, player) -> str:
    """Direct open URL (alias for play with url)."""
    url = parameters.get("url", "").strip()
    if not url:
        return "Please provide a YouTube URL."
    return _handle_play({"url": url}, player)

def _handle_search(parameters: dict, player, speak) -> str:
    query = parameters.get("query", "").strip()
    if not query:
        return "Please provide a search query."
    max_res = int(parameters.get("max_results", 5))
    results = _scrape_search_results(query, max_results=max_res)
    if not results:
        return f"No results found for: {query}"
    lines = [f"Top {len(results)} results for '{query}':"]
    for i, r in enumerate(results, 1):
        lines.append(f"\n{i}. {r['title']}")
        lines.append(
            f"   Channel: {r['channel']}  |  Views: {r['views']}  |  Duration: {r['duration']}"
        )
        lines.append(f"   URL: {r['url']}")
    return "\n".join(lines)

def _handle_download(parameters: dict, player, speak) -> str:
    url = parameters.get("url", "").strip()
    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
    if not url or not _is_valid_youtube_url(url):
        return "Please provide a valid YouTube URL."
    fmt = parameters.get("format", "video").lower()                  
    quality = parameters.get("quality", "best").lower()
    output = parameters.get("output_dir")
    return _download_video(url, fmt, quality, output)

def _handle_transcript(parameters: dict, player, speak) -> str:
    if not _TRANSCRIPT_OK:
        return "youtube-transcript-api is not installed. Run: pip install youtube-transcript-api"
    url = parameters.get("url", "").strip()
    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
    if not url or not _is_valid_youtube_url(url):
        return "Please provide a valid YouTube URL."
    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID."

    transcript = _get_transcript(video_id)
    if not transcript:
        return "I couldn't retrieve a transcript for that video, sir."

    do_save = parameters.get("save", False)
    if do_save or parameters.get("save_transcript", False):
        saved_path = _save_text(transcript, "youtube_transcript")
        return f"Transcript saved to: {saved_path}"
    else:
                                     
        return transcript[:5000]                    

def _handle_summarize(parameters: dict, player, speak) -> str:
    if not _TRANSCRIPT_OK:
        return "youtube-transcript-api is not installed. Run: pip install youtube-transcript-api"

    url = parameters.get("url", "").strip()
    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
    if not url or not _is_valid_youtube_url(url):
        return "Please provide a valid YouTube URL."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID."

    if player:
        player.write_log(f"[YouTube] Summarizing: {url}")
    if speak:
        speak("Fetching the transcript now, sir. One moment.")

    transcript = _get_transcript(video_id)
    if not transcript:
        return "I couldn't retrieve a transcript for that video, sir."

    if speak:
        speak("Transcript retrieved. Generating summary now.")

    try:
        summary = _summarize_with_gemini(transcript, url)
    except Exception as e:
        return f"Summary generation failed, sir: {e}"

    if speak:
        speak(summary)

    if parameters.get("save", False):
        saved_path = _save_summary(summary, url)
        return f"Summary complete and saved to Desktop: {saved_path}"

    return summary

def _handle_get_info(parameters: dict, player, speak) -> str:
    url = parameters.get("url", "").strip()
    if not url:
        url = _ask_for_url("Please paste the YouTube video URL:")
    if not url or not _is_valid_youtube_url(url):
        return "Please provide a valid YouTube URL."

    video_id = _extract_video_id(url)
    if not video_id:
        return "Could not extract video ID."

    if player:
        player.write_log(f"[YouTube] Getting info: {url}")

    info = _scrape_video_info(video_id)
    if not info:
        return "Could not retrieve video information, sir."

    lines = [
        f"{key.capitalize()}: {info[key]}"
        for key in ("title", "channel", "views", "duration", "likes")
        if key in info
    ]
    result = "\n".join(lines)

    if speak:
        speak(f"Here's the video info, sir. {result.replace(chr(10), '. ')}")

    return result

def _handle_trending(parameters: dict, player, speak) -> str:
    region = parameters.get("region", "TR").upper()
    if player:
        player.write_log(f"[YouTube] Trending: {region}")

    trending = _scrape_trending(region=region, max_results=8)
    if not trending:
        return f"Could not fetch trending videos for region {region}, sir."

    lines = [f"Top trending videos in {region}:"]
    lines += [f"{v['rank']}. {v['title']} — {v['channel']}" for v in trending]
    result = "\n".join(lines)

    if speak:
        top3 = trending[:3]
        spoken = "Here are the top trending videos, sir. " + ". ".join(
            f"Number {v['rank']}: {v['title']} by {v['channel']}" for v in top3
        )
        speak(spoken)

    return result

                                                                        

_ACTION_MAP = {
    "play": _handle_play,
    "play_url": _handle_play_url,       
    "search": _handle_search,       
    "download": _handle_download,       
    "transcript": _handle_transcript,       
    "summarize": _handle_summarize,
    "get_info": _handle_get_info,
    "video_info": _handle_get_info,                  
    "trending": _handle_trending,
}

def youtube_video(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
    speak=None,
) -> str:
    """
    Enhanced YouTube controller.

    parameters:
      action       : One of 'play', 'play_url', 'search', 'download',
                     'transcript', 'summarize', 'get_info', 'trending'
      query        : Search query
      url          : YouTube video URL
      max_results  : Max search results (default 5)
      format       : 'video' or 'audio' (download)
      quality      : Video quality e.g. '720' or 'best'
      output_dir   : Download directory (default Desktop)
      region       : Country code for trending (default 'TR')
      save         : Save result (summary/transcript) to Desktop
    """
    params = parameters or {}
    action = params.get("action", "play").lower().strip()

    if player:
        player.write_log(f"[YouTube] Action: {action}")
    print(f"[YouTube] ▶️  Action: {action}  Params: {params}")

    handler = _ACTION_MAP.get(action)
    if handler is None:
        valid = ", ".join(sorted(_ACTION_MAP.keys()))
        return f"Unknown YouTube action: '{action}'. Available: {valid}"

    try:
                                                    
        if action in ("play", "play_url"):
            return handler(params, player) or "Done."
        else:
            return handler(params, player, speak) or "Done."
    except Exception as e:
        print(f"[YouTube] ❌ Error in {action}: {e}")
        return f"YouTube {action} failed, sir: {e}"
