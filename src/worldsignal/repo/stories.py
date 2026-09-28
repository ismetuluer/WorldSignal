"""Stories: clusters of articles about the same event, their scores and story-level AI."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np

from ..db import Database, utc_now_iso
from ..flags import is_breaking, is_exclusive
from ..stories.score import Interest, Member, score_story
from ..textnorm import build_fts_query

DTYPE = np.float32


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def pick_representative(rows: Sequence[sqlite3.Row]) -> int:
    """The member that best stands for the story: closest to the story's mean vector (its most
    typical report, never an outlier), with a small bonus for a Turkish AI title and a reliable source.
    Without vectors: the most reliable member with a Turkish title, else the earliest."""
    with_vec = [r for r in rows if r["vector"] is not None]
    if not with_vec:
        return min(rows, key=lambda r: (r["title_tr"] is None, -r["reliability"], r["sort_at"]))["id"]
    matrix = np.stack([from_blob(r["vector"]) for r in with_vec])
    centroid = matrix.mean(axis=0)
    centroid /= np.linalg.norm(centroid) or 1.0
    typical = matrix @ centroid
    scores = typical + np.array([0.05 * (r["title_tr"] is not None) + 0.02 * r["reliability"] for r in with_vec])
    return with_vec[int(scores.argmax())]["id"]


def to_blob(vector: Sequence[float]) -> bytes:
    v = np.asarray(vector, dtype=DTYPE)
    n = float(np.linalg.norm(v))
    return (v / n if n else v).astype("<f4").tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype="<f4")


@dataclass
class StoryFilter:
    since: str | None = None
    source_ids: Sequence[int] = field(default_factory=tuple)
    regions: Sequence[str] = field(default_factory=tuple)
    groups: Sequence[str] = field(default_factory=tuple)
    languages: Sequence[str] = field(default_factory=tuple)
    categories: Sequence[str] = field(default_factory=tuple)
    turkey_only: bool = False
    min_sources: int = 1
    query: str | None = None
    sort: str = "score"  # score | recent
    limit: int = 50
    offset: int = 0


class StoryRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- embeddings ------------------------------------------------------------------------
    def articles_needing_embedding(self, since_iso: str, limit: int) -> list[dict[str, Any]]:
        rows = self.db.conn.execute(
            """SELECT a.id, a.title, a.summary FROM articles a JOIN sources s ON s.id = a.source_id
               WHERE a.sort_at >= ? AND s.enabled = 1
                 AND NOT EXISTS (SELECT 1 FROM article_embeddings e WHERE e.article_id = a.id)
               ORDER BY a.sort_at DESC LIMIT ?""",
            (since_iso, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def embedding_backlog(self, since_iso: str, cap: int = 10_000) -> int:
        """How many recent reports still wait to be matched into stories (counted up to ``cap``)."""
        return int(self.db.conn.execute(
            """SELECT COUNT(*) FROM (SELECT 1 FROM articles a JOIN sources s ON s.id = a.source_id
               WHERE a.sort_at >= ? AND s.enabled = 1
                 AND NOT EXISTS (SELECT 1 FROM article_embeddings e WHERE e.article_id = a.id) LIMIT ?)""",
            (since_iso, cap),
        ).fetchone()[0])

    def store_embeddings(self, items: Sequence[tuple[int, str, Sequence[float]]]) -> None:
        now = utc_now_iso()
        with self.db.transaction() as c:
            c.executemany(
                """INSERT INTO article_embeddings (article_id, model, vector, created_at) VALUES (?, ?, ?, ?)
                   ON CONFLICT(article_id) DO UPDATE SET model = excluded.model, vector = excluded.vector,
                       created_at = excluded.created_at""",
                [(aid, model, to_blob(vec), now) for aid, model, vec in items],
            )

    def embedding_model_in_use(self) -> str | None:
        row = self.db.conn.execute("SELECT model FROM article_embeddings ORDER BY rowid DESC LIMIT 1").fetchone()
        return row["model"] if row else None

    def drop_embeddings_of_other_models(self, model: str) -> int:
        """Vectors of different models are not comparable; used when the user switches model."""
        with self.db.transaction() as c:
            return c.execute("DELETE FROM article_embeddings WHERE model != ?", (model,)).rowcount

    def recent_vectors(self, since_iso: str, model: str) -> tuple[list[int], list[int | None], list[str], np.ndarray]:
        """Embedded articles since ``since_iso``: ids, story ids (None = unclustered), sort_at, matrix."""
        rows = self.db.conn.execute(
            """SELECT a.id, a.sort_at, e.vector, sa.story_id
               FROM article_embeddings e
               JOIN articles a ON a.id = e.article_id
               LEFT JOIN story_articles sa ON sa.article_id = a.id
               WHERE a.sort_at >= ? AND e.model = ?
               ORDER BY a.sort_at, a.id""",
            (since_iso, model),
        ).fetchall()
        if not rows:
            return [], [], [], np.zeros((0, 0), dtype=DTYPE)
        matrix = np.vstack([from_blob(r["vector"]) for r in rows])
        return [r["id"] for r in rows], [r["story_id"] for r in rows], [r["sort_at"] for r in rows], matrix

    # -- assignment ----------------------------------------------------------------------------
    def create_story(self, c: sqlite3.Connection, first_article_id: int) -> int:
        row = c.execute("SELECT sort_at FROM articles WHERE id = ?", (first_article_id,)).fetchone()
        now = utc_now_iso()
        cur = c.execute(
            """INSERT INTO stories (first_seen_at, last_seen_at, representative_id, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?)""",
            (row["sort_at"], row["sort_at"], first_article_id, now, now),
        )
        return int(cur.lastrowid)

    def assign(self, article_id: int, story_id: int | None, *, similarity: float | None, by: str = "auto") -> int:
        """Put an article into a story (a new one when ``story_id`` is None). Returns the story id."""
        with self.db.transaction() as c:
            if story_id is None:
                story_id = self.create_story(c, article_id)
            c.execute(
                """INSERT INTO story_articles (article_id, story_id, similarity, assigned_by, assigned_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(article_id) DO UPDATE SET story_id = excluded.story_id, similarity = excluded.similarity,
                       assigned_by = excluded.assigned_by, assigned_at = excluded.assigned_at""",
                (article_id, story_id, similarity, by, utc_now_iso()),
            )
        return story_id

    def detach(self, article_id: int) -> int:
        """User: this article is not part of its story. It gets its own story and stays there."""
        with self.db.transaction() as c:
            row = c.execute("SELECT story_id FROM story_articles WHERE article_id = ?", (article_id,)).fetchone()
            if row is None:
                raise KeyError(article_id)
            old = row["story_id"]
            new = self.create_story(c, article_id)
            c.execute(
                "UPDATE story_articles SET story_id = ?, assigned_by = 'user', similarity = NULL, assigned_at = ? WHERE article_id = ?",
                (new, utc_now_iso(), article_id),
            )
            self._delete_if_empty(c, old)
        return new

    def merge(self, source_id: int, target_id: int) -> int:
        """User: these two stories are the same event. Members move to ``target_id`` (locked)."""
        if source_id == target_id:
            return target_id
        with self.db.transaction() as c:
            for sid in (source_id, target_id):
                if c.execute("SELECT 1 FROM stories WHERE id = ?", (sid,)).fetchone() is None:
                    raise KeyError(sid)
            c.execute(
                "UPDATE story_articles SET story_id = ?, assigned_by = 'user', assigned_at = ? WHERE story_id = ?",
                (target_id, utc_now_iso(), source_id),
            )
            from .notebook import reassign_story  # notebook depends on stories, not the other way round

            reassign_story(c, source_id, target_id)
            c.execute("DELETE FROM stories WHERE id = ?", (source_id,))
            # The summary no longer covers the merged content.
            c.execute("UPDATE stories SET ai_status = NULL WHERE id = ? AND ai_status = 'done'", (target_id,))
        return target_id

    def _delete_if_empty(self, c: sqlite3.Connection, story_id: int) -> None:
        if c.execute("SELECT 1 FROM story_articles WHERE story_id = ? LIMIT 1", (story_id,)).fetchone() is None:
            c.execute("DELETE FROM stories WHERE id = ?", (story_id,))

    # -- recompute & score ----------------------------------------------------------------------
    def _members(self, story_id: int) -> list[sqlite3.Row]:
        return self.db.conn.execute(
            """SELECT a.id, a.sort_at, a.title, s.id AS source_id, s.region, s.reliability,
                      COALESCE(NULLIF(s.owner, ''), s.slug) AS owner_key,
                      x.title_tr, x.category, a.home_relevance AS turkey_relevance, e.vector
               FROM story_articles sa
               JOIN articles a ON a.id = sa.article_id
               JOIN sources s ON s.id = a.source_id
               LEFT JOIN article_ai x ON x.article_id = a.id AND x.status = 'done'
               LEFT JOIN article_embeddings e ON e.article_id = a.id
               WHERE sa.story_id = ? AND s.enabled = 1
               ORDER BY a.sort_at""",
            (story_id,),
        ).fetchall()

    def recompute(self, story_ids: Sequence[int], now: datetime, weights: dict[str, float], interest: Interest) -> None:
        with self.db.transaction() as c:
            for sid in set(story_ids):
                rows = self._members(sid)
                if not rows:
                    # Every member's source is disabled (or members were removed).
                    if c.execute("SELECT 1 FROM story_articles WHERE story_id = ? LIMIT 1", (sid,)).fetchone() is None:
                        c.execute("DELETE FROM stories WHERE id = ?", (sid,))
                    else:
                        c.execute("UPDATE stories SET score = 0, article_count = 0, source_count = 0 WHERE id = ?", (sid,))
                    continue
                members = [
                    Member(r["id"], r["owner_key"], r["reliability"], parse_iso(r["sort_at"]), r["region"],
                           f"{r['title']} {r['title_tr'] or ''}", r["category"], r["turkey_relevance"])
                    for r in rows
                ]
                categories = Counter(r["category"] for r in rows if r["category"])
                category = categories.most_common(1)[0][0] if categories else None
                result = score_story(members, now, weights=weights, interest=interest, category=category)
                representative = pick_representative(rows)
                c.execute(
                    """UPDATE stories SET first_seen_at = ?, last_seen_at = ?, article_count = ?, source_count = ?,
                           score = ?, score_parts = ?, turkey_relevance = ?, category = ?, representative_id = ?,
                           updated_at = ?
                       WHERE id = ?""",
                    (rows[0]["sort_at"], rows[-1]["sort_at"], len(rows), result.source_count, result.score,
                     json.dumps(result.parts(), ensure_ascii=False), result.turkey_relevance, category,
                     representative, utc_now_iso(), sid),
                )

    def active_story_ids(self, since_iso: str) -> list[int]:
        return [r[0] for r in self.db.conn.execute("SELECT id FROM stories WHERE last_seen_at >= ?", (since_iso,))]

    # -- story AI queue -----------------------------------------------------------------------------
    def next_story_job(
        self, since_iso: str, min_sources: int, max_attempts: int = 3, *, automatic: bool = True
    ) -> dict[str, Any] | None:
        """The highest-scoring story that needs a (new) summary.

        A story needs one when it has at least ``min_sources`` independent sources and either
        has no summary yet, has grown by half (and at least two articles) since it was written, or its
        summary predates the English text.
        Stories the user asked for (ai_status = 'pending') come first, whatever their size.
        ``automatic=False``: only those.
        """
        if not automatic:
            row = self.db.conn.execute(
                "SELECT id FROM stories WHERE ai_status = 'pending' AND ai_attempts < ? ORDER BY score DESC LIMIT 1",
                (max_attempts,),
            ).fetchone()
            return self.get(row["id"], member_limit=12) if row else None
        row = self.db.conn.execute(
            """SELECT id FROM stories
               WHERE ai_attempts < ?
                 AND (ai_status = 'pending'
                      OR (last_seen_at >= ? AND source_count >= ?
                          AND (ai_status IS NULL
                               OR (ai_status = 'done' AND ai_title_en IS NULL)  -- written before English existed
                               OR (ai_status = 'done' AND article_count >= ai_article_count * 1.5
                                   AND article_count >= ai_article_count + 2))))
               ORDER BY ai_status = 'pending' DESC, score DESC LIMIT 1""",
            (max_attempts, since_iso, min_sources),
        ).fetchone()
        return self.get(row["id"], member_limit=12) if row else None

    def request_summary(self, story_id: int) -> None:
        with self.db.transaction() as c:
            if c.execute("UPDATE stories SET ai_status = 'pending', ai_attempts = 0 WHERE id = ?", (story_id,)).rowcount == 0:
                raise KeyError(story_id)

    def store_story_ai(self, story_id: int, *, title: str, summary: str, why: str, category: str | None,
                       issues: list[str], model: str, article_count: int,
                       title_en: str | None = None, summary_en: str | None = None, why_en: str | None = None) -> None:
        with self.db.transaction() as c:
            c.execute(
                """UPDATE stories SET ai_status = 'done', ai_title_tr = ?, ai_summary_tr = ?, ai_why = ?,
                       ai_title_en = ?, ai_summary_en = ?, ai_why_en = ?,
                       category = COALESCE(?, category), ai_issues = ?, ai_article_count = ?, ai_model = ?,
                       ai_error = NULL, ai_attempts = 0, ai_completed_at = ?
                   WHERE id = ?""",
                (title, summary, why, title_en, summary_en, why_en, category, json.dumps(issues), article_count, model,
                 utc_now_iso(), story_id),
            )

    def store_story_ai_failure(self, story_id: int, code: str, max_attempts: int = 3) -> None:
        with self.db.transaction() as c:
            c.execute(
                """UPDATE stories SET ai_attempts = ai_attempts + 1, ai_error = ?,
                       ai_status = CASE WHEN ai_attempts + 1 >= ? AND ai_status IS NOT 'done' THEN 'failed' ELSE ai_status END
                   WHERE id = ?""",
                (code, max_attempts, story_id),
            )

    # -- queries ----------------------------------------------------------------------------------------
    def list(self, f: StoryFilter) -> tuple[list[dict[str, Any]], int]:
        where = ["st.article_count > 0", "st.source_count >= ?"]
        params: list[Any] = [f.min_sources]
        if f.since:
            where.append("st.last_seen_at >= ?")
            params.append(f.since)
        if f.turkey_only:
            where.append("st.turkey_relevance IN ('direct', 'indirect')")
        if f.categories:
            where.append(f"st.category IN ({','.join('?' * len(f.categories))})")
            params.extend(f.categories)
        member_conds = []
        member_params: list[Any] = []
        for column, values in (("a.source_id", f.source_ids), ("s.region", f.regions), ("s.catalog_group", f.groups),
                               ("COALESCE(a.language, s.language)", f.languages)):
            if values:
                member_conds.append(f"{column} IN ({','.join('?' * len(values))})")
                member_params.extend(values)
        if f.query:
            fts = build_fts_query(f.query)
            if fts is None:
                return [], 0
            member_conds.append(
                "(a.id IN (SELECT rowid FROM articles_fts WHERE articles_fts MATCH ?)"
                " OR a.id IN (SELECT rowid FROM article_ai_fts WHERE article_ai_fts MATCH ?))"
            )
            member_params.extend([fts, fts])
        if member_conds:
            where.append(
                f"""EXISTS (SELECT 1 FROM story_articles sa JOIN articles a ON a.id = sa.article_id
                    JOIN sources s ON s.id = a.source_id WHERE sa.story_id = st.id AND {' AND '.join(member_conds)})"""
            )
            params.extend(member_params)
        where_sql = " AND ".join(where)
        total = int(self.db.conn.execute(f"SELECT COUNT(*) FROM stories st WHERE {where_sql}", params).fetchone()[0])
        order = "st.score DESC, st.last_seen_at DESC" if f.sort == "score" else "st.last_seen_at DESC"
        rows = self.db.conn.execute(
            f"SELECT st.id FROM stories st WHERE {where_sql} ORDER BY {order} LIMIT ? OFFSET ?",
            [*params, max(1, min(f.limit, 200)), max(0, f.offset)],
        ).fetchall()
        return [self.get(r["id"], member_limit=6) for r in rows], total  # type: ignore[misc]

    def get(self, story_id: int, member_limit: int | None = None) -> dict[str, Any] | None:
        row = self.db.conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        if row is None:
            return None
        story = dict(row)
        story["score_parts"] = json.loads(story["score_parts"] or "{}")
        story["ai_issues"] = json.loads(story["ai_issues"] or "[]")
        members = self.db.conn.execute(
            """SELECT a.id, a.url, a.title, a.summary, a.sort_at, COALESCE(a.language, s.language) AS language,
                      s.id AS source_id, s.name AS source_name, s.paywalled, s.region,
                      COALESCE(NULLIF(s.owner, ''), s.slug) AS owner_key,
                      sa.similarity, sa.assigned_by,
                      CASE WHEN x.status = 'done' THEN x.title_tr END AS title_tr,
                      CASE WHEN x.status = 'done' THEN x.summary_tr END AS summary_tr,
                      CASE WHEN x.status = 'done' THEN x.title_en END AS title_en,
                      CASE WHEN x.status = 'done' THEN x.summary_en END AS summary_en,
                      ft.status AS fulltext_status, ft.error_code AS fulltext_error, ft.chars AS fulltext_chars,
                      ft.translate_status AS fulltext_translate_status
               FROM story_articles sa
               JOIN articles a ON a.id = sa.article_id
               JOIN sources s ON s.id = a.source_id
               LEFT JOIN article_ai x ON x.article_id = a.id
               LEFT JOIN article_fulltext ft ON ft.article_id = a.id
               WHERE sa.story_id = ? AND s.enabled = 1
               ORDER BY a.sort_at DESC""",
            (story_id,),
        ).fetchall()
        items = [dict(m) for m in members]
        for m in items:
            m["paywalled"] = bool(m["paywalled"])
            m["exclusive"] = is_exclusive(m["title"])
        story["exclusive"] = any(m["exclusive"] for m in items)
        story["breaking"] = is_breaking(((m["owner_key"], parse_iso(m["sort_at"]), m["title"]) for m in items),
                                        datetime.now(UTC))
        for m in items:
            del m["owner_key"]
        story["sources"] = sorted({m["source_name"] for m in items})
        story["members"] = items if member_limit is None else items[:member_limit]
        rep = next((m for m in items if m["id"] == story["representative_id"]), items[-1] if items else None)
        story["representative"] = rep
        # Timeline: articles per day.
        per_day = Counter(m["sort_at"][:10] for m in items)
        story["timeline"] = [{"day": d, "articles": n} for d, n in sorted(per_day.items())]
        return story

    def story_of(self, article_id: int) -> int | None:
        row = self.db.conn.execute("SELECT story_id FROM story_articles WHERE article_id = ?", (article_id,)).fetchone()
        return row["story_id"] if row else None

    def counts(self) -> dict[str, int]:
        row = self.db.conn.execute(
            """SELECT (SELECT COUNT(*) FROM article_embeddings) AS embedded,
                      (SELECT COUNT(*) FROM story_articles) AS clustered,
                      (SELECT COUNT(*) FROM stories) AS stories,
                      (SELECT COUNT(*) FROM stories WHERE source_count >= 2) AS multi_source"""
        ).fetchone()
        return {k: int(row[k] or 0) for k in row.keys()}
