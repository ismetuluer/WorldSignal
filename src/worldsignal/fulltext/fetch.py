"""Getting an article page: a plain download (free sites), and finding the user's browsers.

The subscription sites are not fetched here: the browser extension reads them in the user's own browser
(fulltext/bridge.py). Before 0.16.0 a browser driven by patchright did that too; it was removed (the sites refused it, the
browser crashed under it, and the extension replaced it).
"""

from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

import httpx

from .. import __version__

log = logging.getLogger(__name__)

HTTP_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
USER_AGENT = f"Mozilla/5.0 (compatible; WorldSignal/{__version__}; article reader)"


class FetchFailed(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


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
