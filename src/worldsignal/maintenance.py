"""Background housekeeping a little after start-up and then every few hours: the retention policy and
the daily database backup."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .backup import BackupManager
from .db import utc_now_iso
from .fulltext.extract import MAX_CHARS, judge
from .repo.fulltext import FullTextRepository
from .repo.history import HistoryRepository
from .repo.settings import SettingsRepository

log = logging.getLogger(__name__)

FIRST_RUN_DELAY = 60.0  # let the collector and the workers start first
INTERVAL = timedelta(hours=6)
# Story matching compares new reports with the last 72 hours (stories/worker.py); a week is ample.
VECTOR_KEEP_DAYS = 7


class Maintenance:
    def __init__(
        self,
        history: HistoryRepository,
        settings: SettingsRepository,
        backups: BackupManager | None = None,
        fulltext: FullTextRepository | None = None,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.history = history
        self.settings = settings
        self.backups = backups
        self.fulltext = fulltext
        self.clock = clock
        self._state: dict[str, Any] = {
            "last_run_at": None, "last_removed": None, "last_error": None, "last_backup": None, "backup_error": None,
        }
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def status(self) -> dict[str, Any]:
        return {**self._state, "database_bytes": self.history.database_size()}

    def run_once(self) -> dict[str, int]:
        prefs = self.settings.get_preferences()
        if self.backups is not None:
            # First, so the copy still has everything the clean-up below removes.
            try:
                made = self.backups.daily(self.clock().astimezone().date(), int(prefs["backup.keep_daily"]))
                if made is not None:
                    self._state["last_backup"] = made.name
                self._state["backup_error"] = None
            except Exception as exc:  # a failed backup must not stop the retention run
                log.exception("Daily backup failed")
                self._state["backup_error"] = type(exc).__name__
        if self.fulltext is not None:
            # Texts stored under older extraction rules are held to the current ones.
            checked = self.fulltext.recheck(judge, MAX_CHARS)
            if any(checked.values()):
                log.info("Full-text re-check: %s", checked)
        removed = self.history.prune(self.clock(), int(prefs["retention.fulltext_days"]), VECTOR_KEEP_DAYS)
        self._state.update(last_run_at=utc_now_iso(self.clock()), last_removed=removed, last_error=None)
        if any(removed.values()):
            log.info("Retention: removed %s", removed)
        return removed

    def wake(self) -> None:
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    async def run_forever(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        delay = FIRST_RUN_DELAY
        while True:
            try:
                await asyncio.wait_for(self._wake.wait(), timeout=delay)
            except TimeoutError:
                pass
            self._wake.clear()
            try:
                await asyncio.to_thread(self.run_once)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.exception("Retention run failed")
                self._state["last_error"] = type(exc).__name__
            delay = INTERVAL.total_seconds()
