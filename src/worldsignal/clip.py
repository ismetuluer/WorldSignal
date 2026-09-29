"""Pages the user sends from their own browser ("Send to World Signal").

Some sites (The Economist, WSJ ...) refuse every program that opens their pages, however politely. The user's own
browser is not refused: they read the article there, click a bookmark, and the page's HTML travels through the
clipboard into World Signal, which reads the article text from it exactly as it does for a downloaded page. Nothing
is fetched from the site and nothing is bypassed: the user is the one reading.

The clipboard text is a JSON object the bookmark writes: ``{"ws": 1, "url", "title", "lang", "html"}``.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import urlsplit

from .collector.rss import ParsedEntry, canonical_url
from .db import Database, utc_now_iso
from .fulltext.extract import extract
from .repo.articles import ArticleRepository
from .repo.fulltext import FullTextRepository

log = logging.getLogger(__name__)

MAX_CLIP_CHARS = 8_000_000
MAX_TITLE_CHARS = 300
SUMMARY_CHARS = 500
MANUAL_SLUG = "manual"


class ClipError(Exception):
    """``code`` is what the interface explains (``clip.error.<code>``)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


@dataclass
class Clip:
    url: str
    title: str
    lang: str
    html: str


def parse_clip(raw: str) -> Clip:
    """The pasted text, checked. Raises ``ClipError`` (bad_clip, too_large, bad_url)."""
    if len(raw) > MAX_CLIP_CHARS:
        raise ClipError("too_large")
    try:
        data = json.loads(raw.strip())
    except ValueError:
        raise ClipError("bad_clip", "not JSON") from None
    if not isinstance(data, dict) or data.get("ws") != 1:
        raise ClipError("bad_clip", "not from the bookmark")
    url, html = str(data.get("url") or "").strip(), str(data.get("html") or "")
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ClipError("bad_url", url[:80])
    if len(html) < 200:
        raise ClipError("bad_clip", "no page")
    title = " ".join(str(data.get("title") or "").split())[:MAX_TITLE_CHARS]
    lang = str(data.get("lang") or "").strip().lower().split("-")[0][:3]
    return Clip(url, title, lang if lang.isalpha() else "", html)


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host


class ClipService:
    def __init__(self, db: Database, articles: ArticleRepository, fulltext: FullTextRepository) -> None:
        self.db = db
        self.articles = articles
        self.fulltext = fulltext

    def source_for(self, c: sqlite3.Connection, url: str) -> sqlite3.Row:
        """The catalog source whose site the page is on (its region, group and weight then count), else the
        "added by hand" source."""
        host = _host(url)
        for row in c.execute("SELECT * FROM sources WHERE homepage IS NOT NULL AND slug != ?", (MANUAL_SLUG,)):
            site = _host(row["homepage"])
            if site and (host == site or host.endswith("." + site)):
                return row
        row = c.execute("SELECT * FROM sources WHERE slug = ?", (MANUAL_SLUG,)).fetchone()
        if row is None:
            now = utc_now_iso()
            c.execute(
                """INSERT INTO sources (slug, name, homepage, catalog_group, owner, region, language, reliability,
                       enabled, paywalled, note, origin, created_at, updated_at, fulltext_mode)
                   VALUES (?, 'Elle eklenenler', NULL, 'other', NULL, 'global', 'en', 1.0, 1, 0, NULL, 'user', ?, ?, 'off')""",
                (MANUAL_SLUG, now, now),
            )
            row = c.execute("SELECT * FROM sources WHERE slug = ?", (MANUAL_SLUG,)).fetchone()
        return row

    def add(self, raw: str, *, now: datetime | None = None) -> dict:
        """Store the page as a report with its full text. Raises ``ClipError`` (no_text, paywall, not_article ...)."""
        clip = parse_clip(raw)
        result = extract(clip.html, clip.url, 200)
        if not result.ok or not result.text:
            raise ClipError(result.error_code or "not_article")
        text = result.text
        now = now or datetime.now(UTC)
        title = clip.title or text.split("\n", 1)[0][:MAX_TITLE_CHARS]
        summary = " ".join(text.split())[:SUMMARY_CHARS]
        key = canonical_url(clip.url)
        with self.db.transaction() as c:
            source = self.source_for(c, clip.url)
            language = clip.lang or source["language"]
            added = self.articles.insert_entries(
                c, source_id=source["id"], feed_id=None, language=language, now=now,
                entries=[ParsedEntry(dedupe_key=key, url=clip.url, title=title, summary=summary, author=None,
                                     published_at=None)],
            )
            article_id = c.execute(
                "SELECT id FROM articles WHERE source_id = ? AND dedupe_key = ?", (source["id"], key)).fetchone()[0]
        self.fulltext.store_clip(article_id, text, now)
        log.info("Page sent by the user: %s (%d chars, %s)", clip.url, len(text), source["name"])
        return {"article_id": article_id, "source": source["name"], "title": title, "chars": len(text),
                "created": bool(added)}
