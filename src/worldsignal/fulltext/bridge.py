"""The browser extension's side of the full-text queue (decision 2026-10-01: subscription sites are read in the user's
own browser). The program decides what and when (the same queue and human pace as the background worker); the
extension asks for one page at a time, reads it in a minimized window and posts its HTML back. A job is lent under a
lease: a result for a lost lease is refused. The page was asked for once the lease was handed out, so an expired lease
(counted as ``timeout``), a page that did not load or could not be read, and a page too large to accept all count as a
failed attempt (after ``MAX_ATTEMPTS`` the article is given up) and rest the site. Only the user closing the window
(``tab_closed``) gives the job back as it was."""

from __future__ import annotations

import asyncio
import hmac
import logging
import math
import secrets
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, tzinfo
from typing import Any
from urllib.parse import urlsplit

from ..db import utc_now_iso
from ..repo.fulltext import FullTextJob, FullTextRepository
from ..repo.settings import SettingsRepository
from .fetch import Page
from .outcome import record_page
from .worker import AGGREGATOR_HOSTS, browser_pace

log = logging.getLogger(__name__)

LEASE = timedelta(minutes=5)
METHOD = "extension"  # article_fulltext.method for everything this reader stores, text or failure
# The extension counts as connected while it keeps to the wait it was handed (plus this much slack: alarms are not
# exact); the user is warned only after a longer silence, and not before the program has run this long.
CONNECTED_GRACE = timedelta(seconds=60)
WARN_AFTER = timedelta(minutes=10)
EXTENSION_ERRORS = {"tab_closed", "load_failed", "timeout", "script_failed"}  # what the extension may report
REJECTIONS = {"too_large"}  # the program's own refusals of a result (``reject``); the extension cannot send these
GIVE_BACK = {"tab_closed"}  # the user closed the window: the attempt is not counted
WAIT = {"disabled": 300, "resting": 300, "busy": 30, "idle": 60}
# After the extension's own trouble with a site (error or lost lease) the site is left alone for 1, 2, 4 ... minutes
# (at most 30), so a page that never loads is not reopened at the poll rate. Kept in memory only.
COOLDOWN_START = timedelta(minutes=1)
COOLDOWN_MAX = timedelta(minutes=30)
MIN_COOLDOWN_WAIT = 30
MAX_BACKOFF_STEPS = 10  # 1 minute * 2**10 is far beyond the 30 minute cap
SILENT_LAUNCH = timedelta(minutes=10)  # the extension has been silent this long: the browser may be closed
LAUNCH_EVERY = timedelta(minutes=30)


class UnknownLease(Exception):
    pass


def _unreadable(url: str) -> str | None:
    """Why a queued link is not handed to the extension at all: not a web page, or an aggregator's redirect page."""
    try:
        parts = urlsplit(url)
        host = parts.hostname
    except ValueError:  # e.g. a broken IPv6 address
        return "not_article"
    if parts.scheme not in ("http", "https") or not host:
        return "not_article"
    if host in AGGREGATOR_HOSTS:
        return "aggregator_link"
    return None


@dataclass
class Lease:
    id: str
    job: FullTextJob
    previous: str | None
    until: datetime


class ExtensionBridge:
    def __init__(self, repo: FullTextRepository, settings: SettingsRepository, *, resting: Callable[[], bool],
                 clock: Callable[[], datetime] = lambda: datetime.now(UTC), local_zone: tzinfo | None = None) -> None:
        self.repo = repo
        self.settings = settings
        self.resting = resting
        self.clock = clock
        self.local_zone = local_zone
        self.on_translation_queued: Callable[[], None] = lambda: None
        self._lock = threading.Lock()
        self._lease: Lease | None = None
        self.last_seen: datetime | None = None
        self._last_wait = timedelta(0)  # the wait handed out with the last answer to the extension
        self._started = clock()  # start-up, or the last time the extension was not the reader (``_note_reader``)
        self._reader_active = True  # as last seen by ``_note_reader`` (start-up itself starts the grace)
        self.last_error: str | None = None
        self.last_source: str | None = None
        self._launched_at: datetime | None = None
        self._day = ""
        self._read_today = 0
        self._cooldown: dict[int, tuple[int, datetime]] = {}  # source id -> (failures in a row, resting until)

    def _wait(self, reason: str) -> dict[str, Any]:
        return {"wait_seconds": WAIT[reason], "reason": reason}

    def _start_cooldown(self, source_id: int, now: datetime) -> None:
        """Caller holds the lock."""
        # The count stops growing where the cap is reached long since, so the arithmetic can never overflow.
        failures = min(self._cooldown.get(source_id, (0, now))[0] + 1, MAX_BACKOFF_STEPS + 1)
        delay = min(COOLDOWN_START * 2 ** min(failures - 1, MAX_BACKOFF_STEPS), COOLDOWN_MAX)
        self._cooldown[source_id] = (failures, now + delay)

    def clear_cooldown(self, source_id: int) -> None:
        """The user asked to try the site again (test / resume): its in-memory rest ends now."""
        with self._lock:
            self._cooldown.pop(source_id, None)

    def _cooling(self, now: datetime) -> dict[int, datetime]:
        """Sources resting right now, with the time each is free again. Caller holds the lock."""
        return {sid: until for sid, (_, until) in self._cooldown.items() if until > now}

    def next(self) -> dict[str, Any]:
        now = self.clock()
        answer = self._answer(now)
        # How long the extension was told to stay away (while reading: the lease), so its silence is judged fairly.
        wait = LEASE if "lease" in answer else timedelta(seconds=answer["wait_seconds"])
        self.last_seen, self._last_wait = now, wait
        return answer

    def _note_reader(self, prefs: dict[str, Any], now: datetime) -> bool:
        """Is the extension the reader? While it is not (and when it is seen again as the reader), the start-up grace
        starts over, so switching to the extension later gets the full ``WARN_AFTER`` before any warning. The switch is
        seen at the next status poll or extension request."""
        active = prefs.get("fulltext.reader") == "extension"
        if not active or not self._reader_active:
            self._started = now
        self._reader_active = active
        return active

    def leased_article(self) -> int | None:
        """The article the extension is reading right now (kept in the queue by ``drop_stale_auto``)."""
        with self._lock:
            return self._lease.job.article_id if self._lease else None

    def _answer(self, now: datetime) -> dict[str, Any]:
        prefs = self.settings.get_preferences()
        if not self._note_reader(prefs, now) or not prefs.get("fulltext.enabled", True):
            with self._lock:
                if self._lease is not None:
                    # Switched off while a page was out: forget the lease (a late result is refused). The page may
                    # have been asked for, so its attempt time stays; nothing is counted against the article.
                    log.info("Extension lease for article %s dropped: the extension no longer reads",
                             self._lease.job.article_id)
                    self._lease = None
            return self._wait("disabled")
        with self._lock:
            if self._lease is not None:
                if self._lease.until > now:
                    return self._wait("busy")
                expired, self._lease = self._lease, None  # gone first: whatever follows, it is never expired twice
                log.info("Extension lease for article %s expired", expired.job.article_id)
                self._failed(expired.job, "timeout", now)  # the page was asked for: the visit counts
            resting = self.resting()
            cooling = self._cooling(now)  # a resting site never holds up the others
            while True:
                job = self.repo.next_job(now, int(prefs.get("fulltext.per_site_hour", 4)),
                                         browser_pace(prefs, now, self.local_zone), resting, ("browser",),
                                         exclude_sources=list(cooling))
                unreadable = None if job is None else _unreadable(job.url)
                if unreadable is None:
                    break
                # Never handed to the extension (nothing is opened); both codes are final, so the loop ends.
                self.repo.store_failure(job, unreadable, now, METHOD)
                log.info("Article %s not given to the extension: %s", job.article_id, unreadable)
            if job is None:
                if resting:  # outside the working hours the long wait is the honest one
                    return self._wait("resting")
                if cooling:  # nothing else to read: wait for the first site to be free again
                    seconds = math.ceil((min(cooling.values()) - now).total_seconds())
                    return {"wait_seconds": max(seconds, MIN_COOLDOWN_WAIT), "reason": "cooldown"}
                return self._wait("idle")
            previous = self.repo.mark_attempt(job.article_id, now)
            self._lease = Lease(secrets.token_urlsafe(16), job, previous, now + LEASE)
            return {"lease": self._lease.id, "article_id": job.article_id, "url": job.url, "source": job.source_name}

    def _failed(self, job: FullTextJob, code: str, now: datetime) -> str:
        """The page was asked for but gave no text: the attempt counts (``store_failure``) and the site rests.
        Caller holds the lock."""
        status = self.repo.store_failure(job, code, now, METHOD)
        self._start_cooldown(job.source_id, now)
        self.last_source, self.last_error = job.source_name, code
        log.info("Extension could not read article %s: %s -> %s", job.article_id, code, status)
        return status

    def _take(self, lease: str) -> Lease:
        """The open lease, if ``lease`` is its id (it is closed then). Caller holds the lock."""
        held = self._lease
        # Bytes: compare_digest refuses a non-ASCII str, and "\ud800" (valid JSON) cannot be encoded strictly:
        # a malformed lease must be refused, not crash.
        if held is None or not hmac.compare_digest(held.id.encode(), lease.encode("utf-8", "surrogatepass")):
            raise UnknownLease(lease)
        self._lease = None
        return held

    def reject(self, lease: str, code: str) -> dict[str, Any]:
        """The program refuses the result itself (``REJECTIONS``, e.g. a page too large to accept): the lease is
        closed and the attempt counts, so the queue does not wait for the lease to run out."""
        if code not in REJECTIONS:
            raise ValueError(code)
        now = self.clock()
        self.last_seen, self._last_wait = now, timedelta(0)  # the extension asks again right away
        with self._lock:
            held = self._take(lease)
            return {"status": self._failed(held.job, code, now), "error": code}

    def result(self, lease: str, *, html: str | None = None, final_url: str | None = None,
               error: str | None = None, status: int | None = None) -> dict[str, Any]:
        """``status``: the page's HTTP status as the browser saw it (None: unknown), so a refusal pauses the site."""
        now = self.clock()
        self.last_seen, self._last_wait = now, timedelta(0)  # the extension asks again right away
        with self._lock:
            held = self._take(lease)
            job = held.job
            self.last_source = job.source_name
            if error in GIVE_BACK:  # the user closed the window: as if the page had never been opened
                self.repo.release_attempt(job.article_id, held.previous)
                self._start_cooldown(job.source_id, now)
                self.last_error = error
                log.info("Extension could not read article %s: %s", job.article_id, error)
                return {"status": "pending"}
            if error is not None or not html:
                code = error or "load_failed"
                return {"status": self._failed(job, code, now), "error": code}
        try:
            outcome = record_page(self.repo, job, Page(status, html, final_url or job.url),
                                  self.settings.get_preferences(), now, self.on_translation_queued, method=METHOD)
        except Exception:
            # Our own failure, not the site's: nothing was stored, the article stays as it was and the site rests.
            self.repo.release_attempt(job.article_id, held.previous)
            with self._lock:
                self._start_cooldown(job.source_id, now)
            self.last_error = "record_failed"
            raise
        with self._lock:
            self._cooldown.pop(job.source_id, None)  # a real answer from the site: the backoff starts over
        self.last_error = outcome.code
        day = utc_now_iso(now)[:10]
        if day != self._day:
            self._day, self._read_today = day, 0
        if outcome.ok:
            self._read_today += 1
        log.info("Extension read article %s (%s): %s", job.article_id, job.source_name, outcome.status)
        return {"status": outcome.status, "error": outcome.code}

    def silent_for(self) -> timedelta | None:
        return None if self.last_seen is None else self.clock() - self.last_seen

    def launch_if_needed(self, find_browser: Callable[[str], Any], is_running: Callable[[Any], bool],
                         start: Callable[[Any], None]) -> bool:
        """Extension mode, nothing heard for a while, the browser not running: start it (at most twice an hour)."""
        prefs = self.settings.get_preferences()
        now = self.clock()
        if prefs.get("fulltext.reader") != "extension" or not prefs.get("fulltext.launch_browser", True):
            return False
        silent = self.silent_for()
        if silent is not None and silent < SILENT_LAUNCH:
            return False
        if self._launched_at is not None and now - self._launched_at < LAUNCH_EVERY:
            return False
        browser = find_browser(str(prefs.get("fulltext.browser_path") or ""))
        if browser is None or is_running(browser.executable):
            return False
        self._launched_at = now
        log.info("Starting %s for the extension (no window)", browser.name)
        start(browser.executable)
        return True

    async def watch_forever(self) -> None:
        from .fetch import browser_for
        from .launcher import is_running, start_hidden

        while True:
            try:
                await asyncio.to_thread(self.launch_if_needed, browser_for, is_running, start_hidden)
            except Exception:
                log.exception("Starting the browser for the extension failed")
            await asyncio.sleep(60)

    def status(self) -> dict[str, Any]:
        """``connected``: the extension asked within the wait it was handed. ``warn``: the extension reads, but has
        been silent for long enough to tell the user (never at start-up, never while it keeps to a long wait)."""
        now = self.clock()
        active = self._note_reader(self.settings.get_preferences(), now)
        silent = self.silent_for()
        connected = silent is not None and silent <= self._last_wait + CONNECTED_GRACE
        # Never within WARN_AFTER of start-up or of switching to the extension; then only after a long silence.
        overdue = now - self._started > WARN_AFTER and (
            silent is None or silent > max(WARN_AFTER, self._last_wait + CONNECTED_GRACE))
        with self._lock:
            reading = self._lease.job.source_name if self._lease else None
        return {
            "connected": connected,
            "warn": active and not connected and overdue,
            "last_seen": utc_now_iso(self.last_seen) if self.last_seen else None,
            "read_today": self._read_today if self._day == utc_now_iso(now)[:10] else 0,
            "reading": reading, "last_source": self.last_source, "last_error": self.last_error,
        }
