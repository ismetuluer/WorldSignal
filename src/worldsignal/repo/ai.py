"""AI enrichment queue and result cache (table ``article_ai``).

Priority is the article's timestamp in seconds, so newer news is processed
first; an explicit user request jumps ahead of everything. A result is stored
once per article and never recomputed automatically (cache).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ..ai.enrich import EnrichResult
from ..country import HomeProfile
from ..db import Database, utc_now_iso
from ..textnorm import fold_for_search
from .articles import rate_home

USER_REQUEST_BOOST = 1e11  # far above any timestamp priority
MAX_ATTEMPTS = 3
RETRY_PENALTY_SECONDS = 3600  # a failed item waits behind an hour's worth of news


@dataclass
class Job:
    article_id: int
    attempts: int
    title: str
    summary: str
    language: str
    source_name: str
    upgrade: bool = False  # redo of a finished article (English missing, or full text arrived)


class AiRepository:
    def __init__(self, db: Database, home: Callable[[], HomeProfile] | None = None) -> None:
        self.db = db
        # The AI's facts (countries, topics) sharpen the report's rating against the user's country.
        self.home = home

    # -- queue ------------------------------------------------------------------
    def enqueue_recent(self, since_iso: str) -> int:
        """Queue every article newer than ``since_iso`` that has no AI row yet."""
        now = utc_now_iso()
        with self.db.transaction() as c:
            cur = c.execute(
                """INSERT INTO article_ai (article_id, status, priority, queued_at)
                   SELECT a.id, 'pending', CAST(strftime('%s', a.sort_at) AS REAL), ?
                   FROM articles a JOIN sources s ON s.id = a.source_id
                   WHERE a.sort_at >= ? AND s.enabled = 1
                     AND NOT EXISTS (SELECT 1 FROM article_ai x WHERE x.article_id = a.id)""",
                (now, since_iso),
            )
            # Automatic items that fell out of the window are dropped from the queue;
            # the user can still request them one by one.
            c.execute(
                """DELETE FROM article_ai WHERE status = 'pending' AND requested_by_user = 0
                   AND article_id IN (SELECT id FROM articles WHERE sort_at < ?)""",
                (since_iso,),
            )
            return cur.rowcount

    def request(self, article_id: int) -> str:
        """User asked for this article. Returns the resulting status."""
        now = utc_now_iso()
        with self.db.transaction() as c:
            if c.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,)).fetchone() is None:
                raise KeyError(article_id)
            row = c.execute("SELECT status FROM article_ai WHERE article_id = ?", (article_id,)).fetchone()
            if row is not None and row["status"] == "done":
                return "done"
            priority = USER_REQUEST_BOOST + datetime.now(UTC).timestamp()
            c.execute(
                """INSERT INTO article_ai (article_id, status, priority, requested_by_user, queued_at)
                   VALUES (?, 'pending', ?, 1, ?)
                   ON CONFLICT(article_id) DO UPDATE SET status = 'pending', priority = excluded.priority,
                       requested_by_user = 1, attempts = 0, error_code = NULL""",
                (article_id, priority, now),
            )
            return "pending"

    def retry_failed(self) -> int:
        with self.db.transaction() as c:
            return c.execute(
                "UPDATE article_ai SET status = 'pending', attempts = 0, error_code = NULL WHERE status = 'failed'"
            ).rowcount

    def next_job(self, upgrade_since: str | None = None) -> Job | None:
        """The next queued article. When the queue is empty and ``upgrade_since`` is given, a finished
        article from that window is redone when it still lacks the English text (written before
        prompt v5) or its full text arrived after it was written; the old text stays visible
        meanwhile. The model reads the full text when there is one, else the feed summary."""
        row = self.db.conn.execute(
            """SELECT x.article_id, x.attempts, a.title,
                      CASE WHEN ft.status = 'done' THEN ft.text ELSE a.summary END AS summary,
                      COALESCE(a.language, s.language) AS language, s.name AS source_name
               FROM article_ai x
               JOIN articles a ON a.id = x.article_id
               JOIN sources s ON s.id = a.source_id
               LEFT JOIN article_fulltext ft ON ft.article_id = a.id
               WHERE x.status = 'pending'
               ORDER BY x.priority DESC LIMIT 1"""
        ).fetchone()
        if row is not None:
            return Job(**dict(row))
        if upgrade_since is None:
            return None
        row = self.db.conn.execute(
            """SELECT x.article_id, x.attempts, a.title,
                      CASE WHEN ft.status = 'done' THEN ft.text ELSE a.summary END AS summary,
                      COALESCE(a.language, s.language) AS language, s.name AS source_name
               FROM article_ai x
               JOIN articles a ON a.id = x.article_id
               JOIN sources s ON s.id = a.source_id
               LEFT JOIN article_fulltext ft ON ft.article_id = a.id
               WHERE x.status = 'done' AND x.attempts < ? AND a.sort_at >= ? AND s.enabled = 1
                 AND (x.title_en IS NULL OR (ft.status = 'done' AND ft.fetched_at > x.completed_at))
               ORDER BY a.sort_at DESC LIMIT 1""",
            (MAX_ATTEMPTS + 1, upgrade_since),
        ).fetchone()
        return Job(**dict(row), upgrade=True) if row else None

    # -- results -------------------------------------------------------------------
    def store_result(self, article_id: int, result: EnrichResult, *, model: str, prompt_version: int, duration_ms: int) -> None:
        with self.db.transaction() as c:
            c.execute(
                """UPDATE article_ai SET status = 'done', model = ?, prompt_version = ?, title_tr = ?, summary_tr = ?,
                       title_en = ?, summary_en = ?, category = ?, countries = ?, topics = ?, mentions_turkey = ?, issues = ?,
                       error_code = NULL, duration_ms = ?, completed_at = ?, attempts = attempts + 1
                   WHERE article_id = ?""",
                (model, prompt_version, result.title_tr, result.summary_tr, result.title_en, result.summary_en,
                 result.category,
                 json.dumps(result.countries), json.dumps(result.topics), int(result.mentions_turkey),
                 json.dumps(result.issues), duration_ms, utc_now_iso(), article_id),
            )
            if self.home is not None:
                rate_home(c, article_id, self.home())
            c.execute("DELETE FROM article_ai_fts WHERE rowid = ?", (article_id,))
            c.execute(
                "INSERT INTO article_ai_fts (rowid, title_tr, summary_tr) VALUES (?, ?, ?)",
                # One index for both AI languages: a search finds the Turkish and the English text.
                (article_id, fold_for_search(f"{result.title_tr} {result.title_en}"),
                 fold_for_search(f"{result.summary_tr} {result.summary_en}")),
            )

    def store_upgrade_failure(self, article_id: int, code: str) -> None:
        """A redo for the English text failed: the finished Turkish result stays as it is."""
        with self.db.transaction() as c:
            c.execute("UPDATE article_ai SET attempts = attempts + 1, error_code = ? WHERE article_id = ?", (code, article_id))

    def store_failure(self, article_id: int, code: str) -> str:
        """Record a failed attempt. Returns the new status ('pending' or 'failed')."""
        with self.db.transaction() as c:
            row = c.execute("SELECT attempts FROM article_ai WHERE article_id = ?", (article_id,)).fetchone()
            if row is None:
                return "failed"
            attempts = row["attempts"] + 1
            status = "failed" if attempts >= MAX_ATTEMPTS else "pending"
            c.execute(
                """UPDATE article_ai SET attempts = ?, status = ?, error_code = ?,
                       priority = priority - ?, completed_at = CASE WHEN ? = 'failed' THEN ? ELSE completed_at END
                   WHERE article_id = ?""",
                (attempts, status, code, RETRY_PENALTY_SECONDS * attempts, status, utc_now_iso(), article_id),
            )
            return status

    def counts(self) -> dict[str, int]:
        since = utc_now_iso(datetime.now(UTC) - timedelta(hours=24))
        row = self.db.conn.execute(
            """SELECT SUM(status = 'pending') AS pending, SUM(status = 'done') AS done,
                      SUM(status = 'failed') AS failed, SUM(status = 'done' AND completed_at >= ?) AS done_24h
               FROM article_ai""",
            (since,),
        ).fetchone()
        return {k: int(row[k] or 0) for k in ("pending", "done", "failed", "done_24h")}

    def get(self, article_id: int) -> dict[str, Any] | None:
        row = self.db.conn.execute("SELECT * FROM article_ai WHERE article_id = ?", (article_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        for key in ("issues", "countries", "turkey_links"):
            d[key] = json.loads(d[key] or "[]")
        return d
