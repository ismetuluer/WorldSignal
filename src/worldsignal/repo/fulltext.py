"""Full-text queue and results (table ``article_fulltext``) and per-source full-text settings.

Priority tiers: the user's own request > stories in the notebook / meeting list > important
stories picked automatically. Within a tier newer articles come first.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Collection, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..db import Database, utc_now_iso

TIERS = {"user": 3, "notebook": 2, "auto": 1}
MAX_ATTEMPTS = 3
PAUSE_AFTER = {  # error -> how long the site is left alone
    "bot_check": timedelta(hours=12),
    "http_403": timedelta(hours=6),
    "http_429": timedelta(hours=6),
    "paywall": timedelta(hours=3),
    "http_401": timedelta(hours=6),  # a site asking for a login is not asked again and again
}
# A refusal (bot check, 401/403/429) repeated within ``ESCALATE_WINDOW`` doubles the pause each time, up to
# ``MAX_PAUSE``: a site that keeps saying no is left alone for longer, so the subscription is not flagged.
REFUSALS = ("bot_check", "http_401", "http_403", "http_429")
ESCALATE_WINDOW = timedelta(days=3)
MAX_PAUSE = timedelta(hours=72)
FINAL_ERRORS = {"bot_check", "paywall", "not_article", "aggregator_link", "http_401", "http_403", "http_404", "http_410",
                "http_429"}


# Extension mode reads every paid report it has time for; exclusives first, the rest after important stories.
EXCLUSIVE_BOOST = 0.5
PAID_BOOST = -0.5
# The full-text mode actually used for a source ('off' sources are read only on the user's request).
EFFECTIVE_MODE = ("(CASE WHEN s.fulltext_mode = 'off' THEN (CASE WHEN s.paywalled THEN 'browser' ELSE 'http' END) "
                  "ELSE s.fulltext_mode END)")


def _priority(reason: str, sort_at: str, boost: float = 0.0) -> float:
    epoch = datetime.strptime(sort_at, "%Y-%m-%dT%H:%M:%SZ").timestamp()
    return (TIERS[reason] + boost) * 1e10 + epoch


@dataclass
class BrowserPace:
    """How a person reads a subscription site (sources read in the browser), on top of the hourly limit.

    ``gap``: at least this long between two pages of the same site; ``user_gap`` for pages the user asked for
    (a person clicking through articles). ``per_day``: pages per site since ``day_start`` (local midnight).
    ``resting``: night hours, when only the user's own requests are read. The user's requests ignore the
    daily limit and the night, never the gap."""

    gap: timedelta
    user_gap: timedelta
    per_day: int
    day_start: datetime
    resting: bool


@dataclass
class FullTextJob:
    article_id: int
    url: str
    source_id: int
    source_name: str
    mode: str  # http | browser
    reason: str
    attempts: int
    summary: str


class FullTextRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    # -- queue ------------------------------------------------------------------------------------
    def enqueue(self, article_ids: list[int], reason: str, boost: float = 0.0) -> int:
        """Queue articles (a higher reason upgrades an existing pending row). Returns rows added/upgraded.
        ``boost`` moves the article within its tier (``EXCLUSIVE_BOOST`` / ``PAID_BOOST``)."""
        if not article_ids:
            return 0
        now = utc_now_iso()
        changed = 0
        with self.db.transaction() as c:
            for aid in article_ids:
                row = c.execute("SELECT sort_at FROM articles WHERE id = ?", (aid,)).fetchone()
                if row is None:
                    continue
                prio = _priority(reason, row["sort_at"], boost)
                cur = c.execute(
                    """INSERT INTO article_fulltext (article_id, status, reason, priority, queued_at)
                       VALUES (?, 'pending', ?, ?, ?)
                       ON CONFLICT(article_id) DO UPDATE SET reason = excluded.reason, priority = excluded.priority
                       WHERE article_fulltext.status = 'pending' AND article_fulltext.priority < excluded.priority""",
                    (aid, reason, prio, now),
                )
                changed += cur.rowcount
        return changed

    def drop_stale_auto(self, before_iso: str, keep: Collection[int] = ()) -> int:
        """Forget automatically queued articles (reason ``auto``) still waiting although their report is older than
        ``before_iso``: in extension mode more paid reports are queued than a person's pace can read, and they would
        pile up. The user's own requests and notebook articles are never dropped, nor a row tried since
        ``before_iso`` (its attempts still count) or an article in ``keep`` (the one the extension is reading).
        Returns the rows removed."""
        kept = {f"k{i}": aid for i, aid in enumerate(keep)}
        keep_sql = f" AND article_id NOT IN ({', '.join(':' + k for k in kept)})" if kept else ""
        with self.db.transaction() as c:
            # Correlated over the (small) pending set rather than over every old article.
            cur = c.execute(
                """DELETE FROM article_fulltext WHERE status = 'pending' AND reason = 'auto'
                     AND (attempted_at IS NULL OR attempted_at < :before)
                     AND EXISTS (SELECT 1 FROM articles a WHERE a.id = article_fulltext.article_id
                                 AND a.sort_at < :before)""" + keep_sql,
                {"before": before_iso, **kept},
            )
        return cur.rowcount

    def request(self, article_id: int) -> str:
        """The user asked for this article's full text (also retries a failed or blocked one)."""
        with self.db.transaction() as c:
            art = c.execute("SELECT sort_at FROM articles WHERE id = ?", (article_id,)).fetchone()
            if art is None:
                raise KeyError(article_id)
            row = c.execute("SELECT status FROM article_fulltext WHERE article_id = ?", (article_id,)).fetchone()
            if row is not None and row["status"] == "done":
                return "done"
            c.execute(
                """INSERT INTO article_fulltext (article_id, status, reason, priority, queued_at)
                   VALUES (?, 'pending', 'user', ?, ?)
                   ON CONFLICT(article_id) DO UPDATE SET status = 'pending', reason = 'user', priority = excluded.priority,
                       attempts = 0, error_code = NULL""",
                (article_id, _priority("user", art["sort_at"]), utc_now_iso()),
            )
        return "pending"

    def next_job(self, now: datetime, per_site_hour: int, browser: BrowserPace | None = None,
                 user_only: bool = False, modes: tuple[str, ...] = ("http", "browser"),
                 exclude_sources: Collection[int] = ()) -> FullTextJob | None:
        """Highest-priority pending article whose site is not paused, not over its hourly limit and
        whose full-text mode allows fetching (the user's own requests ignore 'off'). Sites read in the
        browser also follow ``browser`` (a person's pace). ``modes`` limits the jobs to those full-text modes
        (extension mode leaves "browser" to the user's own browser). ``exclude_sources`` are source ids to skip
        (the extension bridge rests a site after trouble without stalling the others)."""
        now_iso = utc_now_iso(now)
        hour_ago = utc_now_iso(now - timedelta(hours=1))
        pace_sql, pace_params = "", {}
        if browser is not None:
            pace_sql = """
                 AND (""" + EFFECTIVE_MODE + """ != 'browser'
                      OR (NOT EXISTS (SELECT 1 FROM article_fulltext f3 JOIN articles a3 ON a3.id = f3.article_id
                                      WHERE a3.source_id = s.id
                                        AND f3.attempted_at >= (CASE WHEN f.reason = 'user' THEN :user_gap ELSE :gap END))
                          AND (f.reason = 'user'
                               OR (:resting = 0
                                   AND (SELECT COUNT(*) FROM article_fulltext f4 JOIN articles a4 ON a4.id = f4.article_id
                                        WHERE a4.source_id = s.id AND f4.attempted_at >= :day_start) < :per_day))))"""
            pace_params = {"gap": utc_now_iso(now - browser.gap), "user_gap": utc_now_iso(now - browser.user_gap),
                           "resting": int(browser.resting), "day_start": utc_now_iso(browser.day_start),
                           "per_day": browser.per_day}
        mode_names = {f"mode{i}": m for i, m in enumerate(modes)}
        mode_sql = f" AND {EFFECTIVE_MODE} IN ({', '.join(':' + k for k in mode_names)})"
        excluded = {f"ex{i}": sid for i, sid in enumerate(exclude_sources)}
        if excluded:
            mode_sql += f" AND s.id NOT IN ({', '.join(':' + k for k in excluded)})"
        row = self.db.conn.execute(
            """SELECT f.article_id, a.url, s.id AS source_id, s.name AS source_name, s.paywalled, f.reason, f.attempts,
                      a.summary, s.fulltext_mode
               FROM article_fulltext f
               JOIN articles a ON a.id = f.article_id
               JOIN sources s ON s.id = a.source_id
               WHERE f.status = 'pending' AND s.enabled = 1
                 AND (s.fulltext_mode != 'off' OR f.reason = 'user')
                 AND (f.reason = 'user' OR :user_only = 0)
                 AND (s.fulltext_paused_until IS NULL OR s.fulltext_paused_until <= :now)
                 AND (SELECT COUNT(*) FROM article_fulltext f2 JOIN articles a2 ON a2.id = f2.article_id
                      WHERE a2.source_id = s.id AND f2.attempted_at >= :hour_ago) < :per_hour""" + pace_sql + mode_sql + """
               ORDER BY f.priority DESC LIMIT 1""",
            {"now": now_iso, "hour_ago": hour_ago, "per_hour": per_site_hour, "user_only": int(user_only), **pace_params, **mode_names,
             **excluded},
        ).fetchone()
        if row is None:
            return None
        mode = row["fulltext_mode"]
        if mode == "off":  # a user request on a source that is switched off
            mode = "browser" if row["paywalled"] else "http"
        return FullTextJob(row["article_id"], row["url"], row["source_id"], row["source_name"], mode, row["reason"],
                           row["attempts"], row["summary"] or "")

    def mark_attempt(self, article_id: int, now: datetime) -> str | None:
        """Note the attempt (the per-site pace counts it); returns the previous time, for ``release_attempt``."""
        with self.db.transaction() as c:
            row = c.execute("SELECT attempted_at FROM article_fulltext WHERE article_id = ?", (article_id,)).fetchone()
            c.execute("UPDATE article_fulltext SET attempted_at = ? WHERE article_id = ?", (utc_now_iso(now), article_id))
        return row[0] if row else None

    def release_attempt(self, article_id: int, previous: str | None) -> None:
        """The attempt never reached the site (the browser did not start): forget it."""
        with self.db.transaction() as c:
            c.execute("UPDATE article_fulltext SET attempted_at = ? WHERE article_id = ?", (previous, article_id))

    # -- results ----------------------------------------------------------------------------------
    def store_text(self, article_id: int, text: str, method: str, now: datetime) -> None:
        with self.db.transaction() as c:
            c.execute(
                """UPDATE article_fulltext SET status = 'done', method = ?, text = ?, chars = ?, error_code = NULL,
                       fetched_at = ?, attempts = attempts + 1, translate_status = NULL, translations = '{}'
                   WHERE article_id = ?""",
                (method, text, len(text), utc_now_iso(now), article_id),
            )

    def store_failure(self, job: FullTextJob, code: str, now: datetime, method: str | None = None) -> str:
        """Record a failed attempt; pause the site where that is wise. Returns the new status. ``method``: who read
        the page (default the job's mode; the browser extension passes ``extension``, as ``store_text`` gets it)."""
        attempts = job.attempts + 1
        final = code in FINAL_ERRORS or attempts >= MAX_ATTEMPTS
        status = ("blocked" if code == "bot_check" else "failed") if final else "pending"
        with self.db.transaction() as c:
            c.execute(
                "UPDATE article_fulltext SET status = ?, error_code = ?, attempts = ?, method = ? WHERE article_id = ?",
                (status, code, attempts, method or job.mode, job.article_id),
            )
            pause = PAUSE_AFTER.get(code)
            if pause is not None and code in REFUSALS:
                earlier = c.execute(
                    """SELECT COUNT(*) FROM article_fulltext f JOIN articles a ON a.id = f.article_id
                       WHERE a.source_id = ? AND f.error_code IN (?, ?, ?, ?) AND f.attempted_at >= ?
                         AND f.article_id != ?""",
                    (job.source_id, *REFUSALS, utc_now_iso(now - ESCALATE_WINDOW), job.article_id),
                ).fetchone()[0]
                pause = min(pause * 2 ** min(earlier, 6), MAX_PAUSE)
            if pause is not None:
                c.execute("UPDATE sources SET fulltext_paused_until = ? WHERE id = ?", (utc_now_iso(now + pause), job.source_id))
        return status

    def get(self, article_id: int) -> dict[str, Any] | None:
        row = self.db.conn.execute("SELECT * FROM article_fulltext WHERE article_id = ?", (article_id,)).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["translations"] = json.loads(d["translations"] or "{}")
        for old in ("text_tr", "text_en"):
            d.pop(old, None)  # before 0.11: replaced by translations
        return d

    def statuses(self, article_ids: list[int]) -> dict[int, dict[str, Any]]:
        """Light status (no text) for a list of articles, for the story view."""
        if not article_ids:
            return {}
        rows = self.db.conn.execute(
            f"""SELECT article_id, status, error_code, chars, method, translate_status, fetched_at
                FROM article_fulltext WHERE article_id IN ({','.join('?' * len(article_ids))})""",
            article_ids,
        ).fetchall()
        return {r["article_id"]: dict(r) for r in rows}

    def counts(self) -> dict[str, int]:
        row = self.db.conn.execute(
            """SELECT SUM(status = 'pending') AS pending, SUM(status = 'done') AS done,
                      SUM(status = 'failed') AS failed, SUM(status = 'blocked') AS blocked FROM article_fulltext"""
        ).fetchone()
        return {k: int(row[k] or 0) for k in ("pending", "done", "failed", "blocked")}

    def sites(self) -> list[dict[str, Any]]:
        """Sources read through the browser (subscriptions), with the outcome of their latest attempt:
        tells the user whether the sign-in works."""
        rows = self.db.conn.execute(
            """SELECT s.id, s.name, s.homepage, s.fulltext_mode, s.fulltext_paused_until, s.enabled,
                      (SELECT f.status || '|' || COALESCE(f.error_code, '') || '|' || f.attempted_at
                       FROM article_fulltext f JOIN articles a ON a.id = f.article_id
                       WHERE a.source_id = s.id AND f.attempted_at IS NOT NULL AND f.status != 'pending'
                       ORDER BY f.attempted_at DESC LIMIT 1) AS last,
                      (SELECT COUNT(*) FROM article_fulltext f JOIN articles a ON a.id = f.article_id
                       WHERE a.source_id = s.id AND f.status = 'pending') AS queued
               FROM sources s
               WHERE s.enabled = 1 AND (s.fulltext_mode = 'browser' OR s.paywalled = 1)
               ORDER BY s.name COLLATE NOCASE"""
        ).fetchall()
        out = []
        for r in rows:
            item = {k: r[k] for k in ("id", "name", "homepage", "fulltext_mode", "fulltext_paused_until", "queued")}
            if r["last"]:
                status, code, at = r["last"].split("|", 2)
                item["last"] = {"status": status, "error_code": code or None, "at": at}
            else:
                item["last"] = None
            out.append(item)
        return out

    def recheck(self, judge: Callable[[str], Any], max_chars: int) -> dict[str, int]:
        """Apply today's extraction rules to short texts stored earlier. A text that turns out to be a
        subscription offer or page furniture becomes a failure with its reason; its AI summary (written
        from that text) is redone from the feed summary. Cleaned texts are stored cleaned."""
        rows = self.db.conn.execute(
            "SELECT article_id, text FROM article_fulltext WHERE status = 'done' AND chars <= ?", (max_chars,)
        ).fetchall()
        result = {"rejected": 0, "cleaned": 0}
        with self.db.transaction() as c:
            for r in rows:
                verdict = judge(r["text"] or "")
                if verdict.text is None:
                    c.execute(
                        """UPDATE article_fulltext SET status = 'failed', error_code = ?, text = NULL, chars = NULL,
                               translate_status = NULL, translations = '{}' WHERE article_id = ?""",
                        (verdict.error_code, r["article_id"]),
                    )
                    c.execute(
                        """UPDATE article_ai SET status = 'pending', requested_by_user = 1, attempts = 0
                           WHERE article_id = ? AND status = 'done'""",
                        (r["article_id"],),
                    )
                    result["rejected"] += 1
                elif verdict.text != r["text"]:
                    c.execute("UPDATE article_fulltext SET text = ?, chars = ? WHERE article_id = ?",
                              (verdict.text, len(verdict.text), r["article_id"]))
                    result["cleaned"] += 1
        return result

    def latest_article(self, source_id: int) -> int | None:
        row = self.db.conn.execute(
            "SELECT id FROM articles WHERE source_id = ? ORDER BY sort_at DESC, id DESC LIMIT 1", (source_id,)
        ).fetchone()
        return int(row["id"]) if row else None

    def paused_sources(self, now: datetime) -> list[dict[str, Any]]:
        rows = self.db.conn.execute(
            "SELECT id, name, fulltext_paused_until FROM sources WHERE fulltext_paused_until > ? ORDER BY name",
            (utc_now_iso(now),),
        ).fetchall()
        return [dict(r) for r in rows]

    def resume_source(self, source_id: int) -> None:
        with self.db.transaction() as c:
            c.execute("UPDATE sources SET fulltext_paused_until = NULL WHERE id = ?", (source_id,))

    # -- translations of the full text ------------------------------------------------------------
    def request_translation(self, article_id: int, languages: Sequence[str] = ()) -> str:
        """Translate the full text into ``languages`` (except its own language). Already translated: "done",
        unless a language was added since."""
        with self.db.transaction() as c:
            row = c.execute(
                """SELECT f.status, f.translate_status, f.translations, COALESCE(a.language, s.language) AS language
                   FROM article_fulltext f JOIN articles a ON a.id = f.article_id JOIN sources s ON s.id = a.source_id
                   WHERE f.article_id = ?""", (article_id,)).fetchone()
            if row is None or row["status"] != "done":
                raise LookupError(article_id)
            have = json.loads(row["translations"] or "{}")
            if row["translate_status"] == "done" and all(have.get(l) for l in languages if l != row["language"]):
                return "done"
            c.execute("UPDATE article_fulltext SET translate_status = 'pending' WHERE article_id = ?", (article_id,))
        return "pending"

    def next_translation(self) -> dict[str, Any] | None:
        """The next full text the user asked to translate, with the translations it already has."""
        row = self.db.conn.execute(
            """SELECT f.article_id, f.text, f.translations, COALESCE(a.language, s.language) AS language,
                      s.name AS source_name
               FROM article_fulltext f JOIN articles a ON a.id = f.article_id JOIN sources s ON s.id = a.source_id
               WHERE f.translate_status = 'pending' ORDER BY f.fetched_at DESC LIMIT 1"""
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["translations"] = json.loads(d["translations"] or "{}")
        return d

    def store_translation(self, article_id: int, translations: dict[str, str]) -> None:
        with self.db.transaction() as c:
            c.execute(
                """UPDATE article_fulltext SET translate_status = 'done', translations = ?, translated_at = ?
                   WHERE article_id = ?""",
                (json.dumps(translations, ensure_ascii=False), utc_now_iso(), article_id),
            )

    def store_translation_failure(self, article_id: int) -> None:
        with self.db.transaction() as c:
            c.execute("UPDATE article_fulltext SET translate_status = 'failed' WHERE article_id = ?", (article_id,))

    # -- which articles to fetch automatically ----------------------------------------------------
    def auto_candidates(self, since_iso: str, min_score: float, per_story: int, today: str,
                        paid: bool = False) -> dict[str, list[int]]:
        """Articles worth a full text: members of important stories (``auto``) and of stories the
        user put in the notebook or today's meeting list (``notebook``). Browser sources first
        (that is where the RSS text is shortest), then the newest. With ``paid`` (extension mode) every recent
        report of a browser source is offered too: ``exclusive`` ones first, then the other ``paid`` ones."""
        notebook = [r[0] for r in self.db.conn.execute(
            """SELECT story_id FROM meeting_items WHERE day = ? AND story_id IS NOT NULL
               UNION SELECT story_id FROM story_notes WHERE story_id IS NOT NULL AND updated_at >= ?""",
            (today, since_iso),
        )]
        important = [r[0] for r in self.db.conn.execute(
            "SELECT id FROM stories WHERE score >= ? AND last_seen_at >= ? ORDER BY score DESC LIMIT 40",
            (min_score, since_iso),
        )]
        out: dict[str, list[int]] = {"notebook": [], "auto": []}
        for reason, story_ids, limit in (("notebook", notebook, max(per_story, 3)), ("auto", important, per_story)):
            for sid in story_ids:
                # The limit counts every member already queued or tried, so a story never gets more.
                have = self.db.conn.execute(
                    """SELECT COUNT(*) FROM story_articles sa JOIN article_fulltext f ON f.article_id = sa.article_id
                       WHERE sa.story_id = ?""",
                    (sid,),
                ).fetchone()[0]
                if have >= limit:
                    continue
                # Automatic picks are recent reports only (as ``drop_stale_auto`` keeps them), or an older member of a
                # long story would be dropped and queued again at every step.
                rows = self.db.conn.execute(
                    """SELECT a.id FROM story_articles sa
                       JOIN articles a ON a.id = sa.article_id JOIN sources s ON s.id = a.source_id
                       WHERE sa.story_id = ? AND s.enabled = 1 AND s.fulltext_mode != 'off'
                         AND (? = 'notebook' OR a.sort_at >= ?)
                         AND NOT EXISTS (SELECT 1 FROM article_fulltext f WHERE f.article_id = a.id)
                       ORDER BY s.fulltext_mode = 'browser' DESC, a.sort_at DESC LIMIT ?""",
                    (sid, reason, since_iso, limit - have),
                ).fetchall()
                out[reason] += [r[0] for r in rows]
        # A single report on today's meeting list is read too.
        out["notebook"] += [r[0] for r in self.db.conn.execute(
            """SELECT a.id FROM meeting_items m JOIN articles a ON a.id = m.article_id JOIN sources s ON s.id = a.source_id
               WHERE m.day = ? AND s.enabled = 1 AND s.fulltext_mode != 'off'
                 AND NOT EXISTS (SELECT 1 FROM article_fulltext f WHERE f.article_id = a.id)""", (today,))]
        out["exclusive"], out["paid"] = [], []
        if paid:
            from ..flags import is_exclusive  # flags imports nothing from repo

            rows = self.db.conn.execute(
                """SELECT a.id, a.title FROM articles a JOIN sources s ON s.id = a.source_id
                   WHERE s.enabled = 1 AND s.fulltext_mode = 'browser' AND a.sort_at >= ?
                     AND NOT EXISTS (SELECT 1 FROM article_fulltext f WHERE f.article_id = a.id)
                   ORDER BY a.sort_at DESC LIMIT 300""",
                (since_iso,),
            ).fetchall()
            taken = set(out["notebook"]) | set(out["auto"])
            for r in rows:
                if r["id"] not in taken:
                    out["exclusive" if is_exclusive(r["title"]) else "paid"].append(r["id"])
        return out
