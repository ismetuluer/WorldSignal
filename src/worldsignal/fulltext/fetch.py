"""Getting an article page: a plain download (free sites) or the user's own browser (paid sites).

Browser mode drives a real Chromium browser (Brave, Chrome or Edge, found on this computer) with
patchright, which leaves out the automation markers that sites use to refuse automated browsers
(decision 2026-09-27: the user reads their own subscriptions; stealth approved, CAPTCHAs are never
solved). The browser runs with a persistent profile:

* ``own``  - World Signal's own profile under the data folder. The user logs in to their
             subscriptions once through "Oturum aç" (a normal browser window on that profile).
             Works while the user's everyday browser is open.
* ``main`` - the browser's everyday profile. No extra login, but a profile can only be open once:
             while the user's browser is running, fetching waits.

The window is placed off-screen unless the user asks to see it; there is one tab and pages are
opened one at a time.
"""

from __future__ import annotations

import asyncio
import logging
import os
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from .. import __version__

log = logging.getLogger(__name__)

HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
PAGE_TIMEOUT_MS = 45_000
# A person reads a page before leaving it: a first look (late scripts render meanwhile), then the page
# is scrolled down in uneven steps. About 20-60 seconds per page.
FIRST_LOOK_SECONDS = (3.0, 8.0)
SCROLL_STEPS = (4, 9)
SCROLL_PIXELS = (250, 700)
SCROLL_PAUSE_SECONDS = (2.5, 7.0)
USER_AGENT = f"Mozilla/5.0 (compatible; WorldSignal/{__version__}; article reader)"


class FetchFailed(Exception):
    """``local``: the failure happened on this computer before any page was asked for (the browser did not start),
    so the article and its site are not to blame."""

    def __init__(self, code: str, detail: str = "", *, local: bool = False) -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail
        self.local = local


@dataclass
class Page:
    status: int | None
    html: str
    final_url: str


# -- plain download -------------------------------------------------------------------------------
async def fetch_http(url: str, client: httpx.AsyncClient | None = None) -> Page:
    own = client is None
    client = client or httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=HTTP_TIMEOUT, follow_redirects=True)
    try:
        resp = await client.get(url)
    except httpx.TimeoutException as exc:
        raise FetchFailed("timeout", repr(exc)) from exc
    except httpx.HTTPError as exc:
        raise FetchFailed("network", repr(exc)) from exc
    finally:
        if own:
            await client.aclose()
    if "html" not in resp.headers.get("content-type", "html"):
        raise FetchFailed("not_article", resp.headers.get("content-type", ""))
    return Page(resp.status_code, resp.text, str(resp.url))


# -- browsers on this computer -------------------------------------------------------------------
@dataclass(frozen=True)
class BrowserInfo:
    name: str
    executable: Path
    main_profile: Path  # the browser's everyday "User Data" folder


def _candidates() -> list[BrowserInfo]:
    pf = [os.environ.get("ProgramFiles", r"C:\Program Files"), os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")]
    local = os.environ.get("LOCALAPPDATA", "")
    found = []
    for name, rel, data in (
        ("Brave", r"BraveSoftware\Brave-Browser\Application\brave.exe", r"BraveSoftware\Brave-Browser\User Data"),
        ("Google Chrome", r"Google\Chrome\Application\chrome.exe", r"Google\Chrome\User Data"),
        ("Microsoft Edge", r"Microsoft\Edge\Application\msedge.exe", r"Microsoft\Edge\User Data"),
    ):
        for base in [*pf, local]:
            exe = Path(base) / rel
            if base and exe.is_file():
                found.append(BrowserInfo(name, exe, Path(local) / data))
                break
    return found


def find_browsers() -> list[BrowserInfo]:
    """Installed Chromium browsers, Brave first."""
    return _candidates()


def browser_for(path_setting: str) -> BrowserInfo | None:
    """The browser chosen in settings (an executable path), or the first one found."""
    browsers = find_browsers()
    if path_setting:
        for b in browsers:
            if str(b.executable).lower() == path_setting.lower():
                return b
        exe = Path(path_setting)
        if exe.is_file():
            return BrowserInfo(exe.stem, exe, exe.parent.parent / "User Data")
        return None
    return browsers[0] if browsers else None


def profile_in_use(user_data_dir: Path) -> bool:
    """True while a browser has this profile open (Chromium keeps ``lockfile`` open exclusively on Windows)."""
    lock = user_data_dir / "lockfile"
    if not lock.exists():
        return False
    try:
        fd = os.open(lock, os.O_RDWR)
    except OSError:
        return True
    os.close(fd)
    return False


def open_login_window(browser: BrowserInfo, user_data_dir: Path, start_url: str = "about:blank") -> subprocess.Popen[bytes]:
    """A normal, visible browser window on World Signal's profile, so the user can log in to their
    subscriptions. No automation is attached to it."""
    user_data_dir = user_data_dir.resolve()  # a relative path would be read from the browser's own folder
    user_data_dir.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [str(browser.executable), f"--user-data-dir={user_data_dir}", "--no-first-run", "--no-default-browser-check", start_url],
    )


# -- browser session -----------------------------------------------------------------------------
async def read_like_a_person(page: Any, sleep: Any = asyncio.sleep, rng: random.Random | None = None) -> None:
    """Look at the page, then scroll through it the way a reader does, before its text is taken."""
    rng = rng or random.Random()
    await sleep(rng.uniform(*FIRST_LOOK_SECONDS))
    for _ in range(rng.randint(*SCROLL_STEPS)):
        await page.mouse.wheel(0, rng.randint(*SCROLL_PIXELS))
        await sleep(rng.uniform(*SCROLL_PAUSE_SECONDS))


class BrowserSession:
    """One browser with one tab, reused for consecutive pages and closed when idle."""

    def __init__(self, browser: BrowserInfo, user_data_dir: Path, visible: bool = False) -> None:
        self.browser = browser
        self.user_data_dir = user_data_dir.resolve()
        self.visible = visible
        self._pw: Any = None
        self._ctx: Any = None
        self._page: Any = None

    @property
    def open(self) -> bool:
        return self._ctx is not None

    async def _start(self) -> None:
        from patchright.async_api import async_playwright  # heavy import, only when needed

        if profile_in_use(self.user_data_dir):
            raise FetchFailed("profile_in_use", str(self.user_data_dir), local=True)
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        args = ["--no-first-run", "--no-default-browser-check"]
        if not self.visible:
            args += ["--window-position=-32000,-32000", "--window-size=1280,900"]
        self._pw = await async_playwright().start()
        try:
            self._ctx = await self._pw.chromium.launch_persistent_context(
                str(self.user_data_dir), executable_path=str(self.browser.executable),
                headless=False, no_viewport=True, args=args,
            )
        except Exception as exc:
            await self._pw.stop()
            self._pw = None
            raise FetchFailed("browser_failed", repr(exc)[:300], local=True) from exc
        self._page = self._ctx.pages[0] if self._ctx.pages else await self._ctx.new_page()

    async def fetch(self, url: str) -> Page:
        if self._ctx is None:
            await self._start()
        try:
            resp = await self._page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            await read_like_a_person(self._page)
            html = await self._page.content()
            return Page(resp.status if resp else None, html, self._page.url)
        except Exception as exc:
            if "Timeout" in type(exc).__name__ or "timeout" in str(exc).lower():
                raise FetchFailed("timeout", str(exc)[:200]) from exc
            await self.close()  # the browser may have been closed by the user; start fresh next time
            raise FetchFailed("browser_failed", str(exc)[:200]) from exc

    async def close(self) -> None:
        ctx, pw = self._ctx, self._pw
        self._ctx = self._page = self._pw = None
        try:
            if ctx is not None:
                await ctx.close()
        except Exception:
            log.debug("Browser context already gone", exc_info=True)
        try:
            if pw is not None:
                await pw.stop()
        except Exception:
            log.debug("Playwright already stopped", exc_info=True)
