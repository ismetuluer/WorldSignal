"""News sitemaps as a feed, robots.txt, and finding a site's feeds.

Many news sites without RSS publish a *news sitemap* for search engines (``<news:news>`` with headline, date and
language for every recent article). It carries what an RSS item does, so World Signal reads it as a feed. Sitemaps
are meant for automated readers, but only where the site's robots.txt allows it; that is checked every time (cached
for a day per site). Plain sitemaps without headlines are refused rather than guessing titles from addresses.

``discover`` helps the "Add source" dialog: for a web page it lists the RSS/Atom links the page declares and the
news sitemaps its robots.txt declares.
"""

from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..textnorm import strip_html

ROBOTS_AGENT = "WorldSignal"  # the product token robots.txt rules are matched against
ROBOTS_TTL = 24 * 3600
MAX_CHILD_SITEMAPS = 2  # of a sitemap index: the news ones, else the newest
MAX_SUGGESTIONS = 8

_SM = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
_NEWS = "{http://www.google.com/schemas/sitemap-news/0.9}"


def _is_news(url: str) -> bool:
    """A news sitemap by its name ("sitemap-news.xml", "/news/sitemap.xml"); the site's own name does not count."""
    return "news" in urlsplit(url).path.lower()


def looks_like_sitemap(body: bytes) -> bool:
    head = body[:4096].lower()
    return b"<urlset" in head or b"<sitemapindex" in head


@dataclass
class SitemapItem:
    url: str
    title: str
    published_at: datetime | None
    language: str | None


@dataclass
class Sitemap:
    items: list[SitemapItem] = field(default_factory=list)
    children: list[str] = field(default_factory=list)  # a sitemap index: the sitemaps to read next
    has_urls: bool = False  # a plain sitemap (addresses without headlines)


def _time(text: str | None) -> datetime | None:
    if not text:
        return None
    value = text.strip().replace("Z", "+00:00")
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        try:
            stamp = datetime.fromisoformat(value[:10])
        except ValueError:
            return None
    return (stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)).astimezone(UTC)


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def parse_sitemap(body: bytes) -> Sitemap:
    """Raises ValueError when the XML is broken."""
    root = ET.fromstring(body)
    out = Sitemap()
    if root.tag == f"{_SM}sitemapindex":
        children = [(_text(s.find(f"{_SM}loc")), _time(_text(s.find(f"{_SM}lastmod")))) for s in root.findall(f"{_SM}sitemap")]
        children = [c for c in children if c[0].startswith(("http://", "https://"))]
        news = [c for c in children if _is_news(c[0])]
        newest = sorted(news or children, key=lambda c: c[1] or datetime.min.replace(tzinfo=UTC), reverse=True)
        out.children = [url for url, _ in newest[:MAX_CHILD_SITEMAPS]]
        return out
    for u in root.findall(f"{_SM}url"):
        loc = _text(u.find(f"{_SM}loc"))
        if not loc.startswith(("http://", "https://")):
            continue
        out.has_urls = True
        news = u.find(f"{_NEWS}news")
        title = strip_html(_text(news.find(f"{_NEWS}title"))) if news is not None else ""
        if not title:
            continue
        out.items.append(SitemapItem(
            url=loc,
            title=title,
            published_at=_time(_text(news.find(f"{_NEWS}publication_date"))),
            language=(_text(news.find(f"{_NEWS}publication/{_NEWS}language")).split("-")[0].lower() or None),
        ))
    return out


class Robots:
    """robots.txt per site, cached for a day. RFC 9309: a missing file (4xx) allows everything; a server error or
    no answer is treated as "not allowed" until the next try."""

    def __init__(self, clock=time.monotonic) -> None:
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}
        self._clock = clock

    async def parser(self, client: httpx.AsyncClient, url: str) -> RobotFileParser | None:
        """None = robots.txt could not be read (treat as disallowed)."""
        parts = urlsplit(url)
        site = f"{parts.scheme}://{parts.netloc}"
        hit = self._cache.get(site)
        if hit is not None and self._clock() - hit[0] < ROBOTS_TTL:
            return hit[1]
        rp: RobotFileParser | None = RobotFileParser()
        try:
            resp = await client.get(f"{site}/robots.txt")
            if resp.status_code >= 500:
                rp = None
            elif resp.status_code >= 400:
                rp.parse([])  # no robots.txt: everything is allowed
            else:
                rp.parse(resp.text.splitlines())
        except httpx.HTTPError:
            rp = None
        self._cache[site] = (self._clock(), rp)
        return rp

    async def allows(self, client: httpx.AsyncClient, url: str) -> bool:
        rp = await self.parser(client, url)
        return rp is not None and rp.can_fetch(ROBOTS_AGENT, url)


ROBOTS = Robots()


class _FeedLinks(HTMLParser):
    """<link rel="alternate" type="application/rss+xml" href="…" title="…"> in a page's head."""

    TYPES = {"application/rss+xml", "application/atom+xml", "application/feed+json"}

    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if "alternate" in a.get("rel", "").lower().split() and a.get("type", "").lower() in self.TYPES and a.get("href"):
            self.links.append((a["href"], a.get("title", "")))


async def discover(client: httpx.AsyncClient, page_url: str, html: str | None) -> list[dict[str, str]]:
    """Feeds a site offers: RSS/Atom links in the page, then news sitemaps from robots.txt that it allows."""
    found: list[dict[str, str]] = []
    if html:
        parser = _FeedLinks()
        parser.feed(html[:500_000])  # html.parser is lenient: broken markup yields fewer links, not an error
        for href, title in parser.links:
            found.append({"url": urljoin(page_url, href), "kind": "rss", "title": strip_html(title)})
    rp = await ROBOTS.parser(client, page_url)
    for sitemap in (rp.site_maps() or []) if rp is not None else []:
        if _is_news(sitemap) and rp.can_fetch(ROBOTS_AGENT, sitemap):
            found.append({"url": sitemap, "kind": "sitemap", "title": ""})
    seen: set[str] = set()
    unique = [f for f in found if not (f["url"] in seen or seen.add(f["url"]))]
    return [f for f in unique if f["url"].startswith(("http://", "https://"))][:MAX_SUGGESTIONS]
