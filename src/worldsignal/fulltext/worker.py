"""Background full-text fetcher, at a human pace.

One page at a time, random pauses between pages (longer for the browser), at most
``fulltext.per_site_hour`` pages per site per hour, and a site that shows a bot check,
refuses access or a paywall is left alone for hours (see ``repo.fulltext.PAUSE_AFTER``).
Subscription sites, read in the browser, go at a person's pace on top of that: a long gap between
two pages of one site, a daily limit, no automatic reading at night, and each page is read
(scrolled through) before its text is taken (``fetch.BrowserSession``). Bot checks and CAPTCHAs are
never solved.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from ..ai.languages import effective as ai_languages
from ..db import utc_now_iso
from ..repo.fulltext import BrowserPace, FullTextJob, FullTextRepository
from ..repo.notebook import local_today
from ..repo.settings import SettingsRepository
from .extract import extract
from .fetch import BrowserInfo, BrowserSession, FetchFailed, Page, browser_for, fetch_http, profile_in_use

log = logging.getLogger(__name__)

# Links that lead to a news aggregator's redirect page, not to the publisher: never opened.
AGGREGATOR_HOSTS = {"news.google.com"}

IDLE_SECONDS = 30
PAUSED_SECONDS = 60
BROWSER_IDLE_CLOSE = timedelta(minutes=5)
LOGIN_HOLD = timedelta(seconds=30)  # after "open site to sign in": do not reopen the hidden browser meanwhile
PACE = {"browser": (60.0, 180.0), "http": (6.0, 15.0)}
# A person clicking through articles they asked for: a short gap is enough.
USER_GAP = timedelta(minutes=3)
NIGHT_HOURS = range(0, 7)  # local time
AUTO_WINDOW = timedelta(hours=24)


class FullTextWorker:
    def __init__(
        self,
        repo: FullTextRepository,
        settings: SettingsRepository,
        own_profile: Path,
        *,
        http_fetch: Callable[[str], Any] = fetch_http,
        session_factory: Callable[[BrowserInfo, Path, bool], Any] = BrowserSession,
        find_browser: Callable[[str], BrowserInfo | None] = browser_for,
        in_use: Callable[[Path], bool] = profile_in_use,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Any] = asyncio.sleep,
        today: Callable[[], str] = local_today,
        local_zone: tzinfo | None = None,
        resting: Callable[[], bool] = lambda: False,
    ) -> None:
        self.resting = resting  # outside the working hours only the user's own requests are read (worktime.py)
        self.on_translation_queued: Callable[[], None] = lambda: None  # wakes the AI worker (set by the API)
        self.local_zone = local_zone  # None: this computer's time zone
        self.repo = repo
        self.settings = settings
        self.own_profile = own_profile
        self.http_fetch = http_fetch
        self.session_factory = session_factory
        self.find_browser = find_browser
        self.in_use = in_use
        self.clock = clock
        self.sleep = sleep
        self.today = today
        self._session: Any = None
        self._login_until: datetime | None = None
        self._session_key: tuple[Any, ...] | None = None
        self._last_browser_use: datetime | None = None
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._state: dict[str, Any] = {
            "running": False, "state": "starting", "browser": None, "profile": None,
            "current_article_id": None, "last_error": None, "last_done_at": None,
        }

    # -- public ----------------------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        return {**self._state, **self.repo.counts(), "paused_sources": self.repo.paused_sources(self.clock())}

    def wake(self) -> None:
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    def profile_dir(self, prefs: dict[str, Any], browser: BrowserInfo) -> Path:
        return browser.main_profile if prefs.get("fulltext.profile") == "main" else self.own_profile

    async def run_forever(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._state["running"] = True
        log.info("Full-text worker started")
        try:
            while True:
                self._wake.clear()
                try:
                    delay = await self.step()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Full-text step failed")
                    delay = PAUSED_SECONDS
                if delay:
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=delay)
                    except TimeoutError:
                        pass
        finally:
            self._state["running"] = False
            await self.close_browser()

    @property
    def browser_open(self) -> bool:
        """The hidden full-text browser is running (it holds World Signal's profile)."""
        return self._session is not None

    def make_room_for_login(self, timeout: float = 15.0) -> None:
        """The user wants to sign in on World Signal's profile: close the hidden browser (it holds the
        profile) and keep it closed until the login window has started. Thread-safe; waits for the close."""
        self._login_until = self.clock() + LOGIN_HOLD
        if self._loop is None or self._session is None:
            return
        future = asyncio.run_coroutine_threadsafe(self.close_browser(), self._loop)
        try:
            future.result(timeout)
        except Exception:
            log.warning("Closing the hidden browser for login failed", exc_info=True)

    async def close_browser(self) -> None:
        if self._session is not None:
            session, self._session, self._session_key = self._session, None, None
            await session.close()

    # -- one step ---------------------------------------------------------------------------------
    async def step(self) -> float:
        prefs = await asyncio.to_thread(self.settings.get_preferences)
        now = self.clock()
        if not prefs.get("fulltext.enabled", True):
            self._state.update(state="disabled", current_article_id=None)
            await self.close_browser()
            return PAUSED_SECONDS

        resting = await asyncio.to_thread(self.resting)
        if not resting:
            since = utc_now_iso(now - AUTO_WINDOW)
            picks = await asyncio.to_thread(
                self.repo.auto_candidates, since, float(prefs.get("fulltext.auto_min_score", 60)),
                int(prefs.get("fulltext.auto_per_story", 2)), self.today(),
            )
            for reason in ("notebook", "auto"):
                await asyncio.to_thread(self.repo.enqueue, picks[reason], reason)

        job = await asyncio.to_thread(self.repo.next_job, now, int(prefs.get("fulltext.per_site_hour", 4)),
                                      self.browser_pace(prefs, now), resting)
        if job is None:
            if self._session is not None and self._last_browser_use and now - self._last_browser_use > BROWSER_IDLE_CLOSE:
                await self.close_browser()
            self._state.update(state="resting" if resting else "idle", current_article_id=None)
            return IDLE_SECONDS

        browser = None
        if job.mode == "browser":
            browser = self.find_browser(str(prefs.get("fulltext.browser_path") or ""))
            if browser is None:
                self._state.update(state="no_browser", current_article_id=None, browser=None)
                return PAUSED_SECONDS
            profile = self.profile_dir(prefs, browser)
            self._state.update(browser=browser.name, profile=prefs.get("fulltext.profile", "own"))
            holding = self._login_until is not None and now < self._login_until
            if self._session is None and (holding or self.in_use(profile)):
                # The user's browser (main profile) or the login window (own profile) is open.
                self._state.update(state="profile_in_use", current_article_id=None)
                return PAUSED_SECONDS

        self._state.update(state="fetching", current_article_id=job.article_id)
        await asyncio.to_thread(self.repo.mark_attempt, job.article_id, now)
        try:
            page = await self._fetch(job, prefs, browser)
            result = extract(page.html, page.final_url, page.status)
            code = result.error_code
        except FetchFailed as exc:
            code, result = exc.code, None
        if result is not None and result.ok:
            await asyncio.to_thread(self.repo.store_text, job.article_id, result.text, job.mode, self.clock())
            if prefs.get("fulltext.translate") and prefs.get("ai.enabled", True):
                # Summary and full text in the user's languages (Settings -> Full text).
                await asyncio.to_thread(self.repo.request_translation, job.article_id, ai_languages(prefs))
                self.on_translation_queued()
            self._state.update(state="ok", last_error=None, last_done_at=utc_now_iso(self.clock()), current_article_id=None)
            log.info("Full text of article %s (%s, %s): %d chars", job.article_id, job.source_name, job.mode, len(result.text or ""))
        else:
            assert code is not None
            status = await asyncio.to_thread(self.repo.store_failure, job, code, self.clock())
            self._state.update(state="ok", last_error=code, current_article_id=None)
            log.warning("Full text of article %s (%s) failed: %s -> %s", job.article_id, job.source_name, code, status)
            if code in ("profile_in_use", "browser_failed"):
                return PAUSED_SECONDS
        low, high = PACE[job.mode]
        return random.uniform(low, high)

    def browser_pace(self, prefs: dict[str, Any], now: datetime) -> BrowserPace:
        local = now.astimezone(self.local_zone)
        return BrowserPace(
            gap=timedelta(minutes=int(prefs.get("fulltext.browser_gap_min", 20))),
            user_gap=USER_GAP,
            per_day=int(prefs.get("fulltext.browser_per_day", 15)),
            day_start=local.replace(hour=0, minute=0, second=0, microsecond=0),
            resting=bool(prefs.get("fulltext.browser_night_rest", True)) and local.hour in NIGHT_HOURS,
        )

    async def _fetch(self, job: FullTextJob, prefs: dict[str, Any], browser: BrowserInfo | None) -> Page:
        if urlsplit(job.url).hostname in AGGREGATOR_HOSTS:
            # Reports collected before 0.7.3 link to Google News, which shows a robot check instead of the report.
            raise FetchFailed("aggregator_link", job.url)
        if job.mode == "http":
            return await self.http_fetch(job.url)
        assert browser is not None
        profile = self.profile_dir(prefs, browser)
        visible = bool(prefs.get("fulltext.visible", False))
        key = (str(browser.executable), str(profile), visible)
        if self._session is not None and self._session_key != key:
            await self.close_browser()  # settings changed
        if self._session is None:
            self._session = self.session_factory(browser, profile, visible)
            self._session_key = key
        self._last_browser_use = self.clock()
        return await self._session.fetch(job.url)
