# pylint: disable=all
# pylint: disable=C0114, C0115, C0116, C0103, C0301, C0302, W0611, W0718, R0902, R0903, R0904, R0911, R0912, R0913, R0914, R0915, R0801
# flight_finder.py — Enhanced Flight Search Engine
import json
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Try to import dateparser for super‑fast date recognition (optional)
try:
    import dateparser

    _HAS_DATEPARSER = True
except ImportError:
    _HAS_DATEPARSER = False


# Platform detection (re‑used from config)
def _is_windows():
    return sys.platform.startswith("win")


def _is_mac():
    return sys.platform.startswith("darwin")


def _is_linux():
    return sys.platform.startswith("linux")


# ───────────────────────────── Configuration ─────────────────────────────
def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

# Cache API key to avoid repeated file I/O
_API_KEY_CACHE = None


def _get_api_key() -> str:
    global _API_KEY_CACHE
    if _API_KEY_CACHE is None:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            _API_KEY_CACHE = json.load(f)["gemini_api_key"]
    return _API_KEY_CACHE


# Cabin mapping (Google Flights internal codes)
_CABIN_CODE = {"economy": "1", "premium": "2", "business": "3", "first": "4"}


# ─────────────────────────── Date Parser (Multi‑Strategy) ─────────────────
def _parse_date(raw: str) -> str:
    """Parse any human‑readable date into YYYY‑MM‑DD using local logic + AI fallback."""
    raw = raw.strip()
    if not raw:
        return datetime.now().strftime("%Y-%m-%d")

    # Already in perfect format?
    if re.match(r"\d{4}-\d{2}-\d{2}$", raw):
        return raw

    # Known numeric patterns
    for fmt in (
        "%d/%m/%Y",
        "%m/%d/%Y",
        "%d.%m.%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%m/%d/%y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue

    # Relative dates (today, tomorrow)
    lower = raw.lower()
    today = datetime.now()
    if lower in ("today", "bugün"):
        return today.strftime("%Y-%m-%d")
    if lower in ("tomorrow", "yarın"):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    # ── dateparser (fast, offline) ──
    if _HAS_DATEPARSER:
        try:
            parsed = dateparser.parse(raw, settings={"PREFER_DATES_FROM": "future"})
            if parsed:
                return parsed.strftime("%Y-%m-%d")
        except Exception:
            pass

    # ── Named months (English + Turkish) with day number ──
    _MONTH_MAP = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
        "ocak": 1,
        "şubat": 2,
        "mart": 3,
        "nisan": 4,
        "mayıs": 5,
        "haziran": 6,
        "temmuz": 7,
        "ağustos": 8,
        "eylül": 9,
        "ekim": 10,
        "kasım": 11,
        "aralık": 12,
    }
    for name, num in _MONTH_MAP.items():
        if name in lower:
            m = re.search(r"\b(\d{1,2})\b", raw)
            if m:
                day = int(m.group(1))
                year = today.year if num >= today.month else today.year + 1
                return f"{year}-{num:02d}-{day:02d}"

    # ── AI fallback (Gemini) ──
    try:
        from google import genai as _genai

        client = _genai.Client(api_key=_get_api_key())
        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=(
                f"Today is {today.strftime('%Y-%m-%d')}. "
                f"Convert this date expression to YYYY-MM-DD: '{raw}'. "
                f"Return ONLY the date string, nothing else."
            ),
        )
        candidate = response.text.strip()
        if re.match(r"\d{4}-\d{2}-\d{2}", candidate):
            return candidate
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Gemini date parse failed: {e}")

    # ── Last resort ──
    print(f"[FlightFinder] ⚠️ Could not parse date '{raw}' — using today.")
    return today.strftime("%Y-%m-%d")


# ─────────────────────── URL Builder (Proper Encoding) ────────────────────
def _build_google_flights_url(
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str] = None,
    passengers: int = 1,
    cabin: str = "economy",
    currency: str = "USD",
) -> str:
    """
    Build a Google Flights URL with pre‑filled search parameters.
    Uses `q` for the flight string and adds `curr`, `cabin`, `adults`.
    """
    # Clean airport codes (remove spaces, uppercase)
    origin = origin.strip().upper()
    destination = destination.strip().upper()

    # Build the human‑readable query string (Google parses this)
    if return_date:
        trip_str = (
            f"Flights from {origin} to {destination} on {date} returning {return_date}"
        )
    else:
        trip_str = f"Flights from {origin} to {destination} on {date}"

    # URL‑encode the query (the `q` parameter is what Google uses)
    encoded_q = urllib.parse.quote(trip_str)

    base_url = "https://www.google.com/travel/flights"
    # Additional parameters for cabin, adults, currency (note: `curr` might not work on all pages but helps)
    params = {
        "q": encoded_q,
        "curr": currency.upper(),
        "cabin": _CABIN_CODE.get(cabin.lower(), "1"),
        "adults": str(passengers),
    }
    if return_date:
        # Actually the return date is part of the q string, no separate param needed
        pass

    # Build full URL with query string
    query_string = urllib.parse.urlencode(params)
    return f"{base_url}?{query_string}"


# ───────────────────────── Browser Interaction ────────────────────────────
def _search_flights_browser(
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str] = None,
    passengers: int = 1,
    cabin: str = "economy",
) -> Tuple[str, str]:
    """
    Opens the Google Flights URL in the INDRA browser (via browser_control)
    and extracts the full page text. Returns (raw_text, final_url).
    """
    from actions.browser_control import browser_control

    url = _build_google_flights_url(
        origin, destination, date, return_date, passengers, cabin
    )
    print(f"[FlightFinder] 🌐 Opening: {url}")

    # Navigate
    browser_control({"action": "go_to", "url": url})

    # Wait for flight results to load (multiple attempts)
    max_attempts = 10
    raw_text = ""
    for attempt in range(1, max_attempts + 1):
        time.sleep(2)
        # Check if the page contains typical flight result indicators
        raw_text = browser_control({"action": "get_text"})
        if "Showing" in raw_text or "from" in raw_text.lower():
            break
        if attempt % 3 == 0:
            # Refresh or scroll down a bit to trigger loading
            browser_control(
                {"action": "execute_script", "script": "window.scrollBy(0, 300);"}
            )
    else:
        # Last resort: try to get the page text even if incomplete
        print("[FlightFinder] ⚠️ Results may not have fully loaded.")

    return raw_text, url


# ──────────────────────── Flight Data Extraction ──────────────────────────
# Pre‑compiled regex patterns for rule‑based fallback
_RE_PRICE = re.compile(r"\$\s?([\d,]+(?:\.\d{2})?)")
_RE_TIME = re.compile(r"(\d{1,2}:\d{2}\s?[APap][Mm])")
_RE_DURATION = re.compile(r"(\d+\s?h\s?\d+\s?m)")
_RE_STOPS = re.compile(r"(\d+)\s?stop", re.IGNORECASE)
_RE_AIRLINE = re.compile(r"([\w\s]+)\s+flight", re.IGNORECASE)


def _fallback_parse(raw_text: str) -> List[Dict]:
    """Rule‑based extraction of flight data as fallback if AI fails."""
    flights = []
    # Simplistic: find blocks that look like a flight listing
    # Normally Gemini is far better, this is a safety net.
    lines = raw_text.splitlines()
    current = {}
    for line in lines:
        line = line.strip()
        if not line:
            if current:
                flights.append(current)
                current = {}
                if len(flights) >= 5:
                    break
            continue
        # Try to extract price
        price_match = _RE_PRICE.search(line)
        if price_match:
            current["price"] = price_match.group(1).replace(",", "")
            current["currency"] = "USD"
        # Airline
        airline_match = _RE_AIRLINE.search(line)
        if airline_match and "airline" not in current:
            current["airline"] = airline_match.group(1).strip()
        # Times
        times = _RE_TIME.findall(line)
        if len(times) >= 2:
            current["departure"] = times[0]
            current["arrival"] = times[-1]
        # Duration
        dur_match = _RE_DURATION.search(line)
        if dur_match:
            current["duration"] = dur_match.group(1)
        # Stops
        stop_match = _RE_STOPS.search(line)
        if stop_match:
            current["stops"] = int(stop_match.group(1))
        elif "non‑stop" in line.lower() or "nonstop" in line.lower():
            current["stops"] = 0

    if current:
        flights.append(current)

    # Clean up incomplete entries
    valid = []
    for f in flights:
        if f.get("price") and f.get("airline"):
            valid.append(f)
    return valid[:5]


def _parse_flights_with_gemini(
    raw_text: str, origin: str, destination: str, date: str
) -> List[Dict]:
    """Use Gemini to extract structured flight data from Google Flights page text."""
    from google import genai as _genai
    from google.genai import types

    client = _genai.Client(api_key=_get_api_key())
    prompt = (
        f"Extract flight options from {origin} to {destination} on {date} "
        f"from this Google Flights page text:\n\n{raw_text[:12000]}\n\n"
        f"Return a JSON array of up to 5 flights:\n"
        f'[{{"airline":"...","departure":"HH:MM","arrival":"HH:MM",'
        f'"duration":"Xh Ym","stops":0,"price":"123.45","currency":"USD",'
        f'"flight_number":"AB123","layover_airport":"..."}}]\n'
        f"If no flights found, return: []"
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are a flight data extraction expert. "
                    "Extract flight information from raw webpage text. "
                    "Return ONLY valid JSON — no markdown, no explanation."
                )
            ),
        )
        text = response.text.strip()
        # Remove markdown code fences
        text = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        flights = json.loads(text)
        if isinstance(flights, list):
            return flights
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Gemini parse failed: {e}")

    # Fallback to rule‑based
    print("[FlightFinder] ⚡ Falling back to rule‑based extraction.")
    return _fallback_parse(raw_text)


# ──────────────────────── Formatting & Output ────────────────────────────
def _format_spoken(
    flights: List[Dict], origin: str, destination: str, date: str
) -> str:
    if not flights:
        return (
            f"I couldn't find any flights from {origin} to {destination} "
            f"on {date}, sir."
        )

    lines = [f"Here are the top flights from {origin} to {destination} on {date}, sir."]
    for i, f in enumerate(flights[:5], 1):
        airline = f.get("airline", "Unknown airline")
        dep = f.get("departure", "??:??")
        arr = f.get("arrival", "??:??")
        dur = f.get("duration", "")
        stops = f.get("stops", 0)
        price = f.get("price", "")
        cur = f.get("currency", "$")
        stop_str = (
            "non-stop" if stops == 0 else f"{stops} stop" + ("s" if stops > 1 else "")
        )
        price_str = f"{cur}{price}" if price else "price unavailable"
        dur_str = f", {dur}" if dur else ""
        lines.append(
            f"Option {i}: {airline}, departing {dep}, arriving {arr}{dur_str}, "
            f"{stop_str}, {price_str}."
        )

    # Find cheapest
    priced = [f for f in flights if f.get("price")]
    if priced:
        cheapest = min(
            priced,
            key=lambda x: float(re.sub(r"[^\d.]", "", str(x["price"])) or 999999),
        )
        lines.append(
            f"The cheapest option is {cheapest.get('airline')} "
            f"at {cheapest.get('currency','$')}{cheapest.get('price')}."
        )

    return " ".join(lines)


def _format_text_report(
    flights: List[Dict],
    origin: str,
    destination: str,
    date: str,
    return_date: Optional[str],
    page_url: str,
) -> str:
    lines = [
        "INDRA — Flight Search Results",
        "─" * 50,
        f"Route     : {origin} → {destination}",
        f"Date      : {date}",
    ]
    if return_date:
        lines.append(f"Return    : {return_date}")
    lines += [
        f"Searched  : {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"Source    : {page_url}",
        "─" * 50,
        "",
    ]

    if not flights:
        lines.append("No flights found.")
    else:
        for i, f in enumerate(flights, 1):
            stops = f.get("stops", 0)
            stop_str = "Non-stop" if stops == 0 else f"{stops} stop(s)"
            flight_num = f.get("flight_number", "")
            layover = f.get("layover_airport", "")
            lines += [
                f"Flight {i}:",
                f"  Airline   : {f.get('airline', 'N/A')} {flight_num}",
                f"  Departure : {f.get('departure', 'N/A')}",
                f"  Arrival   : {f.get('arrival', 'N/A')}",
                f"  Duration  : {f.get('duration', 'N/A')}",
                f"  Stops     : {stop_str}" + (f" via {layover}" if layover else ""),
                f"  Price     : {f.get('currency','$')}{f.get('price','N/A')}",
                "",
            ]

    return "\n".join(lines)


def _save_to_desktop(content: str, origin: str, destination: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"flights_{origin}_{destination}_{ts}.txt".replace(" ", "_")
    desktop = Path.home() / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    filepath = desktop / filename
    filepath.write_text(content, encoding="utf-8")
    print(f"[FlightFinder] 💾 Saved: {filepath}")

    # Open the file with default text editor
    try:
        if _is_windows():
            subprocess.Popen(["notepad.exe", str(filepath)])
        elif _is_mac():
            subprocess.Popen(["open", "-t", str(filepath)])
        else:
            subprocess.Popen(["xdg-open", str(filepath)])
    except Exception as e:
        print(f"[FlightFinder] ⚠️ Could not open editor: {e}")

    return str(filepath)


# ──────────────────────── Price Trend / Alert (New) ──────────────────────
# (Optional: these can be called by the controller with action="price_alert")
def _add_price_alert(parameters: dict, player=None) -> str:
    """Placeholder for future price tracking integration."""
    # Would store route + target price in a file and check periodically.
    return "Price alert feature is under development."


# ──────────────────────────── Main Controller ────────────────────────────
def flight_finder(parameters: dict, player=None, speak=None) -> str:
    """
    INDRA Flight Finder Controller – unchanged signature.
    Supported actions: search (default), price_alert, ...
    """
    params = parameters or {}
    action = params.get("action", "search").lower().strip()

    # ── Quick action routing ──
    if action == "price_alert":
        return _add_price_alert(params, player)

    # ── Default: search flights ──
    origin = params.get("origin", "").strip()
    destination = params.get("destination", "").strip()
    date_raw = params.get("date", "").strip()
    return_raw = (params.get("return_date") or "").strip()
    passengers = max(1, int(params.get("passengers", 1)))
    cabin = params.get("cabin", "economy").strip().lower()
    currency = params.get("currency", "USD").strip().upper()
    save = bool(params.get("save", False))
    max_price = params.get("max_price")  # optional filter

    if not origin or not destination:
        return "Please provide both origin and destination, sir."
    if not date_raw:
        return "Please provide a departure date, sir."

    if cabin not in _CABIN_CODE:
        cabin = "economy"

    date = _parse_date(date_raw)
    return_date = _parse_date(return_raw) if return_raw else None

    if player:
        player.write_log(
            f"[FlightFinder] {origin} → {destination} on {date}"
            f"{' return ' + return_date if return_date else ''}"
        )

    if speak:
        speak(f"Searching flights from {origin} to {destination} on {date}, sir.")

    print(
        f"[FlightFinder] ▶️ {origin} → {destination} | {date}"
        f"{' → ' + return_date if return_date else ''}"
        f" | {cabin} | {passengers} pax | {currency}"
    )

    try:
        raw_text, page_url = _search_flights_browser(
            origin, destination, date, return_date, passengers, cabin
        )

        if not raw_text:
            return "Could not retrieve flight data, sir. The page may not have loaded."

        if speak:
            speak("Analysing the results now, sir.")

        flights = _parse_flights_with_gemini(raw_text, origin, destination, date)

        # Optional max price filter
        if max_price and flights:
            max_price = float(max_price)
            flights = [
                f
                for f in flights
                if f.get("price")
                and float(str(f["price"]).replace(",", "")) <= max_price
            ]
            if not flights:
                return f"No flights found under {currency} {max_price}, sir."

        spoken = _format_spoken(flights, origin, destination, date)
        if speak:
            speak(spoken)

        result = spoken

        if save and flights:
            report = _format_text_report(
                flights, origin, destination, date, return_date, page_url
            )
            saved_path = _save_to_desktop(report, origin, destination)
            result += f" Results saved to Desktop: {saved_path}"

        return result

    except Exception as e:
        print(f"[FlightFinder] ❌ {e}")
        return f"Flight search failed, sir: {e}"
