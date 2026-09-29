"""Articles collected from feeds, with a Turkish-aware full-text index."""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from ..collector.rss import ParsedEntry
from ..country import HomeProfile
from ..db import Database, utc_now_iso
from ..flags import MARKER_WINDOW, group_condition, has_breaking_marker, is_exclusive
from ..textnorm import build_fts_query, fold_for_search
from .sources import region_condition

# Small clock differences between servers are ignored.
FUTURE_TOLERANCE = timedelta(minutes=5)
# Real time-zone mistakes are at most UTC+14.
MAX_TZ_ERROR = timedelta(hours=14)


def timezone_correction(entries: Sequence[ParsedEntry], now: datetime) -> timedelta:
    """Detect a feed that labels local time as UTC (e.g. Turkish time with "GMT").

    Such feeds put all their recent items hours in the future. When at least
    two items are ahead of ``now``, the whole feed is shifted back by the
    smallest whole number of hours that brings the newest item into the past.
    A single future item is more likely a scheduled/embargoed story and is
    simply clamped by the caller instead.
    """
    ahead = [
        e.published_at - now
        for e in entries
        if e.published_at is not None and FUTURE_TOLERANCE < e.published_at - now <= MAX_TZ_ERROR
    ]
    if len(ahead) < 2:
        return timedelta(0)
    return timedelta(hours=math.ceil(max(ahead) / timedelta(hours=1)))


@dataclass
class ArticleFilter:
    since: str | None = None
    until: str | None = None
    source_ids: Sequence[int] = field(default_factory=tuple)
    regions: Sequence[str] = field(default_factory=tuple)
    groups: Sequence[str] = field(default_factory=tuple)
    languages: Sequence[str] = field(default_factory=tuple)
    categories: Sequence[str] = field(default_factory=tuple)
    turkey_only: bool = False  # only articles related (directly or indirectly) to the user's country
    query: str | None = None
    alternatives: Sequence[str] = field(default_factory=tuple)  # translations of the query (ai/query.py)
    before: tuple[str, int] | None = None  # pagination cursor (sort_at, id)
    limit: int = 100


class ArticleRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def insert_entries(
        self,
        c: sqlite3.Connection,
        *,
        source_id: int,
        feed_id: int | None,
        language: str | None,
        entries: Sequence[ParsedEntry],
        now: datetime,
    ) -> int:
        """Store new entries; already-known ones are ignored. Returns the number added.

        ``published_at`` keeps what the feed said; ``sort_at`` is the best
        estimate of the real time (time-zone mistakes corrected, never in the
        future, first-seen time when the feed gives no date). Must be called inside a transaction (``c``) so that articles and their
        search index rows are written together.
        """
        now_iso = utc_now_iso(now)
        correction = timezone_correction(entries, now)
        added = 0
        for e in entries:
            published_iso = utc_now_iso(e.published_at) if e.published_at else None
            corrected = e.published_at - correction if e.published_at else None
            if corrected is None or corrected > now + FUTURE_TOLERANCE:
                sort_at = now_iso
            else:
                sort_at = utc_now_iso(corrected)
            row = c.execute(
                """INSERT INTO articles (source_id, feed_id, dedupe_key, url, title, summary, author, language,
                       published_at, first_seen_at, sort_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(source_id, dedupe_key) DO NOTHING
                   RETURNING id""",
                (source_id, feed_id, e.dedupe_key, e.url, e.title, e.summary, e.author, language,
                 published_iso, now_iso, sort_at),
            ).fetchone()
            if row is None:
                continue
            c.execute(
                "INSERT INTO articles_fts (rowid, title, summary) VALUES (?, ?, ?)",
                (row[0], fold_for_search(e.title), fold_for_search(e.summary)),
            )
            added += 1
        return added

    def _where(self, f: ArticleFilter, *, paginate: bool) -> tuple[str, list[Any]] | None:
        """Build the WHERE part shared by list() and count(). None = matches nothing.

        Queries alias articles as ``a``, sources as ``s`` and the AI row as ``x`` (LEFT JOIN).
        """
        where: list[str] = []
        params: list[Any] = []
        if f.query:
            fts = build_fts_query(f.query, f.alternatives)
            if fts is None:
                return None
            # Match the original text or the Turkish AI title/summary.
            where.append(
                "(a.id IN (SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?)"
                " OR a.id IN (SELECT rowid FROM article_ai_fts WHERE article_ai_fts MATCH ?))"
            )
            params.extend([fts, fts])
        if f.since:
            where.append("a.sort_at >= ?")
            params.append(f.since)
        if f.until:
            where.append("a.sort_at < ?")
            params.append(f.until)
        for column, values in (
            ("a.source_id", f.source_ids),
            ("COALESCE(a.language, s.language)", f.languages),
            ("x.category", f.categories),
        ):
            if values:
                where.append(f"{column} IN ({','.join('?' * len(values))})")
                params.extend(values)
        if groups := group_condition(f.groups):
            where.append(groups[0])
            params.extend(groups[1])
        if regions := region_condition(f.regions):
            where.append(regions[0])
            params.extend(regions[1])
        if f.turkey_only:
            where.append("a.home_relevance IN ('direct', 'indirect')")
        if paginate and f.before:
            where.append("(a.sort_at < ? OR (a.sort_at = ? AND a.id < ?))")
            params.extend([f.before[0], f.before[0], f.before[1]])
        where.append("s.enabled = 1")
        return " AND ".join(where), params

    def list(self, f: ArticleFilter) -> list[dict[str, Any]]:
        built = self._where(f, paginate=True)
        if built is None:
            return []
        where, params = built
        sql = f"""
            SELECT a.id, a.url, a.title, a.summary, a.author, a.published_at, a.first_seen_at, a.sort_at,
                   COALESCE(a.language, s.language) AS language,
                   s.id AS source_id, s.name AS source_name, s.region, s.catalog_group, s.paywalled,
                   x.status AS ai_status, x.texts AS ai_texts, x.brief AS ai_brief, x.category, x.countries,
                   a.home_relevance AS turkey_relevance, a.home_links AS turkey_links, x.issues AS ai_issues, x.model AS ai_model, x.error_code AS ai_error,
                   ft.status AS fulltext_status, ft.error_code AS fulltext_error, ft.chars AS fulltext_chars,
                   ft.translate_status AS fulltext_translate_status
            FROM articles a
            JOIN sources s ON s.id = a.source_id
            LEFT JOIN article_ai x ON x.article_id = a.id
            LEFT JOIN article_fulltext ft ON ft.article_id = a.id
            WHERE {where}
            ORDER BY a.sort_at DESC, a.id DESC
            LIMIT ?"""
        rows = self.db.conn.execute(sql, [*params, max(1, min(f.limit, 500))]).fetchall()
        items = [dict(r) for r in rows]
        now = datetime.now(UTC)
        for item in items:
            item["paywalled"] = bool(item["paywalled"])
            item["exclusive"] = is_exclusive(item["title"])
            at = datetime.fromisoformat(item["sort_at"].replace("Z", "+00:00"))
            item["breaking"] = has_breaking_marker(item["title"]) and now - at <= MARKER_WINDOW
            for key in ("ai_issues", "countries", "turkey_links"):
                item[key] = json.loads(item[key]) if item[key] else []
            item["ai_texts"] = json.loads(item["ai_texts"] or "{}")
            if item["ai_status"] != "done":
                # Only finished AI output is exposed; partial rows are queue bookkeeping.
                for key in ("category", "ai_model", "turkey_relevance"):
                    item[key] = None
                item["ai_texts"] = {}
                item["turkey_links"] = []
        return items

    def recompute_home(self, home: HomeProfile, batch: int = 2000) -> int:
        """Rate every report the AI has read again (the user changed their country or what counts as related).
        Returns the number of reports whose rating changed."""
        changed = 0
        last = 0
        while True:
            rows = self.db.conn.execute(
                """SELECT a.id, a.title, a.summary, a.home_relevance, a.home_links,
                          x.countries, x.topics, x.mentions_turkey
                   FROM articles a JOIN article_ai x ON x.article_id = a.id AND x.status = 'done'
                   WHERE a.id > ? ORDER BY a.id LIMIT ?""",
                (last, batch),
            ).fetchall()
            if not rows:
                return changed
            updates = []
            for r in rows:
                level, links = _rate(home, r)
                links_json = json.dumps(links)
                if level != r["home_relevance"] or links_json != r["home_links"]:
                    updates.append((level, links_json, r["id"]))
            if updates:
                with self.db.transaction() as c:
                    c.executemany("UPDATE articles SET home_relevance = ?, home_links = ? WHERE id = ?", updates)
                changed += len(updates)
            last = rows[-1]["id"]

    def count(self, f: ArticleFilter) -> int:
        """Number of articles matching the filter (ignores the pagination cursor)."""
        built = self._where(f, paginate=False)
        if built is None:
            return 0
        where, params = built
        sql = (
            "SELECT COUNT(*) FROM articles a JOIN sources s ON s.id = a.source_id "
            f"LEFT JOIN article_ai x ON x.article_id = a.id WHERE {where}"
        )
        return int(self.db.conn.execute(sql, params).fetchone()[0])

    def counts(self, since_iso: str) -> dict[str, int]:
        row = self.db.conn.execute(
            """SELECT COUNT(*) AS total, SUM(a.first_seen_at >= ?) AS recent
               FROM articles a JOIN sources s ON s.id = a.source_id WHERE s.enabled = 1""",
            (since_iso,),
        ).fetchone()
        return {"total": row["total"] or 0, "recent": row["recent"] or 0}

    def source_languages(self) -> list[str]:
        """Languages the enabled sources publish in, the most common first (search translations, ai/query.py)."""
        rows = self.db.conn.execute(
            """SELECT language FROM sources WHERE enabled = 1 AND language IS NOT NULL AND language != ''
               GROUP BY language ORDER BY COUNT(*) DESC, language"""
        ).fetchall()
        return [r["language"] for r in rows]

    def languages(self) -> list[str]:
        rows = self.db.conn.execute(
            """SELECT DISTINCT COALESCE(a.language, s.language) AS lang
               FROM articles a JOIN sources s ON s.id = a.source_id ORDER BY lang"""
        ).fetchall()
        return [r["lang"] for r in rows if r["lang"]]


def _rate(home: HomeProfile, row: sqlite3.Row) -> tuple[str, list[str]]:
    """The country rules need the AI's findings; a report it has not read is not rated."""
    if row["countries"] is None:
        return "none", []
    countries = json.loads(row["countries"]) if row["countries"] else []
    topics = json.loads(row["topics"]) if row["topics"] else []
    # The AI's "Türkiye is mentioned" answer only helps when the user's country is Türkiye.
    mentions = bool(row["mentions_turkey"]) and home.code == "TR"
    return home.relevance(f"{row['title']}\n{row['summary']}", countries, topics, mentions)


def rate_home(c: sqlite3.Connection, article_id: int, home: HomeProfile) -> None:
    """Rate one report against the user's country, once the AI has read it."""
    row = c.execute(
        """SELECT a.title, a.summary, x.countries, x.topics, x.mentions_turkey
           FROM articles a LEFT JOIN article_ai x ON x.article_id = a.id AND x.status = 'done'
           WHERE a.id = ?""",
        (article_id,),
    ).fetchone()
    if row is not None:
        level, links = _rate(home, row)
        c.execute("UPDATE articles SET home_relevance = ?, home_links = ? WHERE id = ?",
                  (level, json.dumps(links), article_id))
