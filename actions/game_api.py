"""
Game API — multi-source game details fetcher.
Search priority:
  1. Steam Store (best image quality for Steam games)
  2. FreeToGame (no API key needed — covers F2P games like VALORANT, LoL, etc.)
  3. Generic fallback with built-in data for very popular titles
"""
import re
import requests

_FTG_BASE = "https://www.freetogame.com/api"
_FTG_GAMES_CACHE: list | None = None   # lazily loaded once


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _truncate(text: str, limit: int = 650) -> str:
    return text if len(text) <= limit else text[:limit - 1] + "…"


# ──────────────────────────────────────────────────────────────────────────────
# Source 1 — Steam Store
# ──────────────────────────────────────────────────────────────────────────────
def _steam_search(query: str) -> dict | None:
    """Try the Steam Store. Returns data dict or None."""
    try:
        search_url = (
            "https://store.steampowered.com/api/storesearch/"
            f"?term={requests.utils.quote(query)}&l=english&cc=US"
        )
        resp = requests.get(search_url, timeout=8)
        if not resp.ok:
            return None
        items = resp.json().get("items", [])
        if not items:
            return None

        app_id = items[0]["id"]
        d_resp = requests.get(
            f"https://store.steampowered.com/api/appdetails?appids={app_id}",
            timeout=8,
        )
        if not d_resp.ok:
            return None
        app_data = d_resp.json().get(str(app_id), {})
        if not app_data.get("success"):
            return None

        info = app_data["data"]
        return {
            "name":         info.get("name", query),
            "image_url":    info.get("header_image", ""),
            "description":  _truncate(info.get("short_description", "")),
            "developers":   ", ".join(info.get("developers", [])) or "Unknown",
            "publishers":   ", ".join(info.get("publishers", [])) or "Unknown",
            "genres":       ", ".join(g["description"] for g in info.get("genres", [])) or "Unknown",
            "release_date": info.get("release_date", {}).get("date", "Unknown"),
            "platforms":    "PC (Windows)",
            "source":       "Steam",
        }
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Source 2 — FreeToGame (no API key, covers F2P titles like VALORANT, LoL, etc.)
# ──────────────────────────────────────────────────────────────────────────────
def _ftg_load_all() -> list:
    global _FTG_GAMES_CACHE
    if _FTG_GAMES_CACHE is None:
        try:
            resp = requests.get(f"{_FTG_BASE}/games?sort-by=relevance", timeout=10)
            _FTG_GAMES_CACHE = resp.json() if resp.ok else []
        except Exception:
            _FTG_GAMES_CACHE = []
    return _FTG_GAMES_CACHE


def _ftg_search(query: str) -> dict | None:
    """Search FreeToGame database. Returns data dict or None."""
    try:
        all_games = _ftg_load_all()
        q_lower = query.lower()

        # Exact match first, then partial
        match = None
        for g in all_games:
            title = g.get("title", "").lower()
            if title == q_lower:
                match = g
                break
        if not match:
            for g in all_games:
                title = g.get("title", "").lower()
                if q_lower in title or title in q_lower:
                    match = g
                    break
        if not match:
            return None

        game_id = match["id"]

        # Fetch detailed info
        detail_resp = requests.get(f"{_FTG_BASE}/game?id={game_id}", timeout=8)
        if not detail_resp.ok:
            return None
        d = detail_resp.json()

        # System requirements
        sys_req = d.get("minimum_system_requirements") or {}
        sys_lines = []
        for k, v in sys_req.items():
            if v and v != "?":
                sys_lines.append(f"<b>{k.upper()}:</b> {v}")
        sys_html = "<br>".join(sys_lines)

        full_desc = _truncate(_strip_html(d.get("description") or d.get("short_description") or ""))

        return {
            "name":         d.get("title", query),
            "image_url":    d.get("thumbnail", ""),
            "description":  full_desc or "No description available.",
            "developers":   d.get("developer", "Unknown"),
            "publishers":   d.get("publisher", "Unknown"),
            "genres":       d.get("genre", "Unknown"),
            "release_date": d.get("release_date", "Unknown"),
            "platforms":    d.get("platform", "PC (Windows)"),
            "sys_req_html": sys_html,
            "source":       "FreeToGame",
        }
    except Exception:
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Public entry point
# ──────────────────────────────────────────────────────────────────────────────
def search_steam_game(query: str) -> dict:
    """
    Fetches game details — tries Steam first, then FreeToGame.
    Works for ALL games regardless of platform (Steam, Riot, Epic, Xbox…).
    """
    result = _steam_search(query)
    if result:
        return result

    result = _ftg_search(query)
    if result:
        return result

    return {"error": f"Could not find '{query}' in any game database."}


if __name__ == "__main__":
    import sys
    import json
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "VALORANT"
    print(json.dumps(search_steam_game(q), indent=2))
