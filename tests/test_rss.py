import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from conftest import fixture_bytes
from worldsignal.collector.rss import (
    MAX_FEED_BYTES,
    FetchError,
    canonical_url,
    fetch_feed,
    make_client,
    parse_feed,
)


def test_parse_rss_turkish_entries():
    feed = parse_feed(fixture_bytes("rss_turkish.xml"))
    assert feed.title == "Beta Haber - Dünya"
    assert feed.language == "tr"
    titles = [e.title for e in feed.entries]
    # Empty title, missing link and the tracking-parameter duplicate are dropped.
    assert titles == [
        "IRAK'ta seçim sonuçları açıklandı",
        "İstanbul'da şiddetli yağış",
        "Tarihsiz haber",
        "Geleceğe tarihli haber (saat dilimi hatası)",
    ]
    first = feed.entries[0]
    assert first.summary == "Irak'ta yapılan genel seçimlerin sonuçları & katılım oranı açıklandı."
    assert first.dedupe_key == "https://beta.example/haber/irak-secim?id=7"
    assert first.published_at == datetime(2026, 9, 27, 6, 0, tzinfo=UTC)
    # +0300 is converted to UTC.
    assert feed.entries[1].published_at == datetime(2026, 9, 27, 2, 30, tzinfo=UTC)
    assert feed.entries[2].published_at is None


def test_parse_atom_uses_content_when_no_summary():
    feed = parse_feed(fixture_bytes("atom_basic.xml"))
    assert [e.title for e in feed.entries] == ["Leaders meet in Brussels", "Markets rally"]
    assert feed.entries[0].summary == "EU leaders gathered on Saturday."
    assert feed.entries[1].summary == "Stocks rose sharply."
    assert feed.language == "en"


def test_google_news_publisher_suffix_is_removed():
    feed = parse_feed(fixture_bytes("google_news.xml"))
    assert feed.entries[0].title == "Ceasefire talks resume in Cairo"
    assert feed.entries[1].title == "Reuters"


def test_html_page_is_not_a_feed():
    with pytest.raises(FetchError) as exc:
        parse_feed(fixture_bytes("not_a_feed.html"))
    assert exc.value.code == "not_a_feed"


def test_truncated_xml_still_yields_complete_items():
    feed = parse_feed(fixture_bytes("broken.xml"))
    assert [e.title for e in feed.entries][:1] == ["Only item"]


def test_very_long_title_is_truncated():
    long_title = "Ç" * 2000
    xml = f'<rss version="2.0"><channel><item><title>{long_title}</title><link>https://x.example/a</link></item></channel></rss>'
    feed = parse_feed(xml.encode())
    assert len(feed.entries[0].title) == 500
    assert feed.entries[0].title.endswith("…")


def test_canonical_url_strips_tracking_and_fragment():
    assert canonical_url("HTTPS://Example.COM/a?utm_source=x&b=1&fbclid=y#top") == "https://example.com/a?b=1"


def _fetch(handler, **kwargs):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await fetch_feed(client, "https://beta.example/rss", **kwargs)

    return asyncio.run(run())


def test_fetch_ok_returns_cache_headers():
    def handler(request):
        return httpx.Response(200, content=fixture_bytes("rss_turkish.xml"), headers={"ETag": '"v1"', "Last-Modified": "Sat, 27 Sep 2026 06:00:00 GMT"})

    result = _fetch(handler)
    assert not result.not_modified
    assert result.etag == '"v1"'
    assert len(result.feed.entries) == 4


def test_fetch_sends_conditional_headers_and_handles_304():
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(304)

    result = _fetch(handler, etag='"v1"', last_modified="Sat, 27 Sep 2026 06:00:00 GMT")
    assert result.not_modified and result.feed is None
    assert seen["if-none-match"] == '"v1"'
    assert seen["if-modified-since"] == "Sat, 27 Sep 2026 06:00:00 GMT"


def test_client_identifies_itself_honestly():
    async def run():
        async with make_client() as client:
            return client.headers["user-agent"]

    ua = asyncio.run(run())
    assert "WorldSignal/" in ua and "RSS reader" in ua


@pytest.mark.parametrize(("status", "code"), [(403, "http_403"), (404, "http_404"), (500, "http_500")])
def test_fetch_http_errors(status, code):
    with pytest.raises(FetchError) as exc:
        _fetch(lambda r: httpx.Response(status))
    assert exc.value.code == code


def test_fetch_timeout_and_network_errors():
    def timeout(request):
        raise httpx.ConnectTimeout("slow", request=request)

    def refused(request):
        raise httpx.ConnectError("no route", request=request)

    with pytest.raises(FetchError) as exc:
        _fetch(timeout)
    assert exc.value.code == "timeout"
    with pytest.raises(FetchError) as exc:
        _fetch(refused)
    assert exc.value.code == "network"


def test_fetch_rejects_oversized_body():
    big = b"<rss>" + b" " * (MAX_FEED_BYTES + 10)
    with pytest.raises(FetchError) as exc:
        _fetch(lambda r: httpx.Response(200, content=big))
    assert exc.value.code == "too_large"


def test_fetch_html_challenge_page_is_reported():
    with pytest.raises(FetchError) as exc:
        _fetch(lambda r: httpx.Response(200, content=fixture_bytes("not_a_feed.html")))
    assert exc.value.code == "not_a_feed"


def test_bing_news_links_point_to_the_publisher():
    xml = b"""<?xml version="1.0" encoding="utf-8"?><rss version="2.0" xmlns:News="https://www.bing.com:443/news/search?q=x&amp;format=rss"><channel><title>site:reuters.com - Bing</title>
<item><title>China, US agree tariff cuts</title><link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;aid=&amp;tid=abc&amp;url=https%3a%2f%2fwww.reuters.com%2fbusiness%2fchina-us-2026-09-28%2f&amp;c=316&amp;mkt=tr-tr</link><description>China said on Monday...</description><pubDate>Mon, 28 Sep 2026 00:45:00 GMT</pubDate><News:Source>Reuters</News:Source></item>
<item><title>Second</title><link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=https%3a%2f%2fwww.reuters.com%2fworld%2fsecond%2f&amp;c=2</link><pubDate>Mon, 28 Sep 2026 00:40:00 GMT</pubDate></item>
<item><title>Broken wrapper</title><link>http://www.bing.com/news/apiclick.aspx?ref=FexRss&amp;url=javascript%3aalert(1)</link></item>
</channel></rss>"""
    feed = parse_feed(xml)
    assert [e.url for e in feed.entries[:2]] == ["https://www.reuters.com/business/china-us-2026-09-28/",
                                                "https://www.reuters.com/world/second/"]
    assert feed.entries[0].dedupe_key == "https://www.reuters.com/business/china-us-2026-09-28/"
    assert feed.entries[0].summary == "China said on Monday..."
    # A wrapper without a usable address stays as it is (still a valid http link).
    assert feed.entries[2].url.startswith("http://www.bing.com/news/apiclick.aspx")
