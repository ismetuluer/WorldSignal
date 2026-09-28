"""Downloading and parsing RSS/Atom feeds (and news sitemaps, see sitemap.py).

The network layer (httpx) and the parser (feedparser) are kept separate so the
parser can be tested with fixture files and the fetcher with a mock transport.
Conditional GET (ETag / Last-Modified) avoids re-downloading unchanged feeds.
"""

from __future__ import annotations

import calendar
import logging
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx

from .. import __version__
from ..textnorm import strip_html
from .sitemap import ROBOTS, Robots, Sitemap, looks_like_sitemap, parse_sitemap

log = logging.getLogger(__name__)

USER_AGENT = f"Mozilla/5.0 (compatible; WorldSignal/{__version__}; RSS reader)"
MAX_FEED_BYTES = 10 * 1024 * 1024
DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
MAX_SUMMARY_CHARS = 2000
MAX_TITLE_CHARS = 500

_TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "ocid", "cmpid", "at_medium", "at_campaign")


class FetchError(Exception):
    """A feed could not be fetched or parsed. ``code`` is shown (translated) in the UI."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


@dataclass
class ParsedEntry:
    dedupe_key: str
    url: str
    title: str
    summary: str
    author: str | None
    published_at: datetime | None


@dataclass
class ParsedFeed:
    title: str | None
    language: str | None
    entries: list[ParsedEntry] = field(default_factory=list)


@dataclass
class FetchResult:
    not_modified: bool
    feed: ParsedFeed | None
    etag: str | None
    last_modified: str | None
    final_url: str


def canonical_url(url: str) -> str:
    """Remove tracking parameters and fragments so the same story dedupes."""
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip()
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith(_TRACKING_PARAMS)
    ]
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, urlencode(query), ""))


def unwrap_aggregator_link(url: str) -> str:
    """Bing News feeds wrap every article as bing.com/news/apiclick.aspx?url=<publisher URL>; keep the publisher URL."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return url
    if parts.netloc.lower().endswith("bing.com") and parts.path.lower().endswith("/apiclick.aspx"):
        real = dict(parse_qsl(parts.query)).get("url", "")
        if real.startswith(("http://", "https://")):
            return real
    return url


def bing_time_to_utc(stamp: datetime, now: datetime | None = None) -> datetime:
    """Bing News feeds label US Pacific wall-clock time as "GMT" (measured 2026-09-28: every Bing time was
    exactly 7 h behind the publisher's own feed). Read the value as Pacific time: UTC-7 in daylight
    saving time (second Sunday of March to first Sunday of November, 02:00), UTC-8 otherwise. If Bing ever
    fixes its feed, the corrected time would lie in the future; then the value is kept as it is."""
    wall = stamp.replace(tzinfo=None)
    march = datetime(wall.year, 3, 8)
    november = datetime(wall.year, 11, 1)
    dst_start = march + timedelta(days=(6 - march.weekday()) % 7, hours=2)
    dst_end = november + timedelta(days=(6 - november.weekday()) % 7, hours=2)
    offset = 7 if dst_start <= wall < dst_end else 8
    corrected = (wall + timedelta(hours=offset)).replace(tzinfo=UTC)
    if corrected > (now or datetime.now(UTC)) + timedelta(minutes=10):
        return stamp
    return corrected


def _entry_time(entry: feedparser.FeedParserDict) -> datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        value = entry.get(key)
        if value:
            try:
                # feedparser normalises to UTC struct_time.
                return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)
            except (OverflowError, ValueError, TypeError):
                continue
    return None


def _entry_summary(entry: feedparser.FeedParserDict) -> str:
    text = entry.get("summary") or ""
    if not text and entry.get("content"):
        text = entry["content"][0].get("value", "")
    text = strip_html(text)
    if len(text) > MAX_SUMMARY_CHARS:
        text = text[: MAX_SUMMARY_CHARS - 1].rstrip() + "…"
    return text


def _strip_source_suffix(title: str, entry: feedparser.FeedParserDict) -> str:
    """Aggregator feeds (Google News) append " - Publisher" to every title."""
    source = entry.get("source") or {}
    publisher = (source.get("title") or "").strip()
    suffix = f" - {publisher}"
    if publisher and title.endswith(suffix) and len(title) > len(suffix):
        return title[: -len(suffix)].rstrip()
    return title


def parse_feed(content: bytes, base_url: str = "") -> ParsedFeed:
    """Parse feed bytes. Raises FetchError('not_a_feed') for HTML pages etc."""
    parsed = feedparser.parse(content, response_headers={"content-location": base_url})
    if not parsed.get("version") and not parsed.entries:
        reason = str(parsed.get("bozo_exception", "")) if parsed.get("bozo") else ""
        raise FetchError("not_a_feed", reason)

    entries: list[ParsedEntry] = []
    seen: set[str] = set()
    for e in parsed.entries:
        title = _strip_source_suffix(strip_html(e.get("title")), e)
        raw_link = (e.get("link") or "").strip()
        link = unwrap_aggregator_link(raw_link)
        from_bing = link != raw_link
        guid = (e.get("id") or "").strip()
        if not title or not (link or guid):
            continue
        url = link or guid
        if not url.startswith(("http://", "https://")):
            continue
        key = canonical_url(link) if link else guid
        if key in seen:
            continue
        seen.add(key)
        if len(title) > MAX_TITLE_CHARS:
            title = title[: MAX_TITLE_CHARS - 1].rstrip() + "…"
        entries.append(
            ParsedEntry(
                dedupe_key=key,
                url=url,
                title=title,
                summary=_entry_summary(e),
                author=strip_html(e.get("author")) or None,
                published_at=bing_time_to_utc(t) if from_bing and (t := _entry_time(e)) else _entry_time(e),
            )
        )

    feed_meta = parsed.get("feed", {})
    language = (feed_meta.get("language") or "").split("-")[0].lower() or None
    return ParsedFeed(title=strip_html(feed_meta.get("title")) or None, language=language, entries=entries)


def make_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml;q=0.9, text/xml;q=0.9, */*;q=0.5",
        },
        timeout=DEFAULT_TIMEOUT,
        follow_redirects=True,
        http2=False,
    )


async def download(
    client: httpx.AsyncClient, url: str, headers: dict[str, str] | None = None
) -> tuple[int, bytes, str, str | None, str | None]:
    """(status, body, final URL, ETag, Last-Modified). Errors become FetchError; 304 comes back with an empty body."""
    try:
        async with client.stream("GET", url, headers=headers or {}) as resp:
            if resp.status_code == 304:
                return 304, b"", str(resp.url), None, None
            if resp.status_code >= 400:
                raise FetchError(f"http_{resp.status_code}", resp.reason_phrase)
            declared = resp.headers.get("content-length")
            if declared and declared.isdigit() and int(declared) > MAX_FEED_BYTES:
                raise FetchError("too_large", declared)
            chunks: list[bytes] = []
            size = 0
            async for chunk in resp.aiter_bytes():
                size += len(chunk)
                if size > MAX_FEED_BYTES:
                    raise FetchError("too_large", str(size))
                chunks.append(chunk)
            return (resp.status_code, b"".join(chunks), str(resp.url), resp.headers.get("etag"),
                    resp.headers.get("last-modified"))
    except FetchError:
        raise
    except httpx.TimeoutException as exc:
        raise FetchError("timeout", repr(exc)) from exc
    except httpx.TooManyRedirects as exc:
        raise FetchError("redirect_loop", repr(exc)) from exc
    except httpx.HTTPError as exc:
        raise FetchError("network", repr(exc)) from exc


async def fetch_feed(
    client: httpx.AsyncClient,
    url: str,
    etag: str | None = None,
    last_modified: str | None = None,
    robots: Robots | None = None,
) -> FetchResult:
    """Download and parse an RSS/Atom feed, or a news sitemap (sitemap.py) where robots.txt allows it."""
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    status, body, final_url, new_etag, new_last_modified = await download(client, url, headers)
    if status == 304:
        return FetchResult(True, None, etag, last_modified, final_url)
    if looks_like_sitemap(body):
        feed = await _sitemap_feed(client, body, final_url, robots or ROBOTS)
    else:
        feed = parse_feed(body, final_url)
    return FetchResult(False, feed, new_etag, new_last_modified, final_url)


def _read_sitemap(body: bytes) -> Sitemap:
    try:
        return parse_sitemap(body)
    except (ValueError, SyntaxError) as exc:  # ElementTree's ParseError is a SyntaxError
        raise FetchError("not_a_feed", f"broken sitemap: {exc}") from exc


async def _sitemap_feed(client: httpx.AsyncClient, body: bytes, url: str, robots: Robots) -> ParsedFeed:
    if not await robots.allows(client, url):
        raise FetchError("robots_disallow", url)
    first = _read_sitemap(body)
    items, plain = list(first.items), first.has_urls
    for child in first.children:  # a sitemap index: read its news (or newest) sitemaps
        if not await robots.allows(client, child):
            continue
        _, child_body, _, _, _ = await download(client, child)
        sub = _read_sitemap(child_body)
        items += sub.items
        plain = plain or sub.has_urls
    if not items:
        # Addresses without headlines would need every article page opened: not done.
        raise FetchError("sitemap_no_titles" if plain else "empty_feed", url)
    entries: list[ParsedEntry] = []
    seen: set[str] = set()
    for item in items:
        key = canonical_url(item.url)
        if key in seen:
            continue
        seen.add(key)
        title = item.title if len(item.title) <= MAX_TITLE_CHARS else item.title[: MAX_TITLE_CHARS - 1].rstrip() + "…"
        entries.append(ParsedEntry(dedupe_key=key, url=item.url, title=title, summary="", author=None,
                                   published_at=item.published_at))
    languages = Counter(i.language for i in items if i.language)
    return ParsedFeed(title=None, language=languages.most_common(1)[0][0] if languages else None, entries=entries)
