"""Background housekeeping a little after start-up and then every few hours: the retention policy, the
daily database backup, and giving the space of removed data back to the disk."""

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
# Story matching compares new reports with the last 72 hours (stories/worker.py); a day more is enough.
VECTOR_KEEP_DAYS = 4


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
        if not self.settings.get("repair.mojibake"):  # once: reports stored with broken Turkish letters (0.13.1)
            fixed = self.history.repair_mojibake()
            self.settings.set("repair.mojibake", 1)
            if fixed:
                log.info("Repaired the letters of %d reports", fixed)
        if not self.settings.get("repair.languages"):  # once: reports labelled with their feed's language (0.14.1)
            fixed = self.history.repair_languages()
            self.settings.set("repair.languages", 1)
            if fixed:
                log.info("Corrected the language of %d reports", fixed)
        removed = self.history.prune(self.clock(), int(prefs["retention.fulltext_days"]), VECTOR_KEEP_DAYS)
        self._state.update(last_run_at=utc_now_iso(self.clock()), last_removed=removed, last_error=None)
        if any(removed.values()):
            log.info("Retention: removed %s", removed)
        freed = self.history.reclaim()
        if freed:
            log.info("Database compacted: %.1f MB given back to the disk", freed / 1e6)
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
