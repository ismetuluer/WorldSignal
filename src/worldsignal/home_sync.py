"""Keeps every report's "my country" rating in step with the settings.

At start-up, and whenever a "home.*" setting changes, every report is rated again (country.py rules) if the
rules changed since the last run (internal setting ``home.applied``), and the stories of the last days are
rescored so their "<country> link" tag and score follow at once — with or without the AI.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .country import HomeState
from .db import utc_now_iso
from .repo.articles import ArticleRepository
from .repo.settings import SettingsRepository
from .repo.stories import StoryRepository
from .stories.worker import interest_from, weights_from

log = logging.getLogger(__name__)

APPLIED = "home.applied"  # internal: the rules the stored ratings were made with
RESCORE_WINDOW = timedelta(days=7)


class HomeSync:
    def __init__(self, state: HomeState, articles: ArticleRepository, stories: StoryRepository,
                 settings: SettingsRepository, *, clock: Callable[[], datetime] = lambda: datetime.now(UTC)) -> None:
        self.state = state
        self.articles = articles
        self.stories = stories
        self.settings = settings
        self.clock = clock
        self._state: dict[str, Any] = {"running": False, "last_run_at": None, "last_changed": None}
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def status(self) -> dict[str, Any]:
        return dict(self._state)

    def sync(self) -> int | None:
        """Rate everything again if the rules changed. Returns the number of changed ratings (None: nothing to do)."""
        home = self.state.profile()
        if self.settings.get(APPLIED) == home.key:
            return None
        self._state["running"] = True
        try:
            changed = self.articles.recompute_home(home)
            now = self.clock()
            prefs = self.settings.get_preferences()
            ids = self.stories.active_story_ids(utc_now_iso(now - RESCORE_WINDOW))
            if ids:
                self.stories.recompute(ids, now, weights_from(prefs), interest_from(prefs))
            self.settings.set(APPLIED, home.key)
        finally:
            self._state["running"] = False
        self._state.update(last_run_at=utc_now_iso(self.clock()), last_changed=changed)
        log.info("Home country %s: %d report ratings changed, %d stories rescored", home.code, changed, len(ids))
        return changed

    def wake(self) -> None:
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    async def run_forever(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        while True:
            self._wake.clear()
            try:
                await asyncio.to_thread(self.sync)
            except Exception:
                log.exception("Home country ratings could not be updated")
            await self._wake.wait()
