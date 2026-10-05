"""Sources (news outlets) and their feeds."""

from __future__ import annotations

import logging
import re
import sqlite3
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from ..db import Database, utc_now_iso
from .settings import CATALOG_REMOVED, SettingsRepository

log = logging.getLogger(__name__)

# The feed's region filter also offers "abroad": every source outside the user's own region (local = "turkey", the
# region of a user in Türkiye). Not a region of a source, so it is not in REGIONS.
ABROAD = "abroad"
HOME_REGION = "turkey"


def region_condition(regions: Sequence[str]) -> tuple[str, list[str]] | None:
    """SQL over ``s`` (sources) for the feed's region filter: the chosen regions, and/or "abroad"."""
    regions = list(dict.fromkeys(regions))
    plain = [r for r in regions if r != ABROAD]
    parts: list[str] = []
    if plain:
        parts.append(f"s.region IN ({','.join('?' * len(plain))})")
    if ABROAD in regions:
        parts.append("s.region != ?")
    params = plain + ([HOME_REGION] if ABROAD in regions else [])
    return (f"({' OR '.join(parts)})", params) if parts else None


CATALOG_GROUPS = ("western", "agency", "middle_east", "russia_ukraine", "asia", "europe", "other", "turkey", "sports")
REGIONS = (
    "global",
    "north_america",
    "latin_america",
    "europe",
    "middle_east",
    "russia_ukraine",
    "caucasus_central_asia",
    "asia",
    "africa",
    "turkey",
)

# Fields a user may edit on a source.
SOURCE_EDITABLE = {"name", "homepage", "catalog_group", "owner", "region", "language", "reliability", "enabled", "paywalled",
                   "note", "fulltext_mode"}
FEED_EDITABLE = {"label", "enabled", "fetch_interval_min"}


class NotFound(Exception):
    pass


class Conflict(Exception):
    """E.g. a feed URL that already exists."""


@dataclass
class DueFeed:
    id: int
    source_id: int
    url: str
    etag: str | None
    last_modified: str | None
    fetch_interval_min: int
    consecutive_failures: int
    language: str
    keep_only: str | None = None  # "exclusive": store only the reports labelled exclusive by their publisher


def _slugify(name: str) -> str:
    ascii_name = unicodedata.normalize("NFKD", name.replace("ı", "i")).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return slug or "source"


class SourceRepository:
    def __init__(self, db: Database, settings: SettingsRepository) -> None:
        self.db = db
        self.settings = settings

    # -- catalog -----------------------------------------------------------
    def seed_from_catalog(self, catalog: dict[str, Any]) -> int:
        """Insert catalog sources that are not in the database yet.

        Existing rows are never modified (the user may have edited them) and
        catalog sources the user deleted are not re-added. New feeds of an
        existing catalog source are added. Returns the number of new feeds.

        Catalog maintenance that does reach existing rows:
        - feeds listed in ``retired_feeds`` (dead addresses the catalog replaced) are deleted from catalog sources;
        - a catalog source that had no working feed (so it was added switched off, "not verified") is switched on
          once the catalog brings a verified feed for it.
        """
        removed = set(self.settings.get(CATALOG_REMOVED, []) or [])
        retired = list(catalog.get("retired_feeds", []))
        now = utc_now_iso()
        added = 0
        with self.db.transaction() as c:
            # Catalog sources without any working feed, decided before retiring feeds changes the picture.
            dormant = {
                r["id"]
                for r in c.execute(
                    """SELECT s.id FROM sources s WHERE s.origin = 'catalog'
                       AND NOT EXISTS (SELECT 1 FROM feeds f WHERE f.source_id = s.id AND f.verified = 1)"""
                )
            }
            if retired:
                marks = ",".join("?" * len(retired))
                cur = c.execute(
                    f"""DELETE FROM feeds WHERE url IN ({marks})
                        AND source_id IN (SELECT id FROM sources WHERE origin = 'catalog')""",  # noqa: S608
                    retired,
                )
                if cur.rowcount:
                    log.info("Catalog retired %d feeds", cur.rowcount)
            for s in catalog["sources"]:
                if s["slug"] in removed:
                    continue
                row = c.execute("SELECT id, origin FROM sources WHERE slug = ?", (s["slug"],)).fetchone()
                if row is None:
                    cur = c.execute(
                        """INSERT INTO sources (slug, name, homepage, catalog_group, owner, region, language,
                               reliability, enabled, paywalled, note, origin, created_at, updated_at, fulltext_mode)
                           VALUES (?, ?, ?, ?, ?, ?, ?, 1.0, ?, ?, ?, 'catalog', ?, ?, ?)""",
                        (
                            s["slug"], s["name"], s.get("homepage"), s["group"], s.get("owner"), s["region"],
                            s["language"], 1 if s["verified"] else 0, 1 if s.get("paywalled") else 0,
                            s.get("note"), now, now, s.get("fulltext_mode") or ("off" if s.get("paywalled") else "http"),
                        ),
                    )
                    source_id = cur.lastrowid
                elif row["origin"] == "catalog":
                    source_id = row["id"]
                    if s["verified"] and source_id in dormant:
                        c.execute("UPDATE sources SET enabled = 1, updated_at = ? WHERE id = ?", (now, source_id))
                        c.execute("DELETE FROM feeds WHERE source_id = ? AND verified = 0", (source_id,))
                        log.info("Catalog source %s is verified now; switched on", s["slug"])
                else:
                    continue
                for f in s["feeds"]:
                    cur = c.execute(
                        """INSERT OR IGNORE INTO feeds (source_id, url, label, enabled, verified, created_at, keep_only)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (source_id, f["url"], f.get("label"), 1 if f["verified"] else 0, 1 if f["verified"] else 0, now,
                         f.get("keep_only")),
                    )
                    added += cur.rowcount
        if added:
            log.info("Catalog seeding added %d feeds", added)
        return added

    # -- queries -------------------------------------------------------------
    def list_sources(self) -> list[dict[str, Any]]:
        sources = [dict(r) for r in self.db.conn.execute("SELECT * FROM sources ORDER BY catalog_group, name COLLATE NOCASE")]
        feeds_by_source: dict[int, list[dict[str, Any]]] = {}
        for r in self.db.conn.execute("SELECT * FROM feeds ORDER BY id"):
            f = _public_feed(dict(r))
            feeds_by_source.setdefault(f["source_id"], []).append(f)
        counts = {
            r["source_id"]: r["n"]
            for r in self.db.conn.execute(
                "SELECT source_id, COUNT(*) AS n FROM articles WHERE first_seen_at >= ? GROUP BY source_id",
                (_hours_ago_iso(24),),
            )
        }
        for s in sources:
            s["feeds"] = feeds_by_source.get(s["id"], [])
            s["articles_24h"] = counts.get(s["id"], 0)
            _add_source_status(s)
        return sources

    def get_source(self, source_id: int) -> dict[str, Any]:
        for s in self.list_sources():
            if s["id"] == source_id:
                return s
        raise NotFound(f"source {source_id}")

    def get_feed(self, feed_id: int) -> dict[str, Any]:
        row = self.db.conn.execute("SELECT * FROM feeds WHERE id = ?", (feed_id,)).fetchone()
        if row is None:
            raise NotFound(f"feed {feed_id}")
        return _public_feed(dict(row))

    # -- mutations -------------------------------------------------------------
    def create_source(self, data: dict[str, Any], feed_url: str, feed_label: str | None = None) -> int:
        now = utc_now_iso()
        base = _slugify(data["name"])
        with self.db.transaction() as c:
            slug, n = base, 2
            while c.execute("SELECT 1 FROM sources WHERE slug = ?", (slug,)).fetchone():
                slug, n = f"{base}-{n}", n + 1
            cur = c.execute(
                """INSERT INTO sources (slug, name, homepage, catalog_group, owner, region, language,
                       reliability, enabled, paywalled, note, origin, created_at, updated_at, fulltext_mode)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'user', ?, ?, ?)""",
                (
                    slug, data["name"], data.get("homepage"), data.get("catalog_group", "other"), data.get("owner"),
                    data.get("region", "global"), data.get("language", "en"), data.get("reliability", 1.0),
                    1 if data.get("paywalled") else 0, data.get("note"), now, now,
                    data.get("fulltext_mode") or ("off" if data.get("paywalled") else "http"),
                ),
            )
            source_id = int(cur.lastrowid)
            self._insert_feed(c, source_id, feed_url, feed_label, now)
        return source_id

    def update_source(self, source_id: int, changes: dict[str, Any]) -> None:
        changes = {k: v for k, v in changes.items() if k in SOURCE_EDITABLE}
        if not changes:
            return
        for key in ("enabled", "paywalled"):
            if key in changes:
                changes[key] = 1 if changes[key] else 0
        assignments = ", ".join(f"{k} = ?" for k in changes)
        with self.db.transaction() as c:
            cur = c.execute(
                f"UPDATE sources SET {assignments}, updated_at = ? WHERE id = ?",
                (*changes.values(), utc_now_iso(), source_id),
            )
            if cur.rowcount == 0:
                raise NotFound(f"source {source_id}")
            if changes.get("enabled") == 1:
                # Re-enabled sources are fetched promptly.
                c.execute("UPDATE feeds SET next_fetch_at = NULL WHERE source_id = ?", (source_id,))

    def delete_source(self, source_id: int) -> None:
        with self.db.transaction() as c:
            row = c.execute("SELECT slug, origin FROM sources WHERE id = ?", (source_id,)).fetchone()
            if row is None:
                raise NotFound(f"source {source_id}")
            c.execute("DELETE FROM sources WHERE id = ?", (source_id,))
            if row["origin"] == "catalog":
                removed = set(self.settings.get(CATALOG_REMOVED, []) or [])
                removed.add(row["slug"])
                self.settings.set(CATALOG_REMOVED, sorted(removed))

    def add_feed(self, source_id: int, url: str, label: str | None) -> int:
        with self.db.transaction() as c:
            if c.execute("SELECT 1 FROM sources WHERE id = ?", (source_id,)).fetchone() is None:
                raise NotFound(f"source {source_id}")
            return self._insert_feed(c, source_id, url, label, utc_now_iso())

    def _insert_feed(self, c: sqlite3.Connection, source_id: int, url: str, label: str | None, now: str) -> int:
        try:
            cur = c.execute(
                "INSERT INTO feeds (source_id, url, label, enabled, verified, created_at) VALUES (?, ?, ?, 1, 1, ?)",
                (source_id, url, label, now),
            )
        except sqlite3.IntegrityError as exc:
            raise Conflict("feed_exists") from exc
        return int(cur.lastrowid)

    def update_feed(self, feed_id: int, changes: dict[str, Any]) -> None:
        changes = {k: v for k, v in changes.items() if k in FEED_EDITABLE}
        if not changes:
            return
        if "enabled" in changes:
            changes["enabled"] = 1 if changes["enabled"] else 0
        assignments = ", ".join(f"{k} = ?" for k in changes)
        with self.db.transaction() as c:
            cur = c.execute(f"UPDATE feeds SET {assignments} WHERE id = ?", (*changes.values(), feed_id))
            if cur.rowcount == 0:
                raise NotFound(f"feed {feed_id}")
            if changes.get("enabled") == 1 or "fetch_interval_min" in changes:
                c.execute("UPDATE feeds SET next_fetch_at = NULL WHERE id = ?", (feed_id,))

    def delete_feed(self, feed_id: int) -> None:
        with self.db.transaction() as c:
            if c.execute("DELETE FROM feeds WHERE id = ?", (feed_id,)).rowcount == 0:
                raise NotFound(f"feed {feed_id}")

    # -- collector support --------------------------------------------------------
    def due_feeds(self, now_iso: str) -> list[DueFeed]:
        rows = self.db.conn.execute(
            """SELECT f.id, f.source_id, f.url, f.etag, f.last_modified, f.fetch_interval_min,
                      f.consecutive_failures, s.language, f.keep_only
               FROM feeds f JOIN sources s ON s.id = f.source_id
               WHERE f.enabled = 1 AND s.enabled = 1 AND (f.next_fetch_at IS NULL OR f.next_fetch_at <= ?)
               ORDER BY f.next_fetch_at IS NOT NULL, f.next_fetch_at""",
            (now_iso,),
        ).fetchall()
        return [DueFeed(**dict(r)) for r in rows]

    def last_attempt_at(self) -> str | None:
        """Most recent fetch attempt of any feed (survives restarts, unlike in-memory status)."""
        row = self.db.conn.execute("SELECT MAX(last_attempt_at) AS t FROM feeds").fetchone()
        return row["t"] if row else None

    def next_due_at(self) -> str | None:
        row = self.db.conn.execute(
            """SELECT MIN(COALESCE(f.next_fetch_at, '')) AS t FROM feeds f JOIN sources s ON s.id = f.source_id
               WHERE f.enabled = 1 AND s.enabled = 1"""
        ).fetchone()
        return row["t"] if row and row["t"] is not None else None

    def schedule_all_now(self, source_id: int | None = None) -> int:
        with self.db.transaction() as c:
            if source_id is None:
                cur = c.execute("UPDATE feeds SET next_fetch_at = NULL WHERE enabled = 1")
            else:
                cur = c.execute("UPDATE feeds SET next_fetch_at = NULL WHERE enabled = 1 AND source_id = ?", (source_id,))
            return cur.rowcount

    def record_success(
        self, c: sqlite3.Connection, feed_id: int, *, now: str, next_at: str, etag: str | None,
        last_modified: str | None, item_count: int | None, new_count: int, not_modified: bool,
    ) -> None:
        c.execute(
            """UPDATE feeds SET last_attempt_at = ?, last_success_at = ?, next_fetch_at = ?,
                   last_status = ?, last_error_code = NULL, last_error_detail = NULL, consecutive_failures = 0,
                   etag = ?, last_modified = ?, last_item_count = COALESCE(?, last_item_count), last_new_count = ?
               WHERE id = ?""",
            (now, now, next_at, "not_modified" if not_modified else "ok", etag, last_modified, item_count, new_count, feed_id),
        )

    def record_failure(self, feed_id: int, *, now: str, next_at: str, code: str, detail: str, count_failure: bool = True) -> None:
        with self.db.transaction() as c:
            c.execute(
                """UPDATE feeds SET last_attempt_at = ?, next_fetch_at = ?, last_status = 'error',
                       last_error_code = ?, last_error_detail = ?,
                       consecutive_failures = consecutive_failures + ?
                   WHERE id = ?""",
                (now, next_at, code, detail[:500], 1 if count_failure else 0, feed_id),
            )


def _public_feed(f: dict[str, Any]) -> dict[str, Any]:
    f.pop("etag", None)
    f.pop("last_modified", None)
    f["enabled"] = bool(f["enabled"])
    f["verified"] = bool(f["verified"])
    return f


def _add_source_status(s: dict[str, Any]) -> None:
    """Summarise feed health into one status the UI can show."""
    s["enabled"] = bool(s["enabled"])
    s["paywalled"] = bool(s["paywalled"])
    active = [f for f in s["feeds"] if f["enabled"]]
    s["verified"] = any(f["verified"] for f in s["feeds"])
    successes = [f["last_success_at"] for f in s["feeds"] if f["last_success_at"]]
    s["last_success_at"] = max(successes) if successes else None
    if not s["enabled"]:
        s["status"] = "disabled"
    elif not active:
        s["status"] = "no_feeds"
    elif all(f["last_status"] == "error" for f in active):
        s["status"] = "error"
    elif any(f["last_status"] == "error" for f in active):
        s["status"] = "partial"
    elif all(f["last_status"] == "pending" for f in active):
        s["status"] = "pending"
    else:
        s["status"] = "ok"


def _hours_ago_iso(hours: float) -> str:
    return utc_now_iso(datetime.now(UTC) - timedelta(hours=hours))
