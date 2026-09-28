"""Downloading and parsing RSS/Atom feeds.

The network layer (httpx) and the parser (feedparser) are kept separate so the
parser can be tested with fixture files and the fetcher with a mock transport.
Conditional GET (ETag / Last-Modified) avoids re-downloading unchanged feeds.
"""

from __future__ import annotations

import calendar
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import feedparser
import httpx

from .. import __version__
from ..textnorm import strip_html

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
        link = unwrap_aggregator_link((e.get("link") or "").strip())
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
                published_at=_entry_time(e),
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


async def fetch_feed(
    client: httpx.AsyncClient,
    url: str,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FetchResult:
    headers = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified

    try:
        async with client.stream("GET", url, headers=headers) as resp:
            if resp.status_code == 304:
                return FetchResult(True, None, etag, last_modified, str(resp.url))
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
            body = b"".join(chunks)
            final_url = str(resp.url)
            new_etag = resp.headers.get("etag")
            new_last_modified = resp.headers.get("last-modified")
    except FetchError:
        raise
    except httpx.TimeoutException as exc:
        raise FetchError("timeout", repr(exc)) from exc
    except httpx.TooManyRedirects as exc:
        raise FetchError("redirect_loop", repr(exc)) from exc
    except (httpx.ConnectError, httpx.NetworkError, httpx.ProtocolError, httpx.ProxyError) as exc:
        raise FetchError("network", repr(exc)) from exc
    except httpx.HTTPError as exc:
        raise FetchError("network", repr(exc)) from exc

    feed = parse_feed(body, final_url)
    return FetchResult(False, feed, new_etag, new_last_modified, final_url)
