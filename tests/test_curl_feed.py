"""Feeds whose publisher refuses Python's HTTP client are fetched with curl.exe (rss.CURL_HOSTS)."""

from __future__ import annotations

import asyncio

import httpx
import pytest

from worldsignal.collector import rss

RSS = b"""<?xml version="1.0"?><rss version="2.0"><channel><title>T</title>
<item><title>Headline</title><link>https://www.independent.co.uk/a</link><guid>1</guid></item></channel></rss>"""
URL = "https://www.independent.co.uk/news/world/rss"


def curl_says(status: int, body: bytes = RSS, final: str = URL):
    async def fake(url):
        return body + rss._CURL_MARK + f"{status}\n{final}".encode()
    return fake


def run(coro):
    return asyncio.run(coro)


def refusing_client():
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(429)))


def test_a_listed_host_is_fetched_with_curl_and_parsed(monkeypatch):
    monkeypatch.setattr(rss, "_run_curl", curl_says(200))
    result = run(rss.fetch_feed(refusing_client(), URL))  # httpx would have answered 429
    assert [e.title for e in result.feed.entries] == ["Headline"]


def test_curl_is_refused_too_means_failed_and_nothing_else_is_tried(monkeypatch):
    monkeypatch.setattr(rss, "_run_curl", curl_says(429, b""))
    with pytest.raises(rss.FetchError) as err:
        run(rss.fetch_feed(refusing_client(), URL))
    assert err.value.code == "http_429"


def test_curl_missing_is_a_visible_error(monkeypatch):
    monkeypatch.setattr(rss, "_curl_path", lambda: None)
    with pytest.raises(rss.FetchError) as err:
        run(rss.fetch_feed(refusing_client(), URL))
    assert err.value.code == "network" and "curl_missing" in err.value.detail


def test_other_hosts_still_use_httpx(monkeypatch):
    async def boom(url):
        raise AssertionError("curl must not be used")
    monkeypatch.setattr(rss, "_run_curl", boom)
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=RSS)))
    assert run(rss.fetch_feed(client, "https://other.example/rss")).feed.entries[0].title == "Headline"


def test_garbled_curl_output_is_an_error(monkeypatch):
    async def junk(url):
        return b"no mark here"
    monkeypatch.setattr(rss, "_run_curl", junk)
    with pytest.raises(rss.FetchError):
        run(rss.fetch_feed(refusing_client(), URL))


@pytest.mark.skipif(rss._curl_path() is None, reason="curl.exe not available")
def test_the_real_curl_against_a_local_server():
    import http.server
    import threading

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/gone":
                self.send_response(429)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/rss+xml")
            self.end_headers()
            self.wfile.write(RSS)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_port}"
    try:
        status, body, final, _, _ = run(rss.download_with_curl(base + "/rss"))
        assert status == 200 and body == RSS and final == base + "/rss"
        with pytest.raises(rss.FetchError) as err:
            run(rss.download_with_curl(base + "/gone"))
        assert err.value.code == "http_429"
    finally:
        server.shutdown()
