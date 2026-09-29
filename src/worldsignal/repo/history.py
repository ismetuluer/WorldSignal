"""History: past days, their ranking as it was at a given moment, a story's milestones, retention.

The ranking of a past day is *reconstructed* instead of stored: a story's score at time T is computed
from the members it had at T (reports published up to T) with T as "now". This works for every day
in the database, including days before this feature existed, and it reflects later corrections
(detached or merged reports). AI texts are the current ones.
"""

from __future__ import annotations

import logging
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, tzinfo
from typing import Any

from ..db import Database, utc_now_iso
from ..textnorm import fold_for_search, repair_mojibake
from ..stories.score import Interest, Member, independent_sources, score_story
from .stories import StoryRepository, parse_iso

log = logging.getLogger(__name__)

# Moments of a day the history can be seen at.
MOMENTS = ("morning", "day")
MORNING_WINDOW = timedelta(hours=24)  # the morning view shows what the feed showed: the last 24 hours
SOURCE_MILESTONES = (3, 5, 10, 20, 40)


@dataclass
class DayView:
    day: str
    moment: str
    as_of: datetime
    window_start: datetime


def local_datetime(day: str, hour: int, tz: tzinfo | None = None) -> datetime:
    """``day`` at ``hour``:00 on the user's clock, as an aware datetime (local rules incl. DST)."""
    d = date.fromisoformat(day)
    naive = datetime(d.year, d.month, d.day, hour)
    return naive.replace(tzinfo=tz) if tz is not None else naive.astimezone()


def next_day(day: str) -> str:
    return (date.fromisoformat(day) + timedelta(days=1)).isoformat()


def day_view(day: str, moment: str, morning_hour: int, now: datetime, tz: tzinfo | None = None) -> DayView:
    """Which moment and which reports a day view shows.

    morning: the feed as it was at ``morning_hour`` that day (the last 24 hours before it).
    day:     the reports published that calendar day, ranked as at the end of the day.
    Neither looks past ``now`` (today's views are the state so far)."""
    start = local_datetime(day, 0, tz)
    if moment == "morning":
        as_of = local_datetime(day, morning_hour, tz)
        window_start = as_of - MORNING_WINDOW
    else:
        as_of = local_datetime(next_day(day), 0, tz)
        window_start = start
    return DayView(day, moment, min(as_of, now), window_start)


class HistoryRepository:
    def __init__(self, db: Database, stories: StoryRepository) -> None:
        self.db = db
        self.stories = stories

    # -- calendar ---------------------------------------------------------------------------------
    def month(self, month: str, tz: tzinfo | None = None) -> list[dict[str, Any]]:
        """Days of ``YYYY-MM`` that have reports: [{day, articles, stories}] (local days)."""
        first = date.fromisoformat(f"{month}-01")
        mid = local_datetime(f"{month}-15", 12, tz)
        offset_min = int((mid.utcoffset() or timedelta()).total_seconds() // 60)
        modifier = f"{offset_min:+d} minutes"
        start = local_datetime(first.isoformat(), 0, tz).astimezone(UTC)
        nxt = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = local_datetime(nxt.isoformat(), 0, tz).astimezone(UTC)
        rows = self.db.conn.execute(
            """SELECT date(replace(rtrim(a.sort_at, 'Z'), 'T', ' '), ?) AS day,
                      COUNT(*) AS articles, COUNT(DISTINCT sa.story_id) AS stories
               FROM articles a
               JOIN sources s ON s.id = a.source_id AND s.enabled = 1
               LEFT JOIN story_articles sa ON sa.article_id = a.id
               WHERE a.sort_at >= ? AND a.sort_at < ?
               GROUP BY day ORDER BY day""",
            (modifier, utc_now_iso(start), utc_now_iso(end)),
        ).fetchall()
        return [{"day": r["day"], "articles": r["articles"], "stories": r["stories"]} for r in rows]

    # -- ranking of a past moment ---------------------------------------------------------------------
    def ranking(
        self,
        view: DayView,
        weights: dict[str, float],
        interest: Interest,
        *,
        min_sources: int = 1,
        limit: int = 40,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Stories with reports in the view's window, scored as at ``view.as_of``."""
        as_of_iso = utc_now_iso(view.as_of)
        start_iso = utc_now_iso(view.window_start)
        rows = self.db.conn.execute(
            """SELECT sa.story_id, a.id, a.sort_at, a.title, s.region, s.reliability,
                      COALESCE(NULLIF(s.owner, ''), s.slug) AS owner_key,
                      (SELECT group_concat(json_extract(j.value, '$.title'), ' ') FROM json_each(x.texts) j) AS ai_titles,
                      x.category, a.home_relevance AS turkey_relevance
               FROM story_articles sa
               JOIN articles a ON a.id = sa.article_id
               JOIN sources s ON s.id = a.source_id AND s.enabled = 1
               LEFT JOIN article_ai x ON x.article_id = a.id AND x.status = 'done'
               WHERE a.sort_at <= ?
                 AND sa.story_id IN (
                     SELECT sa2.story_id FROM story_articles sa2 JOIN articles a2 ON a2.id = sa2.article_id
                     WHERE a2.sort_at > ? AND a2.sort_at <= ?)
               ORDER BY a.sort_at""",
            (as_of_iso, start_iso, as_of_iso),
        ).fetchall()
        by_story: dict[int, list[Any]] = defaultdict(list)
        for r in rows:
            by_story[r["story_id"]].append(r)

        scored = []
        for sid, members in by_story.items():
            ms = [
                Member(r["id"], r["owner_key"], r["reliability"], parse_iso(r["sort_at"]), r["region"],
                       f"{r['title']} {r['ai_titles'] or ''}", r["category"], r["turkey_relevance"])
                for r in members
            ]
            if len(independent_sources(ms)) < min_sources:
                continue
            categories = Counter(r["category"] for r in members if r["category"])
            category = categories.most_common(1)[0][0] if categories else None
            result = score_story(ms, view.as_of, weights=weights, interest=interest, category=category)
            scored.append((result, sid, members))
        scored.sort(key=lambda x: (-x[0].score, -max(parse_iso(r["sort_at"]).timestamp() for r in x[2])))

        items = []
        for result, sid, members in scored[offset:offset + max(1, min(limit, 200))]:
            story = self.stories.get(sid)
            if story is None:
                continue
            known = {r["id"] for r in members}
            then = [m for m in story["members"] if m["id"] in known]
            story["sources"] = sorted({m["source_name"] for m in then})
            story["members"] = then[:6]
            story["score"] = result.score
            story["score_parts"] = result.parts()
            story["source_count"] = result.source_count
            story["article_count"] = len(members)
            story["turkey_relevance"] = result.turkey_relevance
            story["last_seen_at"] = members[-1]["sort_at"]
            items.append(story)

        unclustered = self.db.conn.execute(
            """SELECT COUNT(*) FROM articles a JOIN sources s ON s.id = a.source_id AND s.enabled = 1
               WHERE a.sort_at > ? AND a.sort_at <= ?
                 AND NOT EXISTS (SELECT 1 FROM story_articles sa WHERE sa.article_id = a.id)""",
            (start_iso, as_of_iso),
        ).fetchone()[0]
        return {
            "day": view.day, "moment": view.moment, "as_of": as_of_iso, "window_start": start_iso,
            "items": items, "total": len(scored), "unclustered": int(unclustered),
        }

    # -- milestones of one story ------------------------------------------------------------------
    def milestones(self, story_id: int, language: str = "tr") -> list[dict[str, Any]]:
        """Turning points: first report, independent-source thresholds, first link to the user's country,
        first source in the user's ``language`` (the interface language), latest report."""
        rows = self.db.conn.execute(
            """SELECT a.id, a.sort_at, s.name AS source_name, COALESCE(NULLIF(s.owner, ''), s.slug) AS owner_key,
                      COALESCE(a.language, s.language) AS language, a.home_relevance AS turkey_relevance
               FROM story_articles sa
               JOIN articles a ON a.id = sa.article_id
               JOIN sources s ON s.id = a.source_id AND s.enabled = 1
               LEFT JOIN article_ai x ON x.article_id = a.id AND x.status = 'done'
               WHERE sa.story_id = ? ORDER BY a.sort_at, a.id""",
            (story_id,),
        ).fetchall()
        if not rows:
            return []
        out: list[dict[str, Any]] = [{"kind": "first", "at": rows[0]["sort_at"], "source": rows[0]["source_name"]}]
        owners: set[str] = set()
        thresholds = list(SOURCE_MILESTONES)
        turkey_seen = False
        # A story that started in the user's language has no "first source in your language" turning point.
        own_seen = rows[0]["language"] == language
        for r in rows:
            owners.add(r["owner_key"])
            while thresholds and len(owners) >= thresholds[0]:
                out.append({"kind": "sources", "at": r["sort_at"], "count": thresholds.pop(0), "source": r["source_name"]})
            if not turkey_seen and r["turkey_relevance"] == "direct":
                turkey_seen = True
                out.append({"kind": "turkey", "at": r["sort_at"], "source": r["source_name"]})
            if not own_seen and r["language"] == language:
                own_seen = True
                out.append({"kind": "own_language_source", "at": r["sort_at"], "source": r["source_name"],
                            "language": language})
        if len(rows) > 1:
            out.append({"kind": "latest", "at": rows[-1]["sort_at"], "source": rows[-1]["source_name"]})
        return out

    # -- retention ----------------------------------------------------------------------------------
    def prune(self, now: datetime, fulltext_days: int, vector_days: int) -> dict[str, int]:
        """Delete what is only needed for a while. Titles, summaries, AI texts, stories and notes stay.

        fulltext_days: full texts (and their translations) older than this are removed; 0 keeps them.
        vector_days:   story-matching vectors are only used for recent reports; older ones are removed."""
        removed = {"fulltexts": 0, "vectors": 0}
        with self.db.transaction() as c:
            if fulltext_days > 0:
                cutoff = utc_now_iso(now - timedelta(days=fulltext_days))
                removed["fulltexts"] = c.execute(
                    """DELETE FROM article_fulltext WHERE article_id IN (
                           SELECT f.article_id FROM article_fulltext f JOIN articles a ON a.id = f.article_id
                           WHERE a.sort_at < ?)""",
                    (cutoff,),
                ).rowcount
            cutoff = utc_now_iso(now - timedelta(days=vector_days))
            removed["vectors"] = c.execute(
                """DELETE FROM article_embeddings WHERE article_id IN (
                       SELECT e.article_id FROM article_embeddings e JOIN articles a ON a.id = e.article_id
                       WHERE a.sort_at < ?)""",
                (cutoff,),
            ).rowcount
        return removed

    def repair_mojibake(self, batch: int = 2000) -> int:
        """Titles and summaries a feed delivered as UTF-8-read-as-Windows-1252 ("SoykÄ±rÄ±m") are written correctly,
        and their search index with them. Returns the number of reports repaired."""
        repaired, last = 0, 0
        while True:
            rows = self.db.conn.execute(
                "SELECT id, title, summary, author FROM articles WHERE id > ? ORDER BY id LIMIT ?", (last, batch)
            ).fetchall()
            if not rows:
                return repaired
            last = rows[-1]["id"]
            with self.db.transaction() as c:
                for r in rows:
                    title, summary, author = (repair_mojibake(r["title"]), repair_mojibake(r["summary"]),
                                              repair_mojibake(r["author"]) or None)
                    if (title, summary, author) == (r["title"], r["summary"], r["author"]):
                        continue
                    c.execute("UPDATE articles SET title = ?, summary = ?, author = ? WHERE id = ?",
                              (title, summary, author, r["id"]))
                    c.execute("UPDATE articles_fts SET title = ?, summary = ? WHERE rowid = ?",
                              (fold_for_search(title), fold_for_search(summary), r["id"]))
                    repaired += 1

    def reclaim(self, min_ratio: float = 0.2, min_bytes: int = 16_000_000) -> int:
        """Give the space of deleted rows back to the disk (VACUUM) once it is a noticeable part of the file.
        SQLite reuses free pages but never shrinks the file by itself. Returns the bytes freed (0: not needed or
        the database was busy; it is tried again on the next run)."""
        page_size = self.db.conn.execute("PRAGMA page_size").fetchone()[0]
        pages = self.db.conn.execute("PRAGMA page_count").fetchone()[0]
        free = self.db.conn.execute("PRAGMA freelist_count").fetchone()[0]
        if not pages or free / pages < min_ratio or free * page_size < min_bytes:
            return 0
        try:
            self.db.conn.execute("VACUUM")
        except sqlite3.OperationalError as exc:
            log.warning("Could not compact the database now: %s", exc)
            return 0
        return int((pages - self.db.conn.execute("PRAGMA page_count").fetchone()[0]) * page_size)

    def database_size(self) -> int:
        """Bytes used by the database file (pages in use)."""
        page_size = self.db.conn.execute("PRAGMA page_size").fetchone()[0]
        pages = self.db.conn.execute("PRAGMA page_count").fetchone()[0]
        free = self.db.conn.execute("PRAGMA freelist_count").fetchone()[0]
        return int(page_size * (pages - free))

