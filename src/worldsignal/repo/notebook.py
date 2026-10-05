"""Notebook: notes on stories, the daily meeting list and free notes per day.

Everything is filed under the user's *local* calendar day. Rows that refer to a
story also keep a snapshot of it (see migration 0004), so the notebook of a past
day still reads correctly after the story was merged, re-summarised or removed.
"""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Callable, Sequence
from datetime import date, datetime
from typing import Any

from ..db import Database, utc_now_iso
from .stories import StoryRepository

DAY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
MAX_NOTE = 20_000
MAX_COMMENT = 300


def local_today() -> str:
    return datetime.now().astimezone().date().isoformat()


def valid_day(day: str) -> bool:
    if not DAY_RE.match(day):
        return False
    try:
        date.fromisoformat(day)
    except ValueError:
        return False
    return True


def _texts(story: dict[str, Any]) -> dict[str, dict[str, str]]:
    """The story's AI texts by language, the representative report's where the story has none."""
    rep = story.get("representative") or {}
    own = story.get("ai_texts") or {} if story.get("ai_status") == "done" else {}
    out: dict[str, dict[str, str]] = {}
    for lang, t in (rep.get("ai_texts") or {}).items():
        out[lang] = {"title": t.get("title", ""), "summary": t.get("summary", ""), "why": ""}
    for lang, t in own.items():
        out[lang] = {"title": t.get("title", ""), "summary": t.get("summary", ""), "why": t.get("why", "")}
        if "points" in t:  # summaries written before 0.13.4 have none (absent: still to be written)
            out[lang]["points"] = t["points"]
    return out


def story_headline(story: dict[str, Any], lang: str | None = None) -> str:
    """Same order as the UI: story AI title, representative's AI title (in ``lang`` if there is one, else any
    language), original title."""
    texts = _texts(story)
    if lang in texts and texts[lang]["title"]:
        return texts[lang]["title"]
    for t in texts.values():
        if t["title"]:
            return t["title"]
    rep = story.get("representative") or {}
    return str(rep.get("title") or "")


def story_snapshot(story: dict[str, Any]) -> dict[str, Any]:
    """What the notebook keeps of a story, in every AI language. Only AI text is kept as summary
    (copyright: outputs never carry the publishers' own text), plus one link per source: the representative report's
    source first, then the reports closest to the story (outputs show only the first few)."""
    rep_id = (story.get("representative") or {}).get("id")
    members = sorted(story.get("members") or [], key=lambda m: m["sort_at"])
    members.sort(key=lambda m: (rep_id is None or m.get("id") != rep_id,
                                -(m.get("similarity") if m.get("similarity") is not None else 1.0)))
    sources: dict[str, str] = {}
    for m in members:
        sources.setdefault(m["source_name"], m["url"])
    return {
        "title": story_headline(story),
        "texts": _texts(story),
        "category": story.get("category"),
        "sources": [{"name": n, "url": u} for n, u in sources.items()],
    }


def article_snapshot(row: sqlite3.Row) -> dict[str, Any]:
    """What the notebook keeps of one report: only its AI texts (never the publisher's own text) and one link."""
    texts: dict[str, dict[str, str]] = {}
    for lang, t in json.loads(row["ai_texts"] or "{}").items():
        texts[lang] = {"title": t.get("title", ""), "summary": t.get("summary", ""), "why": ""}
        if "points" in t:
            texts[lang]["points"] = t["points"]
    return {"title": row["title"], "texts": texts, "category": row["category"],
            "sources": [{"name": row["source_name"], "url": row["url"]}]}


ARTICLE_SQL = """SELECT a.id, a.title, a.url, s.name AS source_name, x.texts AS ai_texts, x.category
                 FROM articles a JOIN sources s ON s.id = a.source_id
                 LEFT JOIN article_ai x ON x.article_id = a.id AND x.status = 'done'
                 WHERE a.id = ?"""


class NotebookRepository:
    def __init__(self, db: Database, stories: StoryRepository, today: Callable[[], str] = local_today) -> None:
        self.db = db
        self.stories = stories
        self.today = today

    # -- story notes ------------------------------------------------------------------------------
    def story_note(self, story_id: int) -> dict[str, Any] | None:
        row = self.db.conn.execute("SELECT * FROM story_notes WHERE story_id = ?", (story_id,)).fetchone()
        return dict(row) if row else None

    def save_story_note(self, story_id: int, body: str) -> dict[str, Any] | None:
        """Create, update or (empty body) delete the note of a story. Returns the note or None."""
        story = self.stories.get(story_id, member_limit=1)
        if story is None:
            raise KeyError(story_id)
        body = body[:MAX_NOTE]
        now = utc_now_iso()
        with self.db.transaction() as c:
            if not body.strip():
                c.execute("DELETE FROM story_notes WHERE story_id = ?", (story_id,))
                return None
            c.execute(
                """INSERT INTO story_notes (story_id, day, title, body, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT(story_id) DO UPDATE SET body = excluded.body, title = excluded.title,
                                                       updated_at = excluded.updated_at""",
                (story_id, self.today(), story_headline(story), body, now, now),
            )
        return self.story_note(story_id)

    # -- meeting list -----------------------------------------------------------------------------
    def meeting(self, day: str) -> list[dict[str, Any]]:
        if day == self.today():
            self._refresh_snapshots(day)
        rows = self.db.conn.execute("SELECT * FROM meeting_items WHERE day = ? ORDER BY position, id", (day,)).fetchall()
        return [self._item(r) for r in rows]

    def add_to_meeting(self, story_id: int) -> dict[str, Any]:
        """Append a story to today's list (no-op if it is already there). Returns the item."""
        day = self.today()
        story = self.stories.get(story_id)
        if story is None:
            raise KeyError(story_id)
        snap = story_snapshot(story)
        now = utc_now_iso()
        with self.db.transaction() as c:
            existing = c.execute("SELECT id FROM meeting_items WHERE day = ? AND story_id = ?", (day, story_id)).fetchone()
            if existing is None:
                pos = c.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM meeting_items WHERE day = ?", (day,)).fetchone()[0]
                cur = c.execute(
                    """INSERT INTO meeting_items (day, story_id, position, title, texts, category, sources,
                                                  created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (day, story_id, pos, snap["title"], json.dumps(snap["texts"], ensure_ascii=False),
                     snap["category"], json.dumps(snap["sources"], ensure_ascii=False), now, now),
                )
                item_id = cur.lastrowid
            else:
                item_id = existing["id"]
        return self._get_item(int(item_id))  # type: ignore[arg-type]

    def add_article_to_meeting(self, article_id: int) -> dict[str, Any]:
        """Append one report to today's list (no-op if it is already there). Returns the item."""
        day = self.today()
        row = self.db.conn.execute(ARTICLE_SQL, (article_id,)).fetchone()
        if row is None:
            raise KeyError(article_id)
        snap = article_snapshot(row)
        now = utc_now_iso()
        with self.db.transaction() as c:
            existing = c.execute("SELECT id FROM meeting_items WHERE day = ? AND article_id = ?", (day, article_id)).fetchone()
            if existing is None:
                pos = c.execute("SELECT COALESCE(MAX(position), -1) + 1 FROM meeting_items WHERE day = ?", (day,)).fetchone()[0]
                cur = c.execute(
                    """INSERT INTO meeting_items (day, story_id, article_id, position, title, texts, category, sources,
                                                  created_at, updated_at)
                       VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (day, article_id, pos, snap["title"], json.dumps(snap["texts"], ensure_ascii=False),
                     snap["category"], json.dumps(snap["sources"], ensure_ascii=False), now, now),
                )
                item_id = cur.lastrowid
            else:
                item_id = existing["id"]
        return self._get_item(int(item_id))  # type: ignore[arg-type]

    def update_item(self, item_id: int, comment: str) -> dict[str, Any]:
        with self.db.transaction() as c:
            if c.execute(
                "UPDATE meeting_items SET comment = ?, updated_at = ? WHERE id = ?",
                (comment.strip()[:MAX_COMMENT], utc_now_iso(), item_id),
            ).rowcount == 0:
                raise KeyError(item_id)
        return self._get_item(item_id)

    def remove_item(self, item_id: int) -> None:
        with self.db.transaction() as c:
            row = c.execute("SELECT day FROM meeting_items WHERE id = ?", (item_id,)).fetchone()
            if row is None:
                raise KeyError(item_id)
            c.execute("DELETE FROM meeting_items WHERE id = ?", (item_id,))
            self._renumber(c, row["day"])

    def reorder(self, day: str, item_ids: Sequence[int]) -> list[dict[str, Any]]:
        """``item_ids`` must be exactly the items of that day, in the new order."""
        with self.db.transaction() as c:
            current = {r[0] for r in c.execute("SELECT id FROM meeting_items WHERE day = ?", (day,))}
            if current != set(item_ids) or len(item_ids) != len(current):
                raise ValueError("order_mismatch")
            now = utc_now_iso()
            c.executemany(
                "UPDATE meeting_items SET position = ?, updated_at = ? WHERE id = ?",
                [(pos, now, iid) for pos, iid in enumerate(item_ids)],
            )
        return self.meeting(day)

    def meeting_story_ids(self, day: str) -> list[int]:
        return [r[0] for r in self.db.conn.execute(
            "SELECT story_id FROM meeting_items WHERE day = ? AND story_id IS NOT NULL", (day,))]

    # -- day notes & notebook ---------------------------------------------------------------------
    def save_day_note(self, day: str, body: str) -> dict[str, Any] | None:
        body = body[:MAX_NOTE]
        with self.db.transaction() as c:
            if not body.strip():
                c.execute("DELETE FROM day_notes WHERE day = ?", (day,))
                return None
            c.execute(
                """INSERT INTO day_notes (day, body, updated_at) VALUES (?, ?, ?)
                   ON CONFLICT(day) DO UPDATE SET body = excluded.body, updated_at = excluded.updated_at""",
                (day, body, utc_now_iso()),
            )
        return self.day(day)["day_note"]

    def day(self, day: str) -> dict[str, Any]:
        note = self.db.conn.execute("SELECT body, updated_at FROM day_notes WHERE day = ?", (day,)).fetchone()
        notes = self.db.conn.execute(
            """SELECT n.*, (st.id IS NOT NULL) AS story_exists FROM story_notes n
               LEFT JOIN stories st ON st.id = n.story_id
               WHERE n.day = ? ORDER BY n.created_at""",
            (day,),
        ).fetchall()
        return {
            "day": day,
            "today": self.today(),
            "day_note": dict(note) if note else None,
            "meeting": self.meeting(day),
            "notes": [{**dict(n), "story_exists": bool(n["story_exists"])} for n in notes],
        }

    def days(self, month: str) -> list[dict[str, Any]]:
        """Days of a month (YYYY-MM) that have anything in the notebook, with counts."""
        like = f"{month}-%"
        rows = self.db.conn.execute(
            """SELECT day, SUM(notes) AS notes, SUM(meeting) AS meeting, SUM(day_note) AS day_note FROM (
                   SELECT day, 1 AS notes, 0 AS meeting, 0 AS day_note FROM story_notes WHERE day LIKE ?
                   UNION ALL SELECT day, 0, 1, 0 FROM meeting_items WHERE day LIKE ?
                   UNION ALL SELECT day, 0, 0, 1 FROM day_notes WHERE day LIKE ?)
               GROUP BY day ORDER BY day""",
            (like, like, like),
        ).fetchall()
        return [{"day": r["day"], "notes": r["notes"], "meeting": r["meeting"], "day_note": bool(r["day_note"])} for r in rows]

    # -- internals --------------------------------------------------------------------------------
    def _item(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        item["sources"] = json.loads(item["sources"] or "[]")
        item["texts"] = json.loads(item["texts"] or "{}")
        for old in ("summary", "why", "title_en", "summary_en", "why_en"):
            item.pop(old, None)  # before 0.11: replaced by texts
        return item

    def _get_item(self, item_id: int) -> dict[str, Any]:
        row = self.db.conn.execute("SELECT * FROM meeting_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise KeyError(item_id)
        return self._item(row)

    def _renumber(self, c: sqlite3.Connection, day: str) -> None:
        renumber(c, day)

    def _refresh_snapshots(self, day: str) -> None:
        """Today's list follows its stories (AI summaries arrive, sources grow)."""
        items = self.db.conn.execute(
            "SELECT id, story_id FROM meeting_items WHERE day = ? AND story_id IS NOT NULL", (day,)
        ).fetchall()
        updates = []
        for it in items:
            story = self.stories.get(it["story_id"])
            if story is None:
                continue
            snap = story_snapshot(story)
            updates.append((snap["title"], json.dumps(snap["texts"], ensure_ascii=False), snap["category"],
                            json.dumps(snap["sources"], ensure_ascii=False), it["id"]))
        for it in self.db.conn.execute(
            "SELECT id, article_id FROM meeting_items WHERE day = ? AND article_id IS NOT NULL", (day,)
        ).fetchall():
            row = self.db.conn.execute(ARTICLE_SQL, (it["article_id"],)).fetchone()
            if row is None:
                continue
            snap = article_snapshot(row)  # the report's AI texts arrive after it was listed
            updates.append((snap["title"], json.dumps(snap["texts"], ensure_ascii=False), snap["category"],
                            json.dumps(snap["sources"], ensure_ascii=False), it["id"]))
        if updates:
            with self.db.transaction() as c:
                c.executemany(
                    """UPDATE meeting_items SET title = ?, texts = ?, category = ?, sources = ? WHERE id = ?""",
                    updates,
                )


def renumber(c: sqlite3.Connection, day: str) -> None:
    ids = [r[0] for r in c.execute("SELECT id FROM meeting_items WHERE day = ? ORDER BY position, id", (day,))]
    c.executemany("UPDATE meeting_items SET position = ? WHERE id = ?", [(pos, iid) for pos, iid in enumerate(ids)])


def reassign_story(c: sqlite3.Connection, source_id: int, target_id: int) -> None:
    """Two stories were merged: notes and meeting items follow the surviving story.

    Called inside the merge transaction. A note on both stories becomes one note; a story
    listed twice on the same day stays once (with both comments)."""
    src = c.execute("SELECT id, body FROM story_notes WHERE story_id = ?", (source_id,)).fetchone()
    if src is not None:
        dst = c.execute("SELECT id, body FROM story_notes WHERE story_id = ?", (target_id,)).fetchone()
        if dst is None:
            c.execute("UPDATE story_notes SET story_id = ? WHERE id = ?", (target_id, src["id"]))
        else:
            c.execute("UPDATE story_notes SET body = ?, updated_at = ? WHERE id = ?",
                      (f"{dst['body']}\n\n{src['body']}", utc_now_iso(), dst["id"]))
            c.execute("DELETE FROM story_notes WHERE id = ?", (src["id"],))
    for item in c.execute("SELECT id, day, comment FROM meeting_items WHERE story_id = ?", (source_id,)).fetchall():
        dup = c.execute("SELECT id, comment FROM meeting_items WHERE day = ? AND story_id = ?",
                        (item["day"], target_id)).fetchone()
        if dup is None:
            c.execute("UPDATE meeting_items SET story_id = ? WHERE id = ?", (target_id, item["id"]))
        else:
            comment = " ".join(x for x in (dup["comment"], item["comment"]) if x)[:MAX_COMMENT]
            c.execute("UPDATE meeting_items SET comment = ? WHERE id = ?", (comment, dup["id"]))
            c.execute("DELETE FROM meeting_items WHERE id = ?", (item["id"],))
            renumber(c, item["day"])
