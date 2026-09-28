"""Windows notifications: an important story is spreading quickly across independent sources.

A story qualifies when its score is at least ``notify.min_score`` and at least ``notify.min_sources``
independent sources reported it in the last three hours (the "spreading" part of the score). Each
story is announced once. During quiet hours nothing is shown; a story that still qualifies afterwards
is announced then. Several stories at once become one notification. Showing it is the desktop's
job (the tray icon); without a desktop (server-only mode) the notifier stays idle.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .db import Database, utc_now_iso
from .repo.settings import SettingsRepository

log = logging.getLogger(__name__)

CHECK_INTERVAL = 60.0
MIN_GAP = timedelta(minutes=10)  # at most one notification per ten minutes
RECENT = timedelta(hours=3)

TEXTS = {
    "tr": {
        "one": "Hızla yayılıyor · {sources} kaynak",
        "many": "{count} hikâye hızla yayılıyor",
        "many_body": "{title} ve {more} hikâye daha",
        "test_title": "World Signal bildirimi",
        "test_body": "Bildirimler çalışıyor. Önemli bir hikâye hızla yayılınca burada görünecek.",
    },
    "en": {
        "one": "Spreading fast · {sources} sources",
        "many": "{count} stories spreading fast",
        "many_body": "{title} and {more} more",
        "test_title": "World Signal notification",
        "test_body": "Notifications work. An important story that spreads quickly will appear here.",
    },
}


@dataclass
class Alert:
    title: str
    body: str
    story_id: int


def in_quiet_hours(local_hour: int, start: int, end: int) -> bool:
    """Quiet from ``start``:00 up to ``end``:00 (may wrap past midnight). start == end: never quiet."""
    if start == end:
        return False
    if start < end:
        return start <= local_hour < end
    return local_hour >= start or local_hour < end


def spreading_count(score_parts: str | None) -> int:
    try:
        tags = json.loads(score_parts or "{}").get("tags", [])
    except ValueError:
        return 0
    return max((int(t.get("count", 0)) for t in tags if t.get("kind") == "spreading"), default=0)


class Notifier:
    def __init__(
        self,
        db: Database,
        settings: SettingsRepository,
        *,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.db = db
        self.settings = settings
        self.clock = clock
        # Set by the desktop: show(title, body, story_id). None = nothing can be shown.
        self.show: Callable[[str, str, int | None], None] | None = None
        self._last_shown: datetime | None = None
        self._state: dict[str, Any] = {"last_sent_at": None, "last_story_id": None, "sent": 0}

    def status(self) -> dict[str, Any]:
        return {**self._state, "available": self.show is not None}

    def candidates(self, prefs: dict[str, Any]) -> list[dict[str, Any]]:
        since = utc_now_iso(self.clock() - RECENT)
        rows = self.db.conn.execute(
            """SELECT st.id, st.score, st.score_parts, st.ai_texts, x.texts AS rep_texts, a.title AS rep_title
               FROM stories st LEFT JOIN articles a ON a.id = st.representative_id
               LEFT JOIN article_ai x ON x.article_id = st.representative_id AND x.status = 'done'
               WHERE st.notified_at IS NULL AND st.last_seen_at >= ? AND st.score >= ?
               ORDER BY st.score DESC""",
            (since, float(prefs["notify.min_score"])),
        ).fetchall()
        need = int(prefs["notify.min_sources"])
        out = []
        for r in rows:
            n = spreading_count(r["score_parts"])
            if n >= need:
                out.append({**dict(r), "spreading": n})
        return out

    def build(self, stories: list[dict[str, Any]], lang: str) -> Alert:
        text = TEXTS.get(lang, TEXTS["tr"])

        def title_of(s: dict[str, Any]) -> str:
            # The interface language if the AI wrote it, else any AI language, else the original headline.
            for texts in (json.loads(s["ai_texts"] or "{}"), json.loads(s["rep_texts"] or "{}")):
                title = (texts.get(lang) or {}).get("title") or next(
                    (t.get("title") for t in texts.values() if t.get("title")), None)
                if title:
                    return str(title)
            return str(s["rep_title"] or "")

        top = stories[0]
        if len(stories) == 1:
            return Alert(text["one"].format(sources=top["spreading"]), title_of(top), top["id"])
        return Alert(text["many"].format(count=len(stories)),
                     text["many_body"].format(title=title_of(top), more=len(stories) - 1), top["id"])

    def check(self) -> Alert | None:
        """Announce what qualifies now (if anything) and remember it. Returns what was shown."""
        if self.show is None:
            return None
        prefs = self.settings.get_preferences()
        if not prefs["notify.enabled"]:
            return None
        now = self.clock()
        if prefs["notify.quiet"] and in_quiet_hours(
            now.astimezone().hour, int(prefs["notify.quiet_start"]), int(prefs["notify.quiet_end"])
        ):
            return None
        if self._last_shown is not None and now - self._last_shown < MIN_GAP:
            return None
        stories = self.candidates(prefs)
        if not stories:
            return None
        alert = self.build(stories, str(prefs["ui.language"]))
        with self.db.transaction() as c:
            c.executemany("UPDATE stories SET notified_at = ? WHERE id = ?", [(utc_now_iso(now), s["id"]) for s in stories])
        self._deliver(alert)
        self._last_shown = now
        self._state.update(last_sent_at=utc_now_iso(now), last_story_id=alert.story_id, sent=self._state["sent"] + 1)
        return alert

    def test(self) -> bool:
        if self.show is None:
            return False
        text = TEXTS.get(str(self.settings.get("ui.language")), TEXTS["tr"])
        self._deliver(Alert(text["test_title"], text["test_body"], 0))
        return True

    def _deliver(self, alert: Alert) -> None:
        assert self.show is not None
        try:
            self.show(alert.title, alert.body, alert.story_id or None)
        except Exception:
            log.exception("Showing a notification failed")

    async def run_forever(self) -> None:
        while True:
            try:
                await asyncio.to_thread(self.check)
            except asyncio.CancelledError:
                raise
            except Exception:
                log.exception("Notification check failed")
            await asyncio.sleep(CHECK_INTERVAL)
