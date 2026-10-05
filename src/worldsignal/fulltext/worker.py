"""Background full-text fetcher, at a human pace.

One page at a time, random pauses between pages, at most
``fulltext.per_site_hour`` pages per site per hour, and a site that shows a bot check,
refuses access or a paywall is left alone for hours (see ``repo.fulltext.PAUSE_AFTER``).
Subscription sites are not read here but by the browser extension (fulltext/bridge.py), which takes its jobs from the
same queue at a person's pace (``browser_pace``): a long gap between two pages of one site, a daily limit, no automatic
reading at night. Bot checks and CAPTCHAs are never solved.
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

from ..db import utc_now_iso
from ..repo.fulltext import EXCLUSIVE_BOOST, PAID_BOOST, BrowserPace, FullTextJob, FullTextRepository
from ..repo.notebook import local_today
from ..repo.settings import SettingsRepository
from .fetch import FetchFailed, Page, fetch_http
from .outcome import record_page

log = logging.getLogger(__name__)

# Links that lead to a news aggregator's redirect page, not to the publisher: never opened.
AGGREGATOR_HOSTS = {"news.google.com"}

IDLE_SECONDS = 30
PAUSED_SECONDS = 60
PACE = (6.0, 15.0)  # seconds between two plain downloads
# A person clicking through articles they asked for: a short gap is enough.
USER_GAP = timedelta(minutes=3)
NIGHT_HOURS = range(0, 7)  # local time
AUTO_WINDOW = timedelta(hours=24)


def browser_pace(prefs: dict[str, Any], now: datetime, local_zone: tzinfo | None = None) -> BrowserPace:
    """A person's pace for the subscription sites (shared by this worker and the extension bridge)."""
    local = now.astimezone(local_zone)
    return BrowserPace(
        gap=timedelta(minutes=int(prefs.get("fulltext.browser_gap_min", 20))),
        user_gap=USER_GAP,
        per_day=int(prefs.get("fulltext.browser_per_day", 15)),
        day_start=local.replace(hour=0, minute=0, second=0, microsecond=0),
        resting=bool(prefs.get("fulltext.browser_night_rest", True)) and local.hour in NIGHT_HOURS,
    )


class FullTextWorker:
    def __init__(
        self,
        repo: FullTextRepository,
        settings: SettingsRepository,
        *,
        http_fetch: Callable[[str], Any] = fetch_http,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Any] = asyncio.sleep,
        today: Callable[[], str] = local_today,
        local_zone: tzinfo | None = None,
        resting: Callable[[], bool] = lambda: False,
        leased: Callable[[], int | None] = lambda: None,
        debug_dir: Path | None = None,
    ) -> None:
        self.debug_dir = debug_dir
        self.resting = resting  # outside the working hours only the user's own requests are read (worktime.py)
        self.leased = leased  # the article the browser extension is reading (ExtensionBridge.leased_article)
        self.on_translation_queued: Callable[[], None] = lambda: None  # wakes the AI worker (set by the API)
        self.local_zone = local_zone  # None: this computer's time zone
        self.repo = repo
        self.settings = settings
        self.http_fetch = http_fetch
        self.clock = clock
        self.sleep = sleep
        self.today = today
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._state: dict[str, Any] = {
            "running": False, "state": "starting",
            "current_article_id": None, "last_error": None, "last_done_at": None,
        }

    # -- public ----------------------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        return {**self._state, **self.repo.counts(), "paused_sources": self.repo.paused_sources(self.clock())}

    def wake(self) -> None:
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

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

    # -- one step ---------------------------------------------------------------------------------
    async def step(self) -> float:
        prefs = await asyncio.to_thread(self.settings.get_preferences)
        now = self.clock()
        if not prefs.get("fulltext.enabled", True):
            self._state.update(state="disabled", current_article_id=None)
            return PAUSED_SECONDS

        since = utc_now_iso(now - AUTO_WINDOW)
        # Automatic picks that were not read within the window are no longer worth reading (whoever reads them); the
        # article the extension is reading right now stays.
        leased = self.leased()
        await asyncio.to_thread(self.repo.drop_stale_auto, since, () if leased is None else (leased,))
        resting = await asyncio.to_thread(self.resting)
        if not resting:
            picks = await asyncio.to_thread(
                self.repo.auto_candidates, since, float(prefs.get("fulltext.auto_min_score", 60)),
                int(prefs.get("fulltext.auto_per_story", 2)), self.today(), True,
            )
            for reason in ("notebook", "auto"):
                await asyncio.to_thread(self.repo.enqueue, picks[reason], reason)
            await asyncio.to_thread(self.repo.enqueue, picks["exclusive"], "auto", EXCLUSIVE_BOOST)
            await asyncio.to_thread(self.repo.enqueue, picks["paid"], "auto", PAID_BOOST)

        # The "browser" sources are read by the extension (fulltext/bridge.py); never here.
        job = await asyncio.to_thread(self.repo.next_job, now, int(prefs.get("fulltext.per_site_hour", 4)),
                                      self.browser_pace(prefs, now), resting, modes=("http",))
        if job is None:
            self._state.update(state="resting" if resting else "idle", current_article_id=None)
            return IDLE_SECONDS

        self._state.update(state="fetching", current_article_id=job.article_id)
        previous = await asyncio.to_thread(self.repo.mark_attempt, job.article_id, now)
        try:
            page = await self._fetch(job)
        except FetchFailed as exc:
            status = await asyncio.to_thread(self.repo.store_failure, job, exc.code, self.clock())
            self._state.update(state="ok", last_error=exc.code, current_article_id=None)
            log.warning("Full text of article %s (%s) failed: %s -> %s", job.article_id, job.source_name, exc.code, status)
            return random.uniform(*PACE)
        outcome = await asyncio.to_thread(record_page, self.repo, job, page, prefs, self.clock(),
                                          self.on_translation_queued, None, self.debug_dir)
        if outcome.ok:
            self._state.update(state="ok", last_error=None, last_done_at=utc_now_iso(self.clock()), current_article_id=None)
            log.info("Full text of article %s (%s, %s)", job.article_id, job.source_name, job.mode)
        else:
            self._state.update(state="ok", last_error=outcome.code, current_article_id=None)
            log.warning("Full text of article %s (%s) failed: %s -> %s", job.article_id, job.source_name,
                        outcome.code, outcome.status)
        return random.uniform(*PACE)

    def browser_pace(self, prefs: dict[str, Any], now: datetime) -> BrowserPace:
        return browser_pace(prefs, now, self.local_zone)

    async def _fetch(self, job: FullTextJob) -> Page:
        if urlsplit(job.url).hostname in AGGREGATOR_HOSTS:
            # Reports collected before 0.7.3 link to Google News, which shows a robot check instead of the report.
            raise FetchFailed("aggregator_link", job.url)
        return await self.http_fetch(job.url)
