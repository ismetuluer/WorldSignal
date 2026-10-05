"""Stories: clusters of articles about the same event, their scores and story-level AI."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from ..db import Database, utc_now_iso
from ..flags import group_condition, is_breaking, is_exclusive
from ..stories.score import Interest, Member, score_story
from ..textnorm import build_fts_query
from .ai import lacking_sql
from .sources import region_condition

DTYPE = np.float32  # computing
STORED = "f2"  # how new vectors are stored (migration 0010): 16-bit floats; older rows say "f4"


def parse_iso(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def pick_representative(rows: Sequence[sqlite3.Row]) -> int:
    """The member that best stands for the story: closest to the story's mean vector (its most
    typical report, never an outlier), with a small bonus for an AI title and a reliable source.
    Without vectors: the most reliable member with an AI title, else the earliest."""
    with_vec = [r for r in rows if r["vector"] is not None]
    if not with_vec:
        return min(rows, key=lambda r: (not r["ai_titles"], -r["reliability"], r["sort_at"]))["id"]
    matrix = np.stack([from_blob(r["vector"], r["dtype"] if "dtype" in r.keys() else STORED) for r in with_vec])
    centroid = matrix.mean(axis=0)
    centroid /= np.linalg.norm(centroid) or 1.0
    typical = matrix @ centroid
    scores = typical + np.array([0.05 * bool(r["ai_titles"]) + 0.02 * r["reliability"] for r in with_vec])
    return with_vec[int(scores.argmax())]["id"]


@dataclass
class StoryFacts:
    """What a story summary found for "my country", and the rating country.py gave it."""

    countries: list[str]
    topics: list[str]
    mentions_home: bool
    level: str
    links: list[str]


def story_text(texts: dict[str, dict[str, str]]) -> str:
    """The story's AI texts in all languages: the names of the home country are also looked for in them."""
    return "\n".join(f"{t.get('title', '')}\n{t.get('summary', '')}" for t in texts.values())


def to_blob(vector: Sequence[float]) -> bytes:
    """Unit length, stored as ``STORED``."""
    v = np.asarray(vector, dtype=DTYPE)
    n = float(np.linalg.norm(v))
    return (v / n if n else v).astype(f"<{STORED}").tobytes()


def from_blob(blob: bytes, dtype: str = STORED) -> np.ndarray:
    return np.frombuffer(blob, dtype=f"<{dtype}").astype(DTYPE)


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
    alternatives: Sequence[str] = field(default_factory=tuple)  # translations of the query (ai/query.py)
    breaking: bool = False  # a report of the window (``since``, else 24 h) carries the publisher's breaking-news label
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
                """INSERT INTO article_embeddings (article_id, model, vector, dtype, created_at) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(article_id) DO UPDATE SET model = excluded.model, vector = excluded.vector,
                       dtype = excluded.dtype, created_at = excluded.created_at""",
                [(aid, model, to_blob(vec), STORED, now) for aid, model, vec in items],
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
            """SELECT a.id, a.sort_at, e.vector, e.dtype, sa.story_id
               FROM article_embeddings e
               JOIN articles a ON a.id = e.article_id
               LEFT JOIN story_articles sa ON sa.article_id = a.id
               WHERE a.sort_at >= ? AND e.model = ?
               ORDER BY a.sort_at, a.id""",
            (since_iso, model),
        ).fetchall()
        if not rows:
            return [], [], [], np.zeros((0, 0), dtype=DTYPE)
        matrix = np.vstack([from_blob(r["vector"], r["dtype"]) for r in rows])
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

    def split_loose(self, since_iso: str, model: str, threshold: float, *, dry_run: bool = False) -> tuple[set[int], int]:
        """Hold the stories of the window to ``threshold``: a story whose members no longer hang together at that
        similarity (they joined under a lower threshold) is split into the groups that do. The largest group keeps
        the story (and its notes, meeting entries, summary); the others become stories of their own. A story the
        user has corrected by hand is left alone. Returns (touched story ids, stories created); with ``dry_run``
        nothing is changed and the ids are those that would be touched."""
        ids, story_ids, _, matrix = self.recent_vectors(since_iso, model)
        if not ids:
            return set(), 0
        by_story: dict[int, list[int]] = {}
        for pos, sid in enumerate(story_ids):
            if sid is not None:
                by_story.setdefault(sid, []).append(pos)
        pinned = {r["article_id"] for r in self.db.conn.execute(
            "SELECT article_id FROM story_articles WHERE assigned_by = 'user'")}
        touched: set[int] = set()
        created = 0
        for sid, rows in by_story.items():
            if len(rows) < 2:
                continue
            sims = matrix[rows] @ matrix[rows].T
            parent = list(range(len(rows)))

            def find(x: int) -> int:
                while parent[x] != x:
                    parent[x] = parent[parent[x]]
                    x = parent[x]
                return x

            for i, j in zip(*np.nonzero(np.triu(sims >= threshold, k=1)), strict=True):
                parent[find(int(i))] = find(int(j))
            if any(ids[pos] in pinned for pos in rows):
                continue  # the user has already corrected this story; their say stands
            groups: dict[int, list[int]] = {}
            for k in range(len(rows)):
                groups.setdefault(find(k), []).append(k)
            if len(groups) < 2:
                continue
            main = max(groups.values(), key=lambda g: (len(g), -min(g)))
            created += len(groups) - 1
            touched.add(sid)
            if dry_run:
                continue
            with self.db.transaction() as c:
                for group in groups.values():
                    if group is main:
                        continue
                    first = ids[rows[group[0]]]
                    new = self.create_story(c, first)
                    for k in group:
                        c.execute(
                            "UPDATE story_articles SET story_id = ?, similarity = NULL, assigned_by = 'auto', assigned_at = ? "
                            "WHERE article_id = ?", (new, utc_now_iso(), ids[rows[k]]))
                    touched.add(new)
                # The kept story's summary no longer covers what was taken out of it.
                c.execute("UPDATE stories SET ai_status = NULL WHERE id = ? AND ai_status = 'done'", (sid,))
        return touched, created

    def _delete_if_empty(self, c: sqlite3.Connection, story_id: int) -> None:
        if c.execute("SELECT 1 FROM story_articles WHERE story_id = ? LIMIT 1", (story_id,)).fetchone() is None:
            c.execute("DELETE FROM stories WHERE id = ?", (story_id,))

    # -- recompute & score ----------------------------------------------------------------------
    def _members(self, story_id: int) -> list[sqlite3.Row]:
        return self.db.conn.execute(
            """SELECT a.id, a.sort_at, a.title, s.id AS source_id, s.region, s.reliability,
                      COALESCE(NULLIF(s.owner, ''), s.slug) AS owner_key,
                      (SELECT group_concat(json_extract(j.value, '$.title'), ' ') FROM json_each(x.texts) j) AS ai_titles,
                      x.category, a.home_relevance AS turkey_relevance, e.vector, e.dtype
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
                           f"{r['title']} {r['ai_titles'] or ''}", r["category"], r["turkey_relevance"])
                    for r in rows
                ]
                categories = Counter(r["category"] for r in rows if r["category"])
                category = categories.most_common(1)[0][0] if categories else None
                own = c.execute("SELECT ai_home_relevance FROM stories WHERE id = ?", (sid,)).fetchone()
                result = score_story(members, now, weights=weights, interest=interest, category=category,
                                     story_relevance=own["ai_home_relevance"] if own else None)
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
        self, since_iso: str, min_sources: int, max_attempts: int = 3, *, automatic: bool = True,
        languages: Sequence[str] = ("tr", "en"), need_facts: bool = False, meeting_day: str | None = None,
    ) -> dict[str, Any] | None:
        """The highest-scoring story that needs a (new) summary.

        A story needs one when it has at least ``min_sources`` independent sources and either
        has no summary yet, has grown by half (and at least two articles) since it was written, or its
        summary lacks one of ``languages`` (the user added a language), or — ``need_facts``: its reports are not
        read one by one ("stories" / "fast") — it was written before summaries extracted the facts for "my country".
        Stories the user asked for (ai_status = 'pending') come first, whatever their size; then the stories on
        the meeting list of ``meeting_day`` that have no summary or one written before it had key points (the
        user chose them, so they count as asked for too). ``automatic=False``: only those.
        """
        row = self.db.conn.execute(
            "SELECT id FROM stories WHERE ai_status = 'pending' AND ai_attempts < ? ORDER BY score DESC LIMIT 1",
            (max_attempts,),
        ).fetchone()
        if row is None and meeting_day is not None:
            row = self.db.conn.execute(
                """SELECT s.id FROM meeting_items m JOIN stories s ON s.id = m.story_id
                   WHERE m.day = ? AND s.ai_attempts < ?
                     AND (s.ai_status IS NULL OR (s.ai_status = 'done' AND NOT EXISTS (
                          SELECT 1 FROM json_each(s.ai_texts) j WHERE json_type(j.value, '$.points') = 'text')))
                   ORDER BY m.position LIMIT 1""",
                (meeting_day, max_attempts),
            ).fetchone()
        if not automatic or row is not None:
            return self.get(row["id"], member_limit=12) if row else None
        row = self.db.conn.execute(
            """SELECT id FROM stories
               WHERE ai_attempts < ?
                 AND (ai_status = 'pending'
                      OR (last_seen_at >= ? AND source_count >= ?
                          AND (ai_status IS NULL
                               OR (ai_status = 'done' AND {lacking})
                               OR (ai_status = 'done' AND ? AND ai_countries IS NULL)
                               OR (ai_status = 'done' AND article_count >= ai_article_count * 1.5
                                   AND article_count >= ai_article_count + 2))))
               ORDER BY ai_status = 'pending' DESC, score DESC LIMIT 1""".format(
                lacking=lacking_sql("ai_texts", languages)),
            (max_attempts, since_iso, min_sources, *languages, int(need_facts)),
        ).fetchone()
        return self.get(row["id"], member_limit=12) if row else None

    def request_summary(self, story_id: int) -> None:
        with self.db.transaction() as c:
            if c.execute("UPDATE stories SET ai_status = 'pending', ai_attempts = 0 WHERE id = ?", (story_id,)).rowcount == 0:
                raise KeyError(story_id)

    def store_story_ai(self, story_id: int, *, texts: dict[str, dict[str, str]], category: str | None,
                       issues: list[str], model: str, article_count: int, facts: StoryFacts | None = None) -> None:
        """``texts``: {"tr": {"title": …, "summary": …, "why": …}, …}; ``facts``: for "my country" (rated)."""
        with self.db.transaction() as c:
            c.execute(
                """UPDATE stories SET ai_status = 'done', ai_texts = ?,
                       category = COALESCE(?, category), ai_issues = ?, ai_article_count = ?, ai_model = ?,
                       ai_error = NULL, ai_attempts = 0, ai_completed_at = ?
                   WHERE id = ?""",
                (json.dumps(texts, ensure_ascii=False), category, json.dumps(issues), article_count, model,
                 utc_now_iso(), story_id),
            )
            if facts is not None:
                c.execute(
                    """UPDATE stories SET ai_countries = ?, ai_topics = ?, ai_mentions_home = ?,
                           ai_home_relevance = ?, ai_home_links = ? WHERE id = ?""",
                    (json.dumps(facts.countries), json.dumps(facts.topics), int(facts.mentions_home), facts.level,
                     json.dumps(facts.links), story_id),
                )

    def recompute_home(self, rate: Callable[[str, list[str], list[str], bool], tuple[str, list[str]]]) -> list[int]:
        """Rate the AI facts of every summarised story again (the user changed their country). ``rate`` is
        ``HomeProfile.relevance``. Returns the stories whose rating changed."""
        changed = []
        rows = self.db.conn.execute(
            """SELECT id, ai_texts, ai_countries, ai_topics, ai_mentions_home, ai_home_relevance, ai_home_links
               FROM stories WHERE ai_status = 'done' AND ai_countries IS NOT NULL"""
        ).fetchall()
        updates = []
        for r in rows:
            level, links = rate(story_text(json.loads(r["ai_texts"] or "{}")), json.loads(r["ai_countries"]),
                                json.loads(r["ai_topics"] or "[]"), bool(r["ai_mentions_home"]))
            if level != r["ai_home_relevance"] or json.dumps(links) != r["ai_home_links"]:
                updates.append((level, json.dumps(links), r["id"]))
                changed.append(r["id"])
        if updates:
            with self.db.transaction() as c:
                c.executemany("UPDATE stories SET ai_home_relevance = ?, ai_home_links = ? WHERE id = ?", updates)
        return changed

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
        if f.breaking:
            where.append(
                """EXISTS (SELECT 1 FROM story_articles sb JOIN articles ab ON ab.id = sb.article_id
                          WHERE sb.story_id = st.id AND ab.sort_at >= ? AND ws_breaking(ab.title))"""
            )
            params.append(f.since or utc_now_iso(datetime.now(UTC) - timedelta(hours=24)))
        if f.categories:
            where.append(f"st.category IN ({','.join('?' * len(f.categories))})")
            params.extend(f.categories)
        member_conds = []
        member_params: list[Any] = []
        for column, values in (("a.source_id", f.source_ids),
                               ("COALESCE(a.language, s.language)", f.languages)):
            if values:
                member_conds.append(f"{column} IN ({','.join('?' * len(values))})")
                member_params.extend(values)
        if groups := group_condition(f.groups):
            member_conds.append(groups[0])
            member_params.extend(groups[1])
        if regions := region_condition(f.regions):
            member_conds.append(regions[0])
            member_params.extend(regions[1])
        if f.query:
            fts = build_fts_query(f.query, f.alternatives)
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

    def breaking_count(self, since_iso: str) -> int:
        """Stories with a report labelled as breaking news since ``since_iso`` (the sidebar's badge)."""
        return int(self.db.conn.execute(
            """SELECT COUNT(DISTINCT sb.story_id) FROM story_articles sb JOIN articles ab ON ab.id = sb.article_id
               WHERE ab.sort_at >= ? AND ws_breaking(ab.title)""", (since_iso,)).fetchone()[0])

    def get(self, story_id: int, member_limit: int | None = None) -> dict[str, Any] | None:
        row = self.db.conn.execute("SELECT * FROM stories WHERE id = ?", (story_id,)).fetchone()
        if row is None:
            return None
        story = dict(row)
        story["score_parts"] = json.loads(story["score_parts"] or "{}")
        story["ai_issues"] = json.loads(story["ai_issues"] or "[]")
        story["ai_texts"] = json.loads(story["ai_texts"] or "{}") if story["ai_status"] == "done" else {}
        for old in ("ai_title_tr", "ai_summary_tr", "ai_why", "ai_title_en", "ai_summary_en", "ai_why_en"):
            story.pop(old, None)  # before 0.11: replaced by ai_texts
        members = self.db.conn.execute(
            """SELECT a.id, a.url, a.title, a.summary, a.sort_at, COALESCE(a.language, s.language) AS language,
                      s.id AS source_id, s.name AS source_name, s.paywalled, s.region, a.page_exclusive,
                      COALESCE(NULLIF(s.owner, ''), s.slug) AS owner_key,
                      sa.similarity, sa.assigned_by,
                      CASE WHEN x.status = 'done' THEN x.texts END AS ai_texts,
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
            m["ai_texts"] = json.loads(m["ai_texts"] or "{}")
            m["exclusive"] = bool(m.pop("page_exclusive")) or is_exclusive(m["title"], m["summary"])
        story["exclusive"] = any(m["exclusive"] for m in items)
        story["breaking"] = is_breaking(((m["owner_key"], parse_iso(m["sort_at"]), m["title"]) for m in items),
                                        datetime.now(UTC))
        for m in items:
            del m["owner_key"]
        story["sources"] = sorted({m["source_name"] for m in items})
        story["members"] = items if member_limit is None else items[:member_limit]
        rep = next((m for m in items if m["id"] == story["representative_id"]), items[-1] if items else None)
        story["representative"] = rep
        # The first outlet to report it (by publication time), where several outlets did.
        earliest = min(items, key=lambda m: m["sort_at"]) if items else None
        story["first"] = ({"source": earliest["source_name"], "at": earliest["sort_at"]}
                          if earliest is not None and len(story["sources"]) >= 2 else None)
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
