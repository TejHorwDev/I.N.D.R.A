                     
                                                                                                                                       
from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import platform
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from playwright.async_api import BrowserContext, Page, Playwright
from playwright.async_api import TimeoutError as PlaywrightTimeout
from playwright.async_api import async_playwright

_OS = platform.system()                                  

                                                                        

def _normalize_url(url: str) -> str:
    url = url.strip()
    if not url:
        return "about:blank"
    if "://" in url:
        return url
    if "." not in url:
        url = url + ".com"
    return "https://" + url

def _user_agent() -> str:
    if _OS == "Windows":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    if _OS == "Darwin":
        return (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    return (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

                                                                        

def _real_profile_dir(browser: str) -> str:
    home = Path.home()
    local = os.environ.get("LOCALAPPDATA", "")
    roam = os.environ.get("APPDATA", "")

    candidates: list[Path] = []

    if _OS == "Windows":
        m = {
            "chrome": [Path(local) / "Google" / "Chrome" / "User Data"],
            "edge": [Path(local) / "Microsoft" / "Edge" / "User Data"],
            "brave": [Path(local) / "BraveSoftware" / "Brave-Browser" / "User Data"],
            "vivaldi": [Path(local) / "Vivaldi" / "User Data"],
            "opera": [
                Path(roam) / "Opera Software" / "Opera Stable",
                Path(local) / "Opera Software" / "Opera Stable",
            ],
            "operagx": [
                Path(roam) / "Opera Software" / "Opera GX Stable",
                Path(local) / "Opera Software" / "Opera GX Stable",
            ],
        }
        candidates = m.get(browser, [])

    elif _OS == "Darwin":
        lib = home / "Library" / "Application Support"
        m = {
            "chrome": [lib / "Google" / "Chrome"],
            "edge": [lib / "Microsoft Edge"],
            "brave": [lib / "BraveSoftware" / "Brave-Browser"],
            "vivaldi": [lib / "Vivaldi"],
            "opera": [lib / "com.operasoftware.Opera"],
            "operagx": [lib / "com.operasoftware.OperaGX"],
        }
        candidates = m.get(browser, [])

    elif _OS == "Linux":
        cfg = home / ".config"
        m = {
            "chrome": [cfg / "google-chrome", cfg / "chromium"],
            "edge": [cfg / "microsoft-edge"],
            "brave": [cfg / "BraveSoftware" / "Brave-Browser"],
            "vivaldi": [cfg / "vivaldi"],
            "opera": [cfg / "opera"],
            "operagx": [cfg / "opera-gx"],
        }
        candidates = m.get(browser, [])

    for p in candidates:
        if p.exists():
            print(f"[Browser] ✅ Real profile found for {browser}: {p}")
            return str(p)

    fallback = home / ".INDRA_profiles" / browser
    fallback.mkdir(parents=True, exist_ok=True)
    print(f"[Browser] ⚠️  Real profile not found for {browser}, using: {fallback}")
    return str(fallback)

def _firefox_profile_dir() -> Optional[str]:
    home = Path.home()

    if _OS == "Windows":
        base = Path(os.environ.get("APPDATA", "")) / "Mozilla" / "Firefox"
    elif _OS == "Darwin":
        base = home / "Library" / "Application Support" / "Firefox"
    else:
        base = home / ".mozilla" / "firefox"

    ini = base / "profiles.ini"
    if not ini.exists():
        return None

    current: dict[str, str] = {}
    default_path: Optional[str] = None

    for line in ini.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line.startswith("["):
            p = current.get("Path", "")
            if p and current.get("Default") == "1":
                is_rel = current.get("IsRelative", "1") == "1"
                default_path = str(base / p) if is_rel else p
            current = {}
        elif "=" in line:
            k, _, v = line.partition("=")
            current[k.strip()] = v.strip()

    p = current.get("Path", "")
    if p and current.get("Default") == "1":
        is_rel = current.get("IsRelative", "1") == "1"
        default_path = str(base / p) if is_rel else p

    if default_path and Path(default_path).exists():
        print(f"[Browser] Firefox real profile: {default_path}")
        return default_path
    return None

def _find_opera_windows() -> Optional[str]:
    local = os.environ.get("LOCALAPPDATA", "")
    prog = os.environ.get("PROGRAMFILES", "")
    prog86 = os.environ.get("PROGRAMFILES(X86)", "")

    candidates = [
        Path(local) / "Programs" / "Opera" / "opera.exe",
        Path(local) / "Programs" / "Opera GX" / "opera.exe",
        Path(prog) / "Opera" / "opera.exe",
        Path(prog86) / "Opera" / "opera.exe",
    ]
    for p in candidates:
        if p.exists():
            print(f"[Browser] Opera found at: {p}")
            return str(p)

    try:
        import winreg

        keys = [
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\opera.exe",
            r"SOFTWARE\Clients\StartMenuInternet\OperaStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\OperaGXStable\shell\open\command",
            r"SOFTWARE\Clients\StartMenuInternet\opera\shell\open\command",
        ]
        for key_path in keys:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        print(f"[Browser] Opera found via registry: {exe}")
                        return exe
                except Exception:
                    continue
    except Exception:
        pass

    return shutil.which("opera") or None

def _find_exe_windows(prog_name: str) -> Optional[str]:
    try:
        import winreg

        paths_to_try = [
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{prog_name}.exe",
            rf"SOFTWARE\Clients\StartMenuInternet\{prog_name}\shell\open\command",
        ]
        for key_path in paths_to_try:
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    k = winreg.OpenKey(hive, key_path)
                    val = winreg.QueryValue(k, None)
                    winreg.CloseKey(k)
                    exe = val.strip().strip('"').split('"')[0].split(" --")[0].strip()
                    if exe and Path(exe).exists():
                        return exe
                except Exception:
                    continue
    except Exception:
        pass
    return None

_BROWSER_SPECS: dict[str, dict] = {
    "Windows": {
        "chrome": {"engine": "chromium", "channel": "chrome", "bins": []},
        "edge": {"engine": "chromium", "channel": "msedge", "bins": []},
        "firefox": {"engine": "firefox", "channel": None, "bins": ["firefox.exe"]},
        "opera": {
            "engine": "chromium",
            "channel": None,
            "bins": ["opera.exe"],
            "special": "opera_windows",
        },
        "operagx": {
            "engine": "chromium",
            "channel": None,
            "bins": [],
            "special": "opera_windows",
        },
        "brave": {"engine": "chromium", "channel": None, "bins": ["brave.exe"]},
        "vivaldi": {"engine": "chromium", "channel": None, "bins": ["vivaldi.exe"]},
        "safari": None,
    },
    "Darwin": {
        "chrome": {"engine": "chromium", "channel": "chrome", "bins": []},
        "edge": {"engine": "chromium", "channel": "msedge", "bins": ["microsoft-edge"]},
        "firefox": {"engine": "firefox", "channel": None, "bins": ["firefox"]},
        "opera": {"engine": "chromium", "channel": None, "bins": ["opera"]},
        "operagx": {"engine": "chromium", "channel": None, "bins": ["opera"]},
        "brave": {
            "engine": "chromium",
            "channel": None,
            "bins": ["brave browser", "brave"],
        },
        "vivaldi": {"engine": "chromium", "channel": None, "bins": ["vivaldi"]},
        "safari": {"engine": "webkit", "channel": None, "bins": []},
    },
    "Linux": {
        "chrome": {
            "engine": "chromium",
            "channel": None,
            "bins": [
                "google-chrome",
                "google-chrome-stable",
                "chromium-browser",
                "chromium",
            ],
        },
        "edge": {
            "engine": "chromium",
            "channel": None,
            "bins": ["microsoft-edge", "microsoft-edge-stable"],
        },
        "firefox": {"engine": "firefox", "channel": None, "bins": ["firefox"]},
        "opera": {
            "engine": "chromium",
            "channel": None,
            "bins": ["opera", "opera-stable"],
        },
        "operagx": {
            "engine": "chromium",
            "channel": None,
            "bins": ["opera", "opera-stable"],
        },
        "brave": {
            "engine": "chromium",
            "channel": None,
            "bins": ["brave-browser", "brave"],
        },
        "vivaldi": {
            "engine": "chromium",
            "channel": None,
            "bins": ["vivaldi-stable", "vivaldi"],
        },
        "safari": None,
    },
}

_ALIASES: dict[str, str] = {
    "google chrome": "chrome",
    "google-chrome": "chrome",
    "microsoft edge": "edge",
    "ms edge": "edge",
    "msedge": "edge",
    "mozilla firefox": "firefox",
    "opera gx": "operagx",
    "opera_gx": "operagx",
}

def _resolve_browser(name: str) -> dict | None:
    name = _ALIASES.get(name.lower().strip(), name.lower().strip())
    os_map = _BROWSER_SPECS.get(_OS, {})
    spec = os_map.get(name)
    if spec is None:
        return None

    engine = spec["engine"]
    channel = spec.get("channel")
    bins = spec.get("bins", [])
    exe = None

    if spec.get("special") == "opera_windows":
        exe = _find_opera_windows()
        if not exe:
            print(f"[Browser] ⚠️  Opera executable not found on Windows.")
        return {"engine": engine, "exe": exe, "channel": channel}

    for b in bins:
        found = shutil.which(b)
        if found:
            exe = found
            break

    if not exe and _OS == "Darwin":
        app_names = {
            "chrome": ["Google Chrome.app"],
            "edge": ["Microsoft Edge.app"],
            "firefox": ["Firefox.app"],
            "opera": ["Opera.app", "Opera GX.app"],
            "brave": ["Brave Browser.app"],
            "vivaldi": ["Vivaldi.app"],
        }
        for app in app_names.get(name, []):
            app_dir = Path("/Applications") / app / "Contents" / "MacOS"
            if app_dir.exists():
                found_bins = list(app_dir.iterdir())
                if found_bins:
                    exe = str(found_bins[0])
                    break

    if not exe and _OS == "Windows" and not channel:
        exe = _find_exe_windows(name)

    return {"engine": engine, "exe": exe, "channel": channel}

def _detect_default_browser() -> str:
    try:
        if _OS == "Windows":
            import winreg

            k = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations"
                r"\UrlAssociations\http\UserChoice",
            )
            prog_id = winreg.QueryValueEx(k, "ProgId")[0].lower()
            winreg.CloseKey(k)
            for kw in ("edge", "firefox", "opera", "brave", "vivaldi", "chrome"):
                if kw in prog_id:
                    return kw
        elif _OS == "Darwin":
            out = subprocess.run(
                [
                    "defaults",
                    "read",
                    "com.apple.LaunchServices/com.apple.launchservices.secure",
                    "LSHandlers",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.lower()
            for kw in (
                "firefox",
                "opera",
                "brave",
                "vivaldi",
                "safari",
                "chrome",
                "edge",
            ):
                if kw in out:
                    return kw
        elif _OS == "Linux":
            out = subprocess.run(
                ["xdg-settings", "get", "default-web-browser"],
                capture_output=True,
                text=True,
                timeout=5,
            ).stdout.lower()
            for kw in ("firefox", "opera", "brave", "vivaldi", "chrome", "edge"):
                if kw in out:
                    return kw
    except Exception:
        pass
    return "chrome"

                                                                        

class _BrowserSession:
    """
    Full session for one browser instance.
    All browsers are launched with persistent context (real profile).
    """

    def __init__(self, browser_name: str):
        self.browser_name = browser_name
        self._spec = _resolve_browser(browser_name)

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

        self._pw: Optional[Playwright] = None
        self._context: Optional[BrowserContext] = None
        self._pages: List[Page] = []
        self._current_page_index: int = 0
        self._downloads: List[str] = []                            
        self._headless: bool = False                             
        self._download_dir: str = str(Path.home() / "Downloads")

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run_loop,
            daemon=True,
            name=f"BrowserThread-{self.browser_name}",
        )
        self._thread.start()
        self._ready.wait(timeout=20)

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._async_init())
        self._ready.set()
        self._loop.run_forever()

    async def _async_init(self):
        self._pw = await async_playwright().start()

    def run(self, coro, timeout: int = 60) -> str:
        if not self._loop:
            raise RuntimeError(f"Session for '{self.browser_name}' not started.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    def shutdown(self):
        """Stop the event loop and join the thread."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_close(), self._loop)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    def close(self):
        """Async close context & playwright, then stop loop."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._async_close(), self._loop).result(10)
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)

    async def _async_close(self):
        if self._context:
            try:
                await self._context.close()
            except Exception:
                pass
        if self._pw:
            try:
                await self._pw.stop()
            except Exception:
                pass
        self._context = None
        self._pages.clear()
        self._current_page_index = 0

    async def _launch(self):
        if self._context is not None:
            return

        if self._spec is None:
            raise RuntimeError(f"'{self.browser_name}' is not supported on {_OS}.")

        engine_name = self._spec["engine"]
        exe = self._spec.get("exe")
        channel = self._spec.get("channel")
        engine_obj = getattr(self._pw, engine_name)

        if engine_name == "firefox":
            profile = _firefox_profile_dir() or str(
                Path.home() / ".INDRA_profiles" / "firefox"
            )
            kwargs: Dict[str, Any] = {
                "headless": self._headless,
                "slow_mo": 0,
                "viewport": None,
                "no_viewport": True,
            }
            if exe:
                kwargs["executable_path"] = exe
            try:
                self._context = await engine_obj.launch_persistent_context(
                    profile, **kwargs
                )
            except Exception as e:
                print(
                    f"[Browser] Firefox real profile failed ({e}), using INDRA profile"
                )
                INDRA = str(Path.home() / ".INDRA_profiles" / "firefox_INDRA")
                Path(INDRA).mkdir(parents=True, exist_ok=True)
                self._context = await engine_obj.launch_persistent_context(
                    INDRA, **kwargs
                )

            await self._setup_context_listeners()
            self._pages = self._context.pages
            self._current_page_index = 0
            print(f"[Browser] ✅ Firefox launched")
            return

        if engine_name == "webkit":
            safari_profile = str(Path.home() / ".INDRA_profiles" / "safari")
            Path(safari_profile).mkdir(parents=True, exist_ok=True)
            kwargs = {
                "headless": self._headless,
                "slow_mo": 0,
                "viewport": None,
                "no_viewport": True,
            }
            self._context = await engine_obj.launch_persistent_context(
                safari_profile, **kwargs
            )
            await self._setup_context_listeners()
            self._pages = self._context.pages
            self._current_page_index = 0
            print(f"[Browser] ✅ Safari launched")
            return

        profile = _real_profile_dir(self.browser_name)

        kwargs = {
            "headless": self._headless,
            "slow_mo": 0,
            "viewport": None,
            "no_viewport": True,
            "args": [
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-first-run",
                "--disable-default-apps",
                "--no-default-browser-check",
            ],
        }

        if exe:
            kwargs["executable_path"] = exe
        elif channel:
            kwargs["channel"] = channel

        label = (
            f"{self.browser_name}"
            + (f"/{channel}" if channel else "")
            + (f" @ {exe}" if exe else "")
        )

        try:
            self._context = await engine_obj.launch_persistent_context(
                profile, **kwargs
            )
        except Exception as e:
            print(f"[Browser] ⚠️  Real profile failed for {label}: {e}")
            INDRA_profile = str(Path.home() / ".INDRA_profiles" / self.browser_name)
            Path(INDRA_profile).mkdir(parents=True, exist_ok=True)
            self._context = await engine_obj.launch_persistent_context(
                INDRA_profile, **kwargs
            )

        await self._setup_context_listeners()
        self._pages = self._context.pages
        self._current_page_index = 0
        print(f"[Browser] ✅ Launched [{label}]")

    async def _setup_context_listeners(self):
        """Attach download listener and track new pages."""
        self._context.on("page", self._on_new_page)
                   
        self._context.on("download", self._on_download)

    async def _on_new_page(self, page: Page):
        self._pages.append(page)
                                 
        self._current_page_index = len(self._pages) - 1

    async def _on_download(self, download):
        try:
            save_path = await download.path()
            if not save_path:
                suffix = download.suggested_filename or "download"
                save_path = str(Path(self._download_dir) / suffix)
                await download.save_as(save_path)
            self._downloads.append(save_path)
            print(f"[Browser] Download saved: {save_path}")
        except Exception as e:
            print(f"[Browser] Download error: {e}")

    @property
    def _current_page(self) -> Optional[Page]:
        if 0 <= self._current_page_index < len(self._pages):
            return self._pages[self._current_page_index]
        if self._pages:
            self._current_page_index = 0
            return self._pages[0]
        return None

    async def _get_page(self) -> Page:
        await self._launch()
        if self._current_page is None or self._current_page.is_closed():
                                   
            for i, p in enumerate(self._pages):
                if not p.is_closed():
                    self._current_page_index = i
                    return p
                                             
            if self._context:
                new_page = await self._context.new_page()
                self._pages.append(new_page)
                self._current_page_index = len(self._pages) - 1
                return new_page
        return self._current_page

    async def go_to(self, url: str) -> str:
        url = _normalize_url(url)
        page = await self._get_page()
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            await asyncio.sleep(0.3)
        except PlaywrightTimeout:
            pass
        except Exception as e:
            return f"Navigation error: {e}"
        return f"Opened: {page.url}"

    async def search(self, query: str, engine: str = "google") -> str:
        _engines = {
            "google": "https://www.google.com/search?q=",
            "bing": "https://www.bing.com/search?q=",
            "duckduckgo": "https://duckduckgo.com/?q=",
            "yandex": "https://yandex.com/search/?text=",
        }
        base = _engines.get(engine.lower(), _engines["google"])
        return await self.go_to(base + query.replace(" ", "+"))

    async def click(self, selector: str = None, text: str = None) -> str:
        page = await self._get_page()
        try:
            if text:
                await page.get_by_text(text, exact=False).first.click(timeout=8_000)
                return f"Clicked text: '{text}'"
            if selector:
                await page.click(selector, timeout=8_000)
                return f"Clicked selector: {selector}"
            return "No selector or text provided."
        except PlaywrightTimeout:
            return "Element not found (timeout)."
        except Exception as e:
            return f"Click error: {e}"

    async def type_text(
        self, selector: str = None, text: str = "", clear_first: bool = True
    ) -> str:
        page = await self._get_page()
        try:
            el = page.locator(selector).first if selector else page.locator(":focus")
            if clear_first:
                await el.clear()
            await el.type(text, delay=50)
            return "Text typed."
        except Exception as e:
            return f"Type error: {e}"

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        page = await self._get_page()
        try:
            y = amount if direction == "down" else -amount
            await page.mouse.wheel(0, y)
            return f"Scrolled {direction}."
        except Exception as e:
            return f"Scroll error: {e}"

    async def press(self, key: str) -> str:
        page = await self._get_page()
        try:
            await page.keyboard.press(key)
            return f"Pressed: {key}"
        except Exception as e:
            return f"Key error: {e}"

    async def get_text(self) -> str:
        page = await self._get_page()
        try:
            text = await page.inner_text("body")
            return text[:4000]
        except Exception as e:
            return f"Could not get page text: {e}"

    async def get_url(self) -> str:
        page = await self._get_page()
        return page.url

    async def get_title(self) -> str:
        page = await self._get_page()
        return await page.title()

    async def get_html(self) -> str:
        page = await self._get_page()
        return await page.content()

    async def fill_form(self, fields: dict) -> str:
        page = await self._get_page()
        results = []
        for selector, value in fields.items():
            try:
                el = page.locator(selector).first
                await el.clear()
                await el.type(str(value), delay=40)
                results.append(f"✓ {selector}")
            except Exception as e:
                results.append(f"✗ {selector}: {e}")
        return "Form filled: " + ", ".join(results)

    async def smart_click(self, description: str) -> str:
        page = await self._get_page()
        for role in (
            "button",
            "link",
            "searchbox",
            "textbox",
            "menuitem",
            "tab",
            "checkbox",
            "radio",
        ):
            try:
                loc = page.get_by_role(role, name=description)
                if await loc.count() > 0:
                    await loc.first.click(timeout=5_000)
                    return f"Clicked ({role}): '{description}'"
            except Exception:
                pass
        for attempt in (
            lambda: page.get_by_text(description, exact=False).first.click(
                timeout=5_000
            ),
            lambda: page.get_by_placeholder(description, exact=False).first.click(
                timeout=5_000
            ),
            lambda: page.locator(
                f'[alt*="{description}" i],[title*="{description}" i],'
                f'[aria-label*="{description}" i]'
            ).first.click(timeout=5_000),
        ):
            try:
                await attempt()
                return f"Clicked: '{description}'"
            except Exception:
                pass
        return f"Could not find element: '{description}'"

    async def smart_type(self, description: str, text: str) -> str:
        page = await self._get_page()
        candidates = [
            ("placeholder", page.get_by_placeholder(description, exact=False)),
            ("label", page.get_by_label(description, exact=False)),
            ("role", page.get_by_role("textbox", name=description)),
            ("searchbox", page.get_by_role("searchbox")),
            ("combobox", page.get_by_role("combobox", name=description)),
        ]
        for method, loc in candidates:
            try:
                el = loc.first
                if await el.count() == 0:
                    continue
                await el.clear()
                await el.type(text, delay=50)
                return f"Typed into ({method}): '{description}'"
            except Exception:
                continue
        return f"Could not find input: '{description}'"

    async def execute_js(self, script: str) -> str:
        page = await self._get_page()
        try:
            result = await page.evaluate(script)
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception as e:
            return f"JS error: {e}"

    async def wait_for_selector(self, selector: str, timeout: int = 15_000) -> str:
        page = await self._get_page()
        try:
            await page.wait_for_selector(selector, timeout=timeout)
            return f"Selector '{selector}' appeared."
        except PlaywrightTimeout:
            return f"Timeout waiting for '{selector}'."
        except Exception as e:
            return f"Wait error: {e}"

    async def wait_for_navigation(self, timeout: int = 30_000) -> str:
        page = await self._get_page()
        try:
            await page.wait_for_load_state("networkidle", timeout=timeout)
            return f"Navigation complete: {page.url}"
        except PlaywrightTimeout:
            return f"Timeout waiting for navigation."
        except Exception as e:
            return f"Wait error: {e}"

    async def select_option(
        self, selector: str, value: str = None, label: str = None
    ) -> str:
        page = await self._get_page()
        try:
            el = page.locator(selector).first
            if value:
                await el.select_option(value=value)
            elif label:
                await el.select_option(label=label)
            else:
                return "No value or label provided."
            return f"Selected option in '{selector}'."
        except Exception as e:
            return f"Select error: {e}"

    async def check(self, selector: str) -> str:
        page = await self._get_page()
        try:
            await page.check(selector)
            return f"Checked: {selector}"
        except Exception as e:
            return f"Check error: {e}"

    async def uncheck(self, selector: str) -> str:
        page = await self._get_page()
        try:
            await page.uncheck(selector)
            return f"Unchecked: {selector}"
        except Exception as e:
            return f"Uncheck error: {e}"

    async def hover(self, selector: str) -> str:
        page = await self._get_page()
        try:
            await page.hover(selector)
            return f"Hovered over: {selector}"
        except Exception as e:
            return f"Hover error: {e}"

    async def upload_file(self, selector: str, file_path: str) -> str:
        page = await self._get_page()
        try:
            await page.set_input_files(selector, file_path)
            return f"File uploaded to {selector}."
        except Exception as e:
            return f"Upload error: {e}"

    async def set_viewport(self, width: int, height: int) -> str:
        page = await self._get_page()
        try:
            await page.set_viewport_size({"width": width, "height": height})
            return f"Viewport set to {width}x{height}."
        except Exception as e:
            return f"Viewport error: {e}"

    async def cookies_get(self, urls: Optional[List[str]] = None) -> str:
        await self._launch()
        try:
            cookies = await self._context.cookies(urls)
            return json.dumps(cookies, indent=2, default=str)
        except Exception as e:
            return f"Get cookies error: {e}"

    async def cookies_set(self, cookies: List[Dict[str, Any]]) -> str:
        await self._launch()
        try:
            await self._context.add_cookies(cookies)
            return "Cookies set."
        except Exception as e:
            return f"Set cookies error: {e}"

    async def handle_dialog(self, accept: bool = True, prompt_text: str = "") -> str:
        page = await self._get_page()
        try:
            dialog = await page.wait_for_event("dialog", timeout=5_000)
            if accept:
                if prompt_text:
                    await dialog.accept(prompt_text)
                else:
                    await dialog.accept()
                return "Dialog accepted."
            else:
                await dialog.dismiss()
                return "Dialog dismissed."
        except PlaywrightTimeout:
            return "No dialog appeared."
        except Exception as e:
            return f"Dialog error: {e}"

    async def pdf(self, path: str = None) -> str:
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "page.pdf")
            await page.pdf(path=save_path)
            return f"PDF saved: {save_path}"
        except Exception as e:
            return f"PDF error: {e}"

    async def screenshot_fullpage(self, path: str = None) -> str:
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "fullpage_screenshot.png")
            await page.screenshot(path=save_path, full_page=True)
            return f"Full‑page screenshot saved: {save_path}"
        except Exception as e:
            return f"Screenshot error: {e}"

    async def emulate_media(self, color_scheme: str = "dark") -> str:
        page = await self._get_page()
        try:
            await page.emulate_media(color_scheme=color_scheme)
            return f"Media emulated to {color_scheme} scheme."
        except Exception as e:
            return f"Emulate media error: {e}"

    async def geolocation(self, latitude: float, longitude: float) -> str:
        page = await self._get_page()
        try:
            await self._context.grant_permissions(["geolocation"])
            await page.evaluate(f"""() => {{
                    navigator.geolocation.getCurrentPosition = (success) => success({{
                        coords: {{latitude: {latitude}, longitude: {longitude}}},
                        timestamp: Date.now()
                    }});
                }}""")
            return f"Geolocation set to ({latitude}, {longitude})."
        except Exception as e:
            return f"Geolocation error: {e}"

    async def grant_permissions(self, permissions: List[str]) -> str:
        await self._launch()
        try:
            await self._context.grant_permissions(permissions)
            return f"Permissions granted: {permissions}"
        except Exception as e:
            return f"Permission error: {e}"

    async def click_and_navigate(self, selector: str, timeout: int = 15_000) -> str:
        page = await self._get_page()
        try:
            async with page.expect_navigation(timeout=timeout):
                await page.click(selector)
            return f"Clicked and navigated to: {page.url}"
        except Exception as e:
            return f"Click & navigate error: {e}"

    async def drag_and_drop(self, source: str, target: str) -> str:
        page = await self._get_page()
        try:
            await page.drag_and_drop(source, target)
            return f"Dragged {source} to {target}."
        except Exception as e:
            return f"Drag & drop error: {e}"

    async def focus(self, selector: str) -> str:
        page = await self._get_page()
        try:
            await page.focus(selector)
            return f"Focused: {selector}"
        except Exception as e:
            return f"Focus error: {e}"

    async def new_tab(self, url: str = "") -> str:
        await self._launch()
        new_page = await self._context.new_page()
        self._pages.append(new_page)
        self._current_page_index = len(self._pages) - 1
        if url:
            return await self.go_to(url)
        return f"New tab opened (index {self._current_page_index})."

    async def close_tab(self) -> str:
        page = self._current_page
        if page and not page.is_closed():
            idx = self._pages.index(page)
            await page.close()
                              
            self._pages.pop(idx)
            if not self._pages:
                self._current_page_index = 0
                return "Tab closed. No tabs left."
                          
            if self._current_page_index >= len(self._pages):
                self._current_page_index = len(self._pages) - 1
            return "Tab closed."
        return "No active tab to close."

    async def switch_tab(self, index: int) -> str:
        await self._launch()
        if 0 <= index < len(self._pages):
            self._current_page_index = index
            page = self._pages[index]
            await page.bring_to_front()
            return f"Switched to tab {index}: {page.url}"
        return f"Tab index {index} out of range (0-{len(self._pages)-1})."

    async def list_tabs(self) -> str:
        await self._launch()
        lines = []
        for i, p in enumerate(self._pages):
            marker = " ◀" if i == self._current_page_index else ""
            title = await p.title() or "Untitled"
            lines.append(f"[{i}]{marker} {title} ({p.url})")
        return "Tabs:\n" + "\n".join(lines)

    async def back(self) -> str:
        page = await self._get_page()
        try:
            await page.go_back(timeout=10_000)
            return f"Navigated back: {page.url}"
        except Exception as e:
            return f"Back error: {e}"

    async def forward(self) -> str:
        page = await self._get_page()
        try:
            await page.go_forward(timeout=10_000)
            return f"Navigated forward: {page.url}"
        except Exception as e:
            return f"Forward error: {e}"

    async def reload(self) -> str:
        page = await self._get_page()
        try:
            await page.reload(timeout=15_000)
            return f"Page reloaded: {page.url}"
        except Exception as e:
            return f"Reload error: {e}"

    async def screenshot(self, path: str = None) -> str:
        page = await self._get_page()
        try:
            save_path = path or str(Path.home() / "Desktop" / "screenshot.png")
            await page.screenshot(path=save_path, full_page=False)
            return f"Screenshot saved: {save_path}"
        except Exception as e:
            return f"Screenshot error: {e}"

    async def close_browser(self) -> str:
        await self._async_close()
        return f"{self.browser_name} closed."

                                                                        

class _SessionRegistry:
    def __init__(self):
        self._sessions: Dict[str, _BrowserSession] = {}
        self._active_browser: str = ""
        self._lock = threading.Lock()

    def _get_or_create(self, browser_name: str) -> _BrowserSession:
        with self._lock:
            if browser_name not in self._sessions:
                sess = _BrowserSession(browser_name)
                sess.start()
                self._sessions[browser_name] = sess
                print(f"[Registry] New session: {browser_name}")
            return self._sessions[browser_name]

    def get(self, browser_name: Optional[str] = None) -> _BrowserSession:
        if not browser_name:
            browser_name = self._active_browser or _detect_default_browser()
        browser_name = _ALIASES.get(
            browser_name.lower().strip(), browser_name.lower().strip()
        )
        sess = self._get_or_create(browser_name)
        self._active_browser = browser_name
        return sess

    def switch(self, browser_name: str) -> str:
        browser_name = _ALIASES.get(
            browser_name.lower().strip(), browser_name.lower().strip()
        )
        self._get_or_create(browser_name)
        self._active_browser = browser_name
        return f"Active browser → {browser_name}"

    def close_one(self, browser_name: str) -> str:
        with self._lock:
            sess = self._sessions.pop(browser_name, None)
        if sess:
            sess.shutdown()
            if self._active_browser == browser_name:
                self._active_browser = ""
            return f"{browser_name} closed."
        return f"No active session for: {browser_name}"

    def close_all(self) -> str:
        with self._lock:
            names = list(self._sessions.keys())
            sessions = list(self._sessions.values())
            self._sessions.clear()
            self._active_browser = ""
        for s in sessions:
            try:
                s.shutdown()
            except Exception:
                pass
        return "All browsers closed: " + (", ".join(names) if names else "none")

    def list_sessions(self) -> str:
        with self._lock:
            if not self._sessions:
                return "No active browser sessions."
            lines = []
            for name in self._sessions:
                marker = " ◀ active" if name == self._active_browser else ""
                lines.append(f"  • {name}{marker}")
            return "Open browsers:\n" + "\n".join(lines)

_registry = _SessionRegistry()

                                                                        

def browser_control(
    parameters: Optional[Dict[str, Any]] = None,
    response=None,                          
    player=None,
    session_memory=None,                                                 
) -> str:
    params = parameters or {}
    action = params.get("action", "").lower().strip()
    browser = params.get("browser", "").lower().strip() or None

    if session_memory is not None and isinstance(session_memory, dict):
        if not browser:
            browser = session_memory.get("active_browser")
                                     
        if not action and "last_action" in session_memory:
                                         
            pass

    result = "Unknown action."

    if action == "switch":
        target = browser or params.get("target", "").lower().strip()
        result = _registry.switch(target) if target else "Please specify a browser."
        _store_state(session_memory, "switch", target)
        _log(player, result)
        return result

    if action == "list_browsers":
        result = _registry.list_sessions()
        _log(player, result)
        return result

    if action == "close_all":
        result = _registry.close_all()
        _store_state(session_memory, "close_all")
        _log(player, result)
        return result

    try:
        sess = _registry.get(browser)
    except Exception as e:
        result = f"Could not start browser session: {e}"
        _log(player, result)
        return result

    try:
                            
        if action == "go_to":
            result = sess.run(sess.go_to(params.get("url", "")))
        elif action == "search":
            result = sess.run(
                sess.search(params.get("query", ""), params.get("engine", "google"))
            )
        elif action == "back":
            result = sess.run(sess.back())
        elif action == "forward":
            result = sess.run(sess.forward())
        elif action == "reload":
            result = sess.run(sess.reload())

        elif action == "click":
            result = sess.run(sess.click(params.get("selector"), params.get("text")))
        elif action == "type":
            result = sess.run(
                sess.type_text(
                    params.get("selector"),
                    params.get("text", ""),
                    params.get("clear_first", True),
                )
            )
        elif action == "scroll":
            result = sess.run(
                sess.scroll(
                    params.get("direction", "down"), int(params.get("amount", 500))
                )
            )
        elif action == "press":
            result = sess.run(sess.press(params.get("key", "Enter")))
        elif action == "fill_form":
            result = sess.run(sess.fill_form(params.get("fields", {})))
        elif action == "smart_click":
            result = sess.run(sess.smart_click(params.get("description", "")))
        elif action == "smart_type":
            result = sess.run(
                sess.smart_type(params.get("description", ""), params.get("text", ""))
            )
        elif action == "hover":
            result = sess.run(sess.hover(params.get("selector", "")))
        elif action == "focus":
            result = sess.run(sess.focus(params.get("selector", "")))
        elif action == "check":
            result = sess.run(sess.check(params.get("selector", "")))
        elif action == "uncheck":
            result = sess.run(sess.uncheck(params.get("selector", "")))
        elif action == "select_option":
            result = sess.run(
                sess.select_option(
                    params.get("selector"), params.get("value"), params.get("label")
                )
            )
        elif action == "upload_file":
            result = sess.run(
                sess.upload_file(params.get("selector"), params.get("file_path", ""))
            )

        elif action == "execute_js":
            result = sess.run(sess.execute_js(params.get("script", "")))
        elif action == "get_text":
            result = sess.run(sess.get_text())
        elif action == "get_html":
            result = sess.run(sess.get_html())
        elif action == "get_url":
            result = sess.run(sess.get_url())
        elif action == "get_title":
            result = sess.run(sess.get_title())

        elif action == "wait_for_selector":
            result = sess.run(
                sess.wait_for_selector(
                    params.get("selector", ""), int(params.get("timeout", 15_000))
                )
            )
        elif action == "wait_for_navigation":
            result = sess.run(
                sess.wait_for_navigation(int(params.get("timeout", 30_000)))
            )

        elif action == "handle_dialog":
            accept = params.get("accept", True)
            prompt_text = params.get("prompt_text", "")
            result = sess.run(sess.handle_dialog(accept, prompt_text))

        elif action == "set_viewport":
            w = int(params.get("width", 1280))
            h = int(params.get("height", 720))
            result = sess.run(sess.set_viewport(w, h))
        elif action == "emulate_media":
            result = sess.run(sess.emulate_media(params.get("color_scheme", "dark")))
        elif action == "geolocation":
            result = sess.run(
                sess.geolocation(
                    float(params.get("lat", 0)), float(params.get("lon", 0))
                )
            )
        elif action == "grant_permissions":
            result = sess.run(sess.grant_permissions(params.get("permissions", [])))

        elif action == "cookies_get":
            result = sess.run(sess.cookies_get(params.get("urls")))
        elif action == "cookies_set":
            result = sess.run(sess.cookies_set(params.get("cookies", [])))

        elif action == "new_tab":
            result = sess.run(sess.new_tab(params.get("url", "")))
        elif action == "close_tab":
            result = sess.run(sess.close_tab())
        elif action == "switch_tab":
            result = sess.run(sess.switch_tab(int(params.get("index", 0))))
        elif action == "list_tabs":
            result = sess.run(sess.list_tabs())

        elif action == "screenshot":
            result = sess.run(sess.screenshot(params.get("path")))
        elif action == "screenshot_fullpage":
            result = sess.run(sess.screenshot_fullpage(params.get("path")))
        elif action == "pdf":
            result = sess.run(sess.pdf(params.get("path")))

        elif action == "downloads_list":
            result = (
                "Downloads:\n" + "\n".join(sess._downloads)
                if sess._downloads
                else "No downloads yet."
            )
        elif action == "clear_downloads":
            sess._downloads.clear()
            result = "Download history cleared."

        elif action == "click_and_navigate":
            result = sess.run(
                sess.click_and_navigate(
                    params.get("selector", ""), int(params.get("timeout", 15_000))
                )
            )
        elif action == "drag_and_drop":
            result = sess.run(
                sess.drag_and_drop(params.get("source", ""), params.get("target", ""))
            )

        elif action == "close":
            target = browser or _registry._active_browser
            result = _registry.close_one(target) if target else "No browser specified."
            _store_state(session_memory, "close", target)
        else:
            result = f"Unknown browser action: '{action}'"

    except concurrent.futures.TimeoutError:
        result = f"Browser action '{action}' timed out (60s)."
    except Exception as e:
        result = f"Browser error ({action}): {e}"

    _store_state(session_memory, action, browser, result, sess)
    _log(player, result)
    return result

def _store_state(memory, action, browser=None, result=None, sess=None):
    """Persist useful info in session_memory for the assistant."""
    if not isinstance(memory, dict):
        return
    if browser:
        memory["active_browser"] = browser
    memory["last_action"] = action
    memory["last_result"] = result
    if sess:
        try:
            page = sess._current_page
            if page and not page.is_closed():
                memory["current_url"] = page.url
                                                        
        except Exception:
            pass

def _log(player, text: str):
    short = str(text)[:80]
    print(f"[Browser] {short}")
    if player and hasattr(player, "write_log"):
        player.write_log(f"[browser] {short[:60]}")
