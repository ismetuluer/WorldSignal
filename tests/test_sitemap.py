"""News sitemaps read as feeds, robots.txt, and finding a site's feeds (collector/sitemap.py)."""

import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from worldsignal.collector.rss import FetchError, fetch_feed
from worldsignal.collector.sitemap import Robots, discover, looks_like_sitemap, parse_sitemap

NEWS = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
  <url><loc>https://news.example/world/talks-resume?utm_source=x</loc>
    <news:news><news:publication><news:name>News Example</news:name><news:language>tr</news:language></news:publication>
      <news:publication_date>2026-09-28T09:30:00+03:00</news:publication_date>
      <news:title>Ankara'da m\xc3\xbczakereler yeniden ba\xc5\x9flad\xc4\xb1</news:title></news:news></url>
  <url><loc>https://news.example/world/talks-resume</loc>
    <news:news><news:publication_date>2026-09-28</news:publication_date><news:title>Duplicate</news:title></news:news></url>
  <url><loc>https://news.example/about</loc></url>
  <url><loc>https://news.example/economy/rates</loc>
    <news:news><news:publication_date>2026-09-28</news:publication_date><news:title>Faiz &amp; enflasyon</news:title></news:news></url>
</urlset>"""

PLAIN = b"""<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://plain.example/a</loc><lastmod>2026-09-28</lastmod></url></urlset>"""

INDEX = b"""<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <sitemap><loc>https://news.example/sitemap-pages.xml</loc><lastmod>2026-09-28T10:00:00Z</lastmod></sitemap>
  <sitemap><loc>https://news.example/sitemap-news.xml</loc><lastmod>2026-09-27T10:00:00Z</lastmod></sitemap>
</sitemapindex>"""

PAGE = b"""<html><head><title>News</title>
<link rel="alternate" type="application/rss+xml" title="Son dakika" href="/rss/latest">
<link rel="stylesheet" href="/a.css"><link rel="alternate" hreflang="en" href="/en/">
</head><body>x</body></html>"""


def run(coro):
    return asyncio.run(coro)


def make_client(robots: dict[str, httpx.Response], pages: dict[str, bytes], seen: list[str] | None = None):
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if seen is not None:
            seen.append(url)
        if request.url.path == "/robots.txt":
            return robots.get(request.url.host, httpx.Response(404))
        if url in pages:
            return httpx.Response(200, content=pages[url])
        return httpx.Response(404)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_news_sitemap_is_parsed():
    assert looks_like_sitemap(NEWS) and looks_like_sitemap(INDEX) and not looks_like_sitemap(PAGE)
    sm = parse_sitemap(NEWS)
    assert [i.title for i in sm.items] == ["Ankara'da müzakereler yeniden başladı", "Duplicate", "Faiz & enflasyon"]
    first = sm.items[0]
    assert first.published_at == datetime(2026, 9, 28, 6, 30, tzinfo=UTC) and first.language == "tr"
    assert sm.items[2].published_at == datetime(2026, 9, 28, tzinfo=UTC)
    assert parse_sitemap(PLAIN).items == [] and parse_sitemap(PLAIN).has_urls
    # An index: the news sitemap first, even though another one is newer.
    assert parse_sitemap(INDEX).children[0] == "https://news.example/sitemap-news.xml"


def test_a_news_sitemap_works_as_a_feed_when_robots_allow_it():
    allow = {"news.example": httpx.Response(200, text="User-agent: *\nDisallow: /private/\n")}
    client = make_client(allow, {"https://news.example/sitemap-news.xml": NEWS})
    result = run(fetch_feed(client, "https://news.example/sitemap-news.xml", robots=Robots()))
    feed = result.feed
    assert feed.language == "tr" and [e.title for e in feed.entries] == [
        "Ankara'da müzakereler yeniden başladı", "Faiz & enflasyon"]  # tracking parameters do not make duplicates
    assert feed.entries[0].url == "https://news.example/world/talks-resume?utm_source=x"


@pytest.mark.parametrize("robots_txt", [
    "User-agent: *\nDisallow: /",
    "User-agent: WorldSignal\nDisallow: /sitemap-news.xml\n\nUser-agent: *\nAllow: /",
])
def test_robots_txt_is_obeyed(robots_txt):
    client = make_client({"news.example": httpx.Response(200, text=robots_txt)},
                         {"https://news.example/sitemap-news.xml": NEWS})
    with pytest.raises(FetchError) as err:
        run(fetch_feed(client, "https://news.example/sitemap-news.xml", robots=Robots()))
    assert err.value.code == "robots_disallow"


def test_unreadable_robots_txt_means_not_allowed_but_a_missing_one_allows():
    pages = {"https://news.example/sitemap-news.xml": NEWS}
    with pytest.raises(FetchError) as err:
        run(fetch_feed(make_client({"news.example": httpx.Response(503)}, pages), "https://news.example/sitemap-news.xml",
                       robots=Robots()))
    assert err.value.code == "robots_disallow"
    result = run(fetch_feed(make_client({}, pages), "https://news.example/sitemap-news.xml", robots=Robots()))
    assert len(result.feed.entries) == 2


def test_robots_txt_is_asked_once_a_day():
    seen: list[str] = []
    now = [0.0]
    robots = Robots(clock=lambda: now[0])
    client = make_client({}, {"https://news.example/sitemap-news.xml": NEWS}, seen)
    for _ in range(3):
        run(fetch_feed(client, "https://news.example/sitemap-news.xml", robots=robots))
    assert seen.count("https://news.example/robots.txt") == 1
    now[0] = 25 * 3600
    run(fetch_feed(client, "https://news.example/sitemap-news.xml", robots=robots))
    assert seen.count("https://news.example/robots.txt") == 2


def test_a_sitemap_index_reads_its_news_sitemap():
    pages = {"https://news.example/sitemap.xml": INDEX, "https://news.example/sitemap-news.xml": NEWS,
             "https://news.example/sitemap-pages.xml": PLAIN}
    result = run(fetch_feed(make_client({}, pages), "https://news.example/sitemap.xml", robots=Robots()))
    assert len(result.feed.entries) == 2


def test_a_sitemap_without_headlines_is_refused():
    client = make_client({}, {"https://plain.example/sitemap.xml": PLAIN})
    with pytest.raises(FetchError) as err:
        run(fetch_feed(client, "https://plain.example/sitemap.xml", robots=Robots()))
    assert err.value.code == "sitemap_no_titles"


def test_a_broken_sitemap_is_not_a_feed():
    client = make_client({}, {"https://news.example/sitemap-news.xml": b"<urlset><url><loc>x"})
    with pytest.raises(FetchError) as err:
        run(fetch_feed(client, "https://news.example/sitemap-news.xml", robots=Robots()))
    assert err.value.code == "not_a_feed"


def test_discover_lists_page_feeds_and_allowed_news_sitemaps(monkeypatch):
    import worldsignal.collector.sitemap as sm

    monkeypatch.setattr(sm, "ROBOTS", Robots())
    robots_txt = ("User-agent: *\nDisallow: /hidden/\n"
                  "Sitemap: https://news.example/sitemap-news.xml\n"
                  "Sitemap: https://news.example/sitemap-pages.xml\n"
                  "Sitemap: https://news.example/hidden/news.xml\n")
    client = make_client({"news.example": httpx.Response(200, text=robots_txt)}, {})
    found = run(discover(client, "https://news.example/", PAGE.decode()))
    assert found == [
        {"url": "https://news.example/rss/latest", "kind": "rss", "title": "Son dakika"},
        {"url": "https://news.example/sitemap-news.xml", "kind": "sitemap", "title": ""},
    ]
