"""Statistics: how much of the news a topic, a category, a region or a source takes, and what is rising.

Everything counts reports of enabled sources. Independent sources are counted as in the score: the sources
of one media group count once. A report's category is its own AI category, else its story's (the AI has
not read most single reports). Periods are aligned to the local clock: the last 24 hours in hourly
buckets, or the last 7 / 30 days (today included) in daily buckets. The previous period, for the
changes, is equally long and ends where this one starts, so a day that is still running is compared
with an equal stretch of time.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..db import Database, utc_now_iso
from ..textnorm import build_fts_query
from .stories import StoryRepository

PERIODS = (24, 168, 720)  # hours
# How far back "rising" looks for each period: the latest window against the one before it.
RISING_WINDOW = {24: timedelta(hours=6), 168: timedelta(hours=24), 720: timedelta(hours=72)}
RISING_MIN_REPORTS = 3
RISING_LIMIT = 8
TOP_COUNTRIES = 12

OWNER = "COALESCE(NULLIF(s.owner, ''), s.slug)"
BUCKET = "CAST((julianday(a.sort_at) - julianday(:origin)) * 24.0 / :step AS INTEGER)"


@dataclass(frozen=True)
class Period:
    hours: int
    origin: datetime  # start of the first bucket (aware)
    step: timedelta
    buckets: int
    now: datetime

    @property
    def previous_start(self) -> datetime:
        return self.origin - (self.now - self.origin)

    def params(self) -> dict[str, Any]:
        return {"origin": utc_now_iso(self.origin), "until": utc_now_iso(self.now),
                "prev": utc_now_iso(self.previous_start), "step": self.step.total_seconds() / 3600}

    def starts(self) -> list[str]:
        return [utc_now_iso(self.origin + i * self.step) for i in range(self.buckets)]


def period(hours: int, now: datetime) -> Period:
    """``now`` in local time (aware). 24 hours: hourly buckets ending with the current hour; otherwise daily
    buckets from local midnight, today last."""
    if hours not in PERIODS:
        raise ValueError(hours)
    if hours == 24:
        current = now.replace(minute=0, second=0, microsecond=0)
        return Period(hours, current - timedelta(hours=23), timedelta(hours=1), 24, now)
    days = hours // 24
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return Period(hours, today - timedelta(days=days - 1), timedelta(days=1), days, now)


class StatsRepository:
    def __init__(self, db: Database, stories: StoryRepository) -> None:
        self.db = db
        self.stories = stories

    def _q(self, sql: str, params: dict[str, Any]) -> list[Any]:
        return self.db.conn.execute(sql, params).fetchall()

    # -- the whole picture ------------------------------------------------------------------------------
    def overview(self, p: Period) -> dict[str, Any]:
        params = p.params()
        base = """FROM articles a JOIN sources s ON s.id = a.source_id
                  WHERE s.enabled = 1 AND a.sort_at >= :prev AND a.sort_at <= :until"""
        now_part = "a.sort_at >= :origin"

        totals = self._q(
            f"""SELECT {now_part} AS cur, COUNT(*) AS articles, COUNT(DISTINCT {OWNER}) AS sources,
                       COUNT(DISTINCT sa.story_id) AS stories
                {base.replace('FROM articles a', 'FROM articles a LEFT JOIN story_articles sa ON sa.article_id = a.id')}
                GROUP BY cur""", params)
        by = {bool(r["cur"]): {"articles": r["articles"], "sources": r["sources"], "stories": r["stories"]} for r in totals}
        empty = {"articles": 0, "sources": 0, "stories": 0}

        timeline = Counter({r["b"]: r["n"] for r in self._q(
            f"SELECT {BUCKET} AS b, COUNT(*) AS n {base} AND {now_part} GROUP BY b", params)})

        categories = self._q(
            f"""SELECT {now_part} AS cur, COALESCE(CASE WHEN x.status = 'done' THEN x.category END, st.category) AS k,
                       COUNT(*) AS n
                FROM articles a JOIN sources s ON s.id = a.source_id
                LEFT JOIN article_ai x ON x.article_id = a.id
                LEFT JOIN story_articles sa ON sa.article_id = a.id LEFT JOIN stories st ON st.id = sa.story_id
                WHERE s.enabled = 1 AND a.sort_at >= :prev AND a.sort_at <= :until GROUP BY cur, k""", params)
        regions = self._q(f"SELECT {now_part} AS cur, s.region AS k, COUNT(*) AS n {base} GROUP BY cur, k", params)

        countries: Counter[str] = Counter()
        read = 0
        for row in self._q(
            f"""SELECT x.countries FROM articles a JOIN sources s ON s.id = a.source_id
                JOIN article_ai x ON x.article_id = a.id
                WHERE s.enabled = 1 AND x.status = 'done' AND a.sort_at >= :origin AND a.sort_at <= :until""", params):
            read += 1
            try:
                countries.update({str(c).upper() for c in json.loads(row["countries"] or "[]") if c})
            except ValueError:
                continue

        sources = self._q(
            f"""SELECT s.id, s.name, s.region,
                       SUM(a.sort_at >= :origin) AS articles, SUM(a.sort_at < :origin) AS previous,
                       COUNT(DISTINCT CASE WHEN a.sort_at >= :origin THEN sa.story_id END) AS stories,
                       MAX(a.sort_at) AS last_at
                FROM sources s
                LEFT JOIN articles a ON a.source_id = s.id AND a.sort_at >= :prev AND a.sort_at <= :until
                LEFT JOIN story_articles sa ON sa.article_id = a.id
                WHERE s.enabled = 1 GROUP BY s.id ORDER BY articles DESC, s.name""", params)

        first = self.db.conn.execute("SELECT MIN(first_seen_at) FROM articles").fetchone()[0]
        return {
            # The previous period can only be compared when collection had started by then.
            "period": {"hours": p.hours, "since": params["origin"], "until": params["until"],
                       "previous_since": params["prev"], "step_hours": params["step"],
                       "comparable": first is not None and first <= params["prev"], "collecting_since": first},
            "totals": {**by.get(True, empty), "previous": by.get(False, empty)},
            "timeline": [{"start": start, "articles": timeline.get(i, 0)} for i, start in enumerate(p.starts())],
            "categories": _shares(categories),
            "regions": _shares(regions),
            "countries": {"read": read, "items": [{"key": k, "articles": n} for k, n in countries.most_common(TOP_COUNTRIES)]},
            "sources": [{"id": r["id"], "name": r["name"], "region": r["region"], "articles": r["articles"] or 0,
                         "previous": r["previous"] or 0, "stories": r["stories"] or 0, "last_at": r["last_at"]}
                        for r in sources],
            "rising": self.rising(p),
        }

    def rising(self, p: Period) -> dict[str, Any]:
        """Stories that grew the most in the latest window compared with the window before it."""
        window = RISING_WINDOW[p.hours]
        start = p.now - window
        rows = self._q(
            f"""SELECT sa.story_id AS id,
                       SUM(a.sort_at >= :start) AS recent, SUM(a.sort_at < :start) AS previous,
                       COUNT(DISTINCT CASE WHEN a.sort_at >= :start THEN {OWNER} END) AS sources
                FROM story_articles sa JOIN articles a ON a.id = sa.article_id JOIN sources s ON s.id = a.source_id
                WHERE s.enabled = 1 AND a.sort_at >= :before AND a.sort_at <= :until
                GROUP BY sa.story_id
                HAVING recent >= :min AND recent > previous
                ORDER BY recent - previous DESC, sources DESC, id DESC LIMIT :limit""",
            {"start": utc_now_iso(start), "before": utc_now_iso(start - window), "until": utc_now_iso(p.now),
             "min": RISING_MIN_REPORTS, "limit": RISING_LIMIT})
        items = []
        for r in rows:
            story = self.stories.get(r["id"], member_limit=0)
            if story is not None:
                items.append({"story": story, "recent": r["recent"], "previous": r["previous"], "sources": r["sources"]})
        return {"window_hours": int(window.total_seconds() // 3600), "items": items}

    # -- one topic ------------------------------------------------------------------------------------
    def topic(self, p: Period, query: str, alternatives: Sequence[str] = ()) -> dict[str, Any] | None:
        """Reports about a topic (the search, with its translations) per bucket: how many, from how many
        independent sources, and their share of all reports in that bucket. None: no searchable word."""
        fts = build_fts_query(query, alternatives)
        if fts is None:
            return None
        params = {**p.params(), "fts": fts}
        base = """FROM articles a JOIN sources s ON s.id = a.source_id
                  WHERE s.enabled = 1 AND a.sort_at >= :origin AND a.sort_at <= :until"""
        match = """AND (a.id IN (SELECT rowid FROM articles_fts WHERE articles_fts MATCH :fts)
                        OR a.id IN (SELECT rowid FROM article_ai_fts WHERE article_ai_fts MATCH :fts))"""
        all_reports = Counter({r["b"]: r["n"] for r in self._q(f"SELECT {BUCKET} AS b, COUNT(*) AS n {base} GROUP BY b", params)})
        hits = {r["b"]: r for r in self._q(
            f"SELECT {BUCKET} AS b, COUNT(*) AS n, COUNT(DISTINCT {OWNER}) AS src {base} {match} GROUP BY b", params)}
        total = self._q(f"SELECT COUNT(*) AS n, COUNT(DISTINCT {OWNER}) AS src {base} {match}", params)[0]
        previous = self._q(
            f"""SELECT COUNT(*) AS n FROM articles a JOIN sources s ON s.id = a.source_id
                WHERE s.enabled = 1 AND a.sort_at >= :prev AND a.sort_at < :origin {match}""", params)[0]["n"]
        buckets = []
        for i, start in enumerate(p.starts()):
            n = hits[i]["n"] if i in hits else 0
            everything = all_reports.get(i, 0)
            buckets.append({"start": start, "articles": n, "sources": hits[i]["src"] if i in hits else 0,
                            "share": round(n / everything, 4) if everything else 0.0})
        return {"articles": total["n"], "sources": total["src"], "previous": previous, "buckets": buckets}


def _shares(rows: list[Any]) -> dict[str, Any]:
    """Counts per key in this and the previous period; ``known``/``total``: reports with a key / all."""
    cur: Counter[str] = Counter()
    prev: Counter[str] = Counter()
    total = 0
    for r in rows:
        if r["cur"]:
            total += r["n"]
        if r["k"] is None:
            continue
        (cur if r["cur"] else prev)[r["k"]] += r["n"]
    items = [{"key": k, "articles": cur[k], "previous": prev[k]} for k in sorted(set(cur) | set(prev),
                                                                               key=lambda k: (-cur[k], k))]
    return {"known": sum(cur.values()), "known_previous": sum(prev.values()), "total": total, "items": items}
