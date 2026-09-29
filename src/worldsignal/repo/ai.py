"""AI enrichment queue and result cache (table ``article_ai``).

Priority is the article's timestamp in seconds, so newer news is processed
first; an explicit user request jumps ahead of everything. A result is stored
once per article and never recomputed automatically (cache).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ..ai.enrich import EnrichResult
from ..ai.languages import missing
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
    upgrade: bool = False  # redo of a finished article (a language missing, or full text arrived)
    requested: bool = False  # the user asked for it


class AiRepository:
    def __init__(self, db: Database, home: Callable[[], HomeProfile] | None = None) -> None:
        self.db = db
        # The AI's facts (countries, topics) sharpen the report's rating against the user's country.
        self.home = home

    # -- queue ------------------------------------------------------------------
    def enqueue_recent(self, since_iso: str, covered_by_stories: int | None = None) -> int:
        """Queue every article newer than ``since_iso`` that has no AI row yet.

        ``covered_by_stories`` (``ai.depth`` "stories" / "fast"): reports of a story with at least this many
        independent sources are not read one by one; the story summary covers them (unless it failed for
        good). Automatic rows of such reports that are still waiting leave the queue."""
        now = utc_now_iso()
        covered = """EXISTS (SELECT 1 FROM story_articles sa JOIN stories st ON st.id = sa.story_id
                             WHERE sa.article_id = {id} AND st.source_count >= ? AND st.ai_status IS NOT 'failed')"""
        with self.db.transaction() as c:
            skip = f"AND NOT {covered.format(id='a.id')}" if covered_by_stories else ""
            cur = c.execute(
                f"""INSERT INTO article_ai (article_id, status, priority, queued_at)
                   SELECT a.id, 'pending', CAST(strftime('%s', a.sort_at) AS REAL), ?
                   FROM articles a JOIN sources s ON s.id = a.source_id
                   WHERE a.sort_at >= ? AND s.enabled = 1
                     AND NOT EXISTS (SELECT 1 FROM article_ai x WHERE x.article_id = a.id) {skip}""",
                (now, since_iso, *([covered_by_stories] if covered_by_stories else [])),
            )
            if covered_by_stories:
                c.execute(
                    f"""DELETE FROM article_ai WHERE status = 'pending' AND requested_by_user = 0
                        AND {covered.format(id='article_ai.article_id')}""",
                    (covered_by_stories,),
                )
            # Automatic items that fell out of the window are dropped from the queue;
            # the user can still request them one by one.
            c.execute(
                """DELETE FROM article_ai WHERE status = 'pending' AND requested_by_user = 0
                   AND article_id IN (SELECT id FROM articles WHERE sort_at < ?)""",
                (since_iso,),
            )
            return cur.rowcount

    def request(self, article_id: int, languages: Sequence[str] = ()) -> str:
        """User asked for this article. Returns the resulting status. A finished article is written again only
        when it lacks one of ``languages``."""
        now = utc_now_iso()
        with self.db.transaction() as c:
            if c.execute("SELECT 1 FROM articles WHERE id = ?", (article_id,)).fetchone() is None:
                raise KeyError(article_id)
            row = c.execute("SELECT status, texts, brief FROM article_ai WHERE article_id = ?", (article_id,)).fetchone()
            if (row is not None and row["status"] == "done" and not row["brief"]
                    and not missing(json.loads(row["texts"] or "{}"), languages)):
                return "done"  # (a brief result, headline only, is written again with its summary)
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

    def next_job(self, upgrade_since: str | None = None, languages: Sequence[str] = ("tr", "en")) -> Job | None:
        """The next queued article. When the queue is empty and ``upgrade_since`` is given, a finished
        article from that window is redone when it lacks one of ``languages`` (the user added a language)
        or its full text arrived after it was written; the old text stays visible meanwhile.
        The model reads the full text when there is one, else the feed summary."""
        jobs = self.next_jobs(1)
        if jobs:
            return jobs[0]
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
                 AND ({lacking} OR (ft.status = 'done' AND ft.fetched_at > x.completed_at))
               ORDER BY a.sort_at DESC LIMIT 1""".format(lacking=lacking_sql("x.texts", languages)),
            (MAX_ATTEMPTS + 1, upgrade_since, *languages),
        ).fetchone()
        return Job(**dict(row), upgrade=True) if row else None

    def next_jobs(self, limit: int, *, automatic_only: bool = False) -> list[Job]:
        """Queued articles, most urgent first (the user's requests before everything)."""
        rows = self.db.conn.execute(
            f"""SELECT x.article_id, x.attempts, a.title,
                      CASE WHEN ft.status = 'done' THEN ft.text ELSE a.summary END AS summary,
                      COALESCE(a.language, s.language) AS language, s.name AS source_name,
                      x.requested_by_user AS requested
               FROM article_ai x
               JOIN articles a ON a.id = x.article_id
               JOIN sources s ON s.id = a.source_id
               LEFT JOIN article_fulltext ft ON ft.article_id = a.id
               WHERE x.status = 'pending' {"AND x.requested_by_user = 0" if automatic_only else ""}
               ORDER BY x.priority DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [Job(**{**dict(r), "requested": bool(r["requested"])}) for r in rows]

    # -- results -------------------------------------------------------------------
    def store_result(self, article_id: int, result: EnrichResult, *, model: str, prompt_version: int, duration_ms: int,
                     brief: bool = False) -> None:
        """``brief``: headline, category and facts only (read in a batch); the summary follows on request."""
        with self.db.transaction() as c:
            c.execute(
                """UPDATE article_ai SET status = 'done', model = ?, prompt_version = ?, texts = ?,
                       category = ?, countries = ?, topics = ?, mentions_turkey = ?, issues = ?, brief = ?,
                       error_code = NULL, duration_ms = ?, completed_at = ?, attempts = attempts + 1
                   WHERE article_id = ?""",
                (model, prompt_version, json.dumps(result.texts, ensure_ascii=False), result.category,
                 json.dumps(result.countries), json.dumps(result.topics), int(result.mentions_turkey),
                 json.dumps(result.issues), int(brief), duration_ms, utc_now_iso(), article_id),
            )
            if self.home is not None:
                rate_home(c, article_id, self.home())
            c.execute("DELETE FROM article_ai_fts WHERE rowid = ?", (article_id,))
            c.execute(
                "INSERT INTO article_ai_fts (rowid, title_tr, summary_tr) VALUES (?, ?, ?)",
                # One index for all AI languages (the column names are historical): a search finds any of them.
                (article_id, fold_for_search(" ".join(t["title"] for t in result.texts.values())),
                 fold_for_search(" ".join(t["summary"] for t in result.texts.values()))),
            )

    def store_upgrade_failure(self, article_id: int, code: str) -> None:
        """A redo (a new language, or the full text) failed: the finished result stays as it is."""
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
        d["texts"] = json.loads(d["texts"] or "{}")
        return d


def lacking_sql(column: str, languages: Sequence[str]) -> str:
    """SQL that is true when the JSON ``column`` has no title for one of ``languages`` (one ``?`` per language)."""
    if not languages:
        return "0"
    return "(" + " OR ".join(f"json_extract({column}, '$.' || ? || '.title') IS NULL" for _ in languages) + ")"
