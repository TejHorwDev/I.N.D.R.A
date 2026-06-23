# pylint: disable=all
# pylint: disable=C0114, C0115, C0116, C0103, C0301, C0302, W0611, W0718, R0902, R0903, R0904, R0911, R0912, R0913, R0914, R0915, R0801
"""
web_search.py – INDRA Advanced Internet Search Engine
======================================================
Multi‑backend, self‑healing web search with AI‑powered summaries,
comparison tables, and real‑time news.

Features:
  • Primary: Gemini Grounding (Google Search via AI) for factual, accurate answers.
  • Fallback: DuckDuckGo Instant Answer + text snippets, with optional Google CSE.
  • Compare mode: side‑by‑side analysis of multiple items with data.
  • Caching layer (TTL) to avoid repeated API calls.
  • Query type detection: simple search, comparison, news, definition.
  • Lazy imports, zero startup penalty.
  • Thread‑safe result formatting, Markdown compatible output.
  • Extensive logging and error recovery.

Author : INDRA Project
Version: 8.0
"""

import hashlib
import json
import re
import sys
import threading
import time
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ----------------------------------------------------------------------
# Lazy imports
# ----------------------------------------------------------------------
_DDGS = None
_GENAI = None
_REQUESTS = None


def _import_ddgs():
    return False


def _import_genai():
    global _GENAI
    if _GENAI is None:
        try:
            from google import genai

            _GENAI = genai
        except ImportError:
            _GENAI = False
    return _GENAI


def _import_requests():
    global _REQUESTS
    if _REQUESTS is None:
        try:
            import requests

            _REQUESTS = requests
        except ImportError:
            _REQUESTS = False
    return _REQUESTS


# ----------------------------------------------------------------------
# Path & config
# ----------------------------------------------------------------------
@lru_cache(maxsize=1)
def _get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = _get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"


@lru_cache(maxsize=1)
def _load_config() -> dict:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _get_api_key(service: str = "gemini") -> str:
    cfg = _load_config()
    key = cfg.get(f"{service}_api_key", "")
    if not key and service == "gemini":
        key = cfg.get("gemini_api_key", "")  # fallback
    if not key:
        raise RuntimeError(f"{service} API key not found in config.")
    return key


# ----------------------------------------------------------------------
# Simple in‑memory cache (TTL)
# ----------------------------------------------------------------------
_CACHE: Dict[str, Tuple[float, Any]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL = 300  # 5 minutes


def _cache_key(*args) -> str:
    raw = "|".join(str(a) for a in args)
    return hashlib.sha256(raw.encode()).hexdigest()


def _cache_get(key: str) -> Optional[Any]:
    with _CACHE_LOCK:
        if key in _CACHE:
            ts, val = _CACHE[key]
            if time.time() - ts < _CACHE_TTL:
                return val
            else:
                del _CACHE[key]
    return None


def _cache_set(key: str, value: Any) -> None:
    with _CACHE_LOCK:
        _CACHE[key] = (time.time(), value)
        # Limit cache size
        if len(_CACHE) > 200:
            # remove oldest
            oldest = min(_CACHE.items(), key=lambda x: x[1][0])
            del _CACHE[oldest[0]]


# ----------------------------------------------------------------------
# Backend: Gemini Grounding (Google Search)
# ----------------------------------------------------------------------
def _gemini_search(query: str, max_retries: int = 2) -> str:
    genai = _import_genai()
    if not genai:
        raise RuntimeError("google‑genai not installed. Run: pip install google‑genai")
    client = genai.Client(api_key=_get_api_key("gemini"))
    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=query,
                config={
                    "tools": [{"google_search": {}}],
                    "temperature": 0.2,
                },
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            if attempt < max_retries:
                time.sleep(1 * (attempt + 1))
                continue
            raise e
    raise RuntimeError("Gemini grounding failed after retries.")


# ----------------------------------------------------------------------
# Backend: DuckDuckGo Custom Scraper
# ----------------------------------------------------------------------
def _ddg_search(query: str, max_results: int = 5) -> List[Dict]:
    requests = _import_requests()
    if not requests:
        print("[WebSearch] requests not installed.")
        return []
        
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        print("[WebSearch] beautifulsoup4 not installed.")
        return []

    results = []
    url = "https://html.duckduckgo.com/html/"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    }
    
    try:
        resp = requests.post(url, data={"q": query}, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        
        for result in soup.find_all("div", class_="result"):
            if len(results) >= max_results:
                break
                
            title_elem = result.find("h2", class_="result__title")
            snippet_elem = result.find("a", class_="result__snippet")
            url_elem = result.find("a", class_="result__url")
            
            if title_elem and snippet_elem and url_elem:
                results.append({
                    "title": title_elem.text.strip(),
                    "snippet": snippet_elem.text.strip(),
                    "url": url_elem.get("href", "")
                })
    except Exception as e:
        print(f"[WebSearch] DDG Scraper failed: {e}")
        
    return results


def _synthesize_results(query: str, results: List[Dict]) -> str:
    if not results:
        return f"No results found for: {query}"
        
    context_lines = []
    for r in results:
        context_lines.append(f"Title: {r.get('title')}\nSnippet: {r.get('snippet')}\nURL: {r.get('url')}\n")
    context_text = "\n".join(context_lines)
    
    genai = _import_genai()
    if genai:
        try:
            client = genai.Client(api_key=_get_api_key("gemini"))
            prompt = (
                f"Synthesize the following search results into a concise, highly accurate, conversational answer for the query: '{query}'. "
                "Provide a direct answer. Do not say 'Based on the results' or 'According to the results'.\n\n"
                f"Search Results:\n{context_text}"
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
                config={"temperature": 0.3}
            )
            if response.text:
                return response.text.strip()
        except Exception as e:
            print(f"[WebSearch] Synthesis failed: {e}")
            
    # Fallback to the best snippet if synthesis fails (e.g. rate limit)
    best_snippet = results[0].get("snippet", "")
    if best_snippet:
        return f"{best_snippet} (Source: {results[0].get('url', 'Unknown')})"
        
    return f"No results found for: {query}"


# ----------------------------------------------------------------------
# Backend: Google Custom Search API (optional)
# ----------------------------------------------------------------------
def _google_cse_search(query: str, max_results: int = 5) -> List[Dict]:
    requests = _import_requests()
    if not requests:
        raise ImportError("requests not installed.")
    cfg = _load_config()
    api_key = cfg.get("google_cse_api_key", "")
    cx = cfg.get("google_cse_id", "")
    if not api_key or not cx:
        return []
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx,
        "q": query,
        "num": min(max_results, 10),
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        items = data.get("items", [])
        results = []
        for item in items:
            results.append(
                {
                    "title": item.get("title", ""),
                    "snippet": item.get("snippet", ""),
                    "url": item.get("link", ""),
                }
            )
        return results
    except Exception as e:
        print(f"[WebSearch] Google CSE failed: {e}")
        return []


# ----------------------------------------------------------------------
# Comparison engine
# ----------------------------------------------------------------------
def _compare(items: List[str], aspect: str) -> str:
    # Try Gemini first (most articulate)
    query = (
        f"Compare the following items: {', '.join(items)}.\n"
        f"Focus on: {aspect}.\n"
        "Provide specific facts, numbers, and key differences. "
        "Present the comparison in a clear, structured way."
    )
    cache_key = _cache_key("compare", tuple(items), aspect)
    cached = _cache_get(cache_key)
    if cached:
        return cached

    try:
        result = _gemini_search(query)
        _cache_set(cache_key, result)
        return result
    except Exception as e:
        print(
            f"[WebSearch] Gemini compare failed: {e} — falling back to DDG + local synthesis"
        )

    # Fallback: fetch DDG results per item and merge
    all_info = []
    for item in items:
        try:
            ddg_res = _ddg_search(f"{item} {aspect}", max_results=3)
            snippets = [r.get("snippet", "") for r in ddg_res if r.get("snippet")]
            if snippets:
                all_info.append(f"**{item}**: {' | '.join(snippets[:2])}")
            else:
                all_info.append(f"**{item}**: no data found.")
        except Exception:
            all_info.append(f"**{item}**: search failed.")
    if not all_info:
        return f"Could not retrieve comparison for {', '.join(items)}."
    # Attempt to summarise using local Gemini without grounding? Just format.
    lines = [f"**Comparison — {aspect.upper()}**\n"]
    lines.extend(all_info)
    return "\n".join(lines)


# ----------------------------------------------------------------------
# Query type detection
# ----------------------------------------------------------------------
_COMPARE_KEYWORDS = ["compare", "vs", "versus", "difference", "differences"]
_NEWS_KEYWORDS = ["news", "latest", "today", "breaking", "update"]
_DEFINE_KEYWORDS = ["define", "definition", "what is", "meaning of", "who is"]


def _detect_query_mode(query: str) -> str:
    q = query.lower()

    def contains_word(keywords, text):
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw) + r"(?:\b|\s)", text):
                return True
        return False

    if contains_word(_COMPARE_KEYWORDS, q):
        # Extract items: split by "and", "vs", ","
        return "compare"
    if contains_word(_NEWS_KEYWORDS, q):
        return "news"
    if contains_word(_DEFINE_KEYWORDS, q):
        return "definition"
    return "search"


# ----------------------------------------------------------------------
# Main controller
# ----------------------------------------------------------------------
def web_search(
    parameters: dict,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """
    Perform an intelligent web search.
    parameters dict keys:
        query       : str – search query
        mode        : "search" (default), "compare", "news", "definition" – optional auto‑detect
        items       : list of str – if mode="compare", items to compare
        aspect      : str – aspect for comparison (e.g., "price", "features")
        max_results : int – max results to return (default 5)
        backend     : "auto" (default), "gemini", "ddg", "cse"
    """
    params = parameters or {}
    query = params.get("query", "").strip()
    mode = params.get("mode", "").strip().lower()
    items = params.get("items", [])
    aspect = params.get("aspect", "general").strip()
    max_results = int(params.get("max_results", 5))
    backend = params.get("backend", "auto").lower().strip()

    # Auto‑detect mode if not specified
    if not mode and query:
        mode = _detect_query_mode(query)

    # If items provided and no explicit compare mode, force compare
    if items and not mode:
        mode = "compare"

    if not query and not items:
        return "Please provide a search query or items to compare."

    # Logging
    if player:
        player.write_log(f"[Search] {query or ', '.join(items)}")
    print(f"[WebSearch] Query: {query!r} | Mode: {mode} | Backend: {backend}")

    # Comparison mode
    if mode == "compare":
        if not items:
            # Try to extract items from query (split by "vs", "and", ",")
            items = re.split(
                r"\s+(?:vs\.?|versus|and|,)\s+", query, flags=re.IGNORECASE
            )
            items = [i.strip() for i in items if i.strip()]
            if len(items) < 2:
                # Fallback: treat whole query as comparison
                items = [query]
        if len(items) < 2:
            return "Please provide at least two items to compare."
        print(f"[WebSearch] Comparing: {items} (aspect: {aspect})")
        try:
            return _compare(items, aspect)
        except Exception as e:
            return f"Comparison failed: {e}"

    # Standard search (or news/definition)
    cache_key = _cache_key("search", query, backend, max_results)
    cached = _cache_get(cache_key)
    if cached:
        print("[WebSearch] Returning cached result.")
        return cached

    result = None

    # Try Gemini Grounding first (unless backend is explicitly set to something else)
    if backend in ("auto", "gemini"):
        try:
            print("[WebSearch] Trying Gemini Grounding...")
            result = _gemini_search(query)
            print("[WebSearch] Gemini OK.")
        except Exception as e:
            print(f"[WebSearch] Gemini failed: {e}")
            if backend == "gemini":
                return f"Gemini search failed: {e}"

    # Fallback to DuckDuckGo
    if not result and backend in ("auto", "ddg"):
        try:
            print("[WebSearch] Trying DuckDuckGo...")
            ddg_results = _ddg_search(query, max_results)
            result = _synthesize_results(query, ddg_results)
            print(f"[WebSearch] DDG: {len(ddg_results)} result(s) synthesized.")
        except Exception as e:
            print(f"[WebSearch] DDG failed: {e}")
            if backend == "ddg":
                return f"DuckDuckGo search failed: {e}"

    # Fallback to Google CSE if configured
    if not result and backend in ("auto", "cse"):
        try:
            print("[WebSearch] Trying Google CSE...")
            cse_results = _google_cse_search(query, max_results)
            if cse_results:
                result = _synthesize_results(query, cse_results)
                print(f"[WebSearch] CSE: {len(cse_results)} result(s) synthesized.")
            else:
                print("[WebSearch] CSE returned no results.")
        except Exception as e:
            print(f"[WebSearch] CSE failed: {e}")

    if not result:
        return "Sorry, I couldn't retrieve any search results. Please try again later."

    # Cache the successful result
    _cache_set(cache_key, result)
    return result


# ----------------------------------------------------------------------
# Quick helper to clear cache (useful for testing)
# ----------------------------------------------------------------------
def clear_cache():
    with _CACHE_LOCK:
        _CACHE.clear()


# ----------------------------------------------------------------------
# CLI test
# ----------------------------------------------------------------------
if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        q = " ".join(sys.argv[1:])
    else:
        q = "latest news about AI"
    print(web_search({"query": q}))
