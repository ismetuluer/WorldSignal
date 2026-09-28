"""Background feed collection.

Runs as an asyncio task inside the server's event loop. Each cycle picks the
feeds whose ``next_fetch_at`` has passed, fetches them politely (a global
concurrency cap and at most one request per host at a time), then writes the
results. Database work runs in worker threads so the event loop stays free.

Failure handling
----------------
* A failing feed is retried with growing delays (interval x 1, 2, 4, 8), so
  dead feeds do not hammer servers, and its error is shown in the UI.
* If every fetch in a cycle fails with a network-level error the computer is
  most likely offline: feeds are not penalised, the status reports
  ``offline`` and everything is retried shortly.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx

from ..db import Database, utc_now_iso
from ..repo.articles import ArticleRepository
from ..repo.sources import DueFeed, SourceRepository
from .rss import FetchError, FetchResult, fetch_feed, make_client

log = logging.getLogger(__name__)

NETWORK_CODES = {"network", "timeout"}
MAX_CONCURRENCY = 6
IDLE_POLL_SECONDS = 30
OFFLINE_RETRY = timedelta(minutes=2)
MAX_BACKOFF_FACTOR = 8


@dataclass
class _Outcome:
    feed: DueFeed
    result: FetchResult | None = None
    error: FetchError | None = None


class Collector:
    def __init__(
        self,
        db: Database,
        sources: SourceRepository,
        articles: ArticleRepository,
        client_factory: Callable[[], httpx.AsyncClient] = make_client,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.db = db
        self.sources = sources
        self.articles = articles
        self.client_factory = client_factory
        self.clock = clock
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        # Called (on the collector's event loop) after a cycle that stored new articles.
        self.on_new_articles: list[Callable[[], None]] = []
        self._state: dict[str, Any] = {
            "running": False,
            "busy": False,
            "offline": False,
            "last_cycle_at": None,
            "last_cycle_new": 0,
            "last_cycle_feeds": 0,
            "last_cycle_errors": 0,
        }

    # -- public ----------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        return dict(self._state)

    def request_run(self, source_id: int | None = None) -> int:
        """Mark feeds as due now and wake the loop. Safe to call from any thread."""
        count = self.sources.schedule_all_now(source_id)
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)
        return count

    async def run_forever(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._state["running"] = True
        if self._state["last_cycle_at"] is None:
            self._state["last_cycle_at"] = await asyncio.to_thread(self.sources.last_attempt_at)
        log.info("Collector started")
        try:
            async with self.client_factory() as client:
                while True:
                    # Cleared before the cycle, not after: a wake() that arrives during the cycle is kept.
                    self._wake.clear()
                    try:
                        await self.run_cycle(client)
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        log.exception("Collector cycle failed")
                        # Avoid a tight error loop if the failure repeats.
                        await asyncio.sleep(IDLE_POLL_SECONDS)
                    await self._sleep_until_next()
        finally:
            self._state["running"] = False
            log.info("Collector stopped")

    # -- internals -------------------------------------------------------------
    async def _sleep_until_next(self) -> None:
        assert self._wake is not None
        delay = IDLE_POLL_SECONDS
        next_at = await asyncio.to_thread(self.sources.next_due_at)
        if next_at is not None:
            if next_at == "":
                delay = 0
            else:
                due = datetime.strptime(next_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                delay = max(0.0, min(IDLE_POLL_SECONDS, (due - self.clock()).total_seconds()))
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=delay if delay > 0 else 0.01)
        except TimeoutError:
            pass

    async def run_cycle(self, client: httpx.AsyncClient) -> int:
        """Fetch all due feeds once. Returns the number of new articles."""
        now = self.clock()
        due = await asyncio.to_thread(self.sources.due_feeds, utc_now_iso(now))
        if not due:
            return 0
        self._state["busy"] = True
        try:
            sem = asyncio.Semaphore(MAX_CONCURRENCY)
            host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

            async def one(feed: DueFeed) -> _Outcome:
                async with sem, host_locks[urlsplit(feed.url).netloc]:
                    try:
                        return _Outcome(feed, result=await fetch_feed(client, feed.url, feed.etag, feed.last_modified))
                    except FetchError as exc:
                        return _Outcome(feed, error=exc)
                    except Exception as exc:  # parser bugs etc. must not kill the cycle
                        log.exception("Unexpected error fetching %s", feed.url)
                        return _Outcome(feed, error=FetchError("internal", repr(exc)))

            outcomes = await asyncio.gather(*(one(f) for f in due))
            return await asyncio.to_thread(self._store, outcomes)
        finally:
            self._state["busy"] = False

    def _store(self, outcomes: list[_Outcome]) -> int:
        now = self.clock()
        now_iso = utc_now_iso(now)
        errors = [o for o in outcomes if o.error is not None]
        offline = len(outcomes) >= 3 and len(errors) == len(outcomes) and all(
            o.error.code in NETWORK_CODES for o in errors  # type: ignore[union-attr]
        )
        total_new = 0
        for o in outcomes:
            feed = o.feed
            if o.error is not None:
                if offline:
                    next_at = utc_now_iso(now + OFFLINE_RETRY)
                else:
                    factor = min(2 ** feed.consecutive_failures, MAX_BACKOFF_FACTOR)
                    next_at = utc_now_iso(now + timedelta(minutes=feed.fetch_interval_min * factor) + _jitter())
                    log.warning("Feed %s failed (%s): %s", feed.url, o.error.code, o.error.detail)
                self.sources.record_failure(
                    feed.id, now=now_iso, next_at=next_at, code=o.error.code, detail=o.error.detail,
                    count_failure=not offline,
                )
                continue

            assert o.result is not None
            next_at = utc_now_iso(now + timedelta(minutes=feed.fetch_interval_min) + _jitter())
            with self.db.transaction() as c:
                new = 0
                item_count = None
                if o.result.feed is not None:
                    item_count = len(o.result.feed.entries)
                    new = self.articles.insert_entries(
                        c, source_id=feed.source_id, feed_id=feed.id, language=feed.language,
                        entries=o.result.feed.entries, now=now,
                    )
                self.sources.record_success(
                    c, feed.id, now=now_iso, next_at=next_at, etag=o.result.etag,
                    last_modified=o.result.last_modified, item_count=item_count, new_count=new,
                    not_modified=o.result.not_modified,
                )
            total_new += new

        self._state.update(
            offline=offline,
            last_cycle_at=now_iso,
            last_cycle_new=total_new,
            last_cycle_feeds=len(outcomes),
            last_cycle_errors=len(errors),
        )
        log.info("Cycle: %d feeds, %d new articles, %d errors%s", len(outcomes), total_new, len(errors),
                 " (offline)" if offline else "")
        if total_new:
            for listener in self.on_new_articles:
                listener()
        return total_new


def _jitter() -> timedelta:
    """Spread requests so all feeds do not fire at the same second."""
    return timedelta(seconds=random.randint(0, 60))
