import asyncio
from datetime import UTC, datetime, timedelta

import httpx

from conftest import MINI_CATALOG, fixture_bytes, mock_client_factory
from worldsignal.collector.service import Collector

START = datetime(2026, 9, 27, 8, 0, tzinfo=UTC)


class Clock:
    def __init__(self):
        self.now = START

    def __call__(self):
        return self.now

    def advance(self, minutes):
        self.now += timedelta(minutes=minutes)


def make(db, sources, articles, handler):
    sources.seed_from_catalog(MINI_CATALOG)
    clock = Clock()
    collector = Collector(db, sources, articles, client_factory=mock_client_factory(handler), clock=clock)
    return collector, clock


def cycle(collector):
    async def run():
        async with collector.client_factory() as client:
            return await collector.run_cycle(client)

    return asyncio.run(run())


def feed_row(db, url):
    return dict(db.conn.execute("SELECT * FROM feeds WHERE url = ?", (url,)).fetchone())


def ok_handler(request):
    if "alpha" in request.url.host:
        return httpx.Response(200, content=fixture_bytes("atom_basic.xml"), headers={"ETag": '"a1"'})
    return httpx.Response(200, content=fixture_bytes("rss_turkish.xml"))


def test_cycle_stores_articles_and_schedules_next(db, sources, articles):
    collector, _ = make(db, sources, articles, ok_handler)
    notified = []
    collector.on_new_articles.append(lambda: notified.append(1))
    assert cycle(collector) == 2 + 4
    assert notified == [1]  # listeners (story and AI workers) are woken once per cycle with new articles
    alpha = feed_row(db, "https://alpha.example/rss")
    assert alpha["last_status"] == "ok" and alpha["etag"] == '"a1"' and alpha["last_new_count"] == 2
    assert alpha["next_fetch_at"] > "2026-09-27T08:14:59Z"
    # Unverified/disabled catalog source is never fetched.
    assert feed_row(db, "https://gamma.example/rss")["last_status"] == "pending"
    # Nothing is due right away.
    assert cycle(collector) == 0
    assert notified == [1]


def test_second_fetch_uses_etag_and_dedupes(db, sources, articles):
    seen_etags = []

    def handler(request):
        seen_etags.append(request.headers.get("if-none-match"))
        if "alpha" in request.url.host and request.headers.get("if-none-match") == '"a1"':
            return httpx.Response(304)
        return ok_handler(request)

    collector, clock = make(db, sources, articles, handler)
    cycle(collector)
    clock.advance(20)
    assert cycle(collector) == 0
    assert '"a1"' in seen_etags
    assert feed_row(db, "https://alpha.example/rss")["last_status"] == "not_modified"
    assert db.conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 6


def test_failing_feed_backs_off_and_reports_error(db, sources, articles):
    def handler(request):
        if "alpha" in request.url.host:
            return httpx.Response(404)
        return ok_handler(request)

    collector, clock = make(db, sources, articles, handler)
    cycle(collector)
    row = feed_row(db, "https://alpha.example/rss")
    assert row["last_status"] == "error" and row["last_error_code"] == "http_404"
    assert row["consecutive_failures"] == 1
    first_delay = datetime.strptime(row["next_fetch_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) - clock.now

    clock.now = datetime.strptime(row["next_fetch_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    cycle(collector)
    row = feed_row(db, "https://alpha.example/rss")
    assert row["consecutive_failures"] == 2
    second_delay = datetime.strptime(row["next_fetch_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) - clock.now
    assert second_delay > first_delay
    status = {s["slug"]: s["status"] for s in sources.list_sources()}
    assert status["alpha"] == "error" and status["beta"] == "ok"


def test_recovery_resets_failure_count(db, sources, articles):
    state = {"fail": True}

    def handler(request):
        if "alpha" in request.url.host and state["fail"]:
            return httpx.Response(500)
        return ok_handler(request)

    collector, clock = make(db, sources, articles, handler)
    cycle(collector)
    state["fail"] = False
    collector.request_run()
    cycle(collector)
    row = feed_row(db, "https://alpha.example/rss")
    assert row["last_status"] == "ok" and row["consecutive_failures"] == 0 and row["last_error_code"] is None


def test_offline_does_not_penalise_feeds(db, sources, articles):
    sources.seed_from_catalog(MINI_CATALOG)
    sources.create_source({"name": "Third"}, "https://third.example/rss")

    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    collector, clock = make(db, sources, articles, handler)
    cycle(collector)
    assert collector.status()["offline"] is True
    row = feed_row(db, "https://alpha.example/rss")
    assert row["consecutive_failures"] == 0 and row["last_error_code"] == "network"
    assert row["next_fetch_at"] == "2026-09-27T08:02:00Z"


def test_unexpected_exception_does_not_break_cycle(db, sources, articles, monkeypatch):
    import worldsignal.collector.service as service

    real = service.fetch_feed

    async def flaky(client, url, *a, **k):
        if "alpha" in url:
            raise RuntimeError("parser bug")
        return await real(client, url, *a, **k)

    monkeypatch.setattr(service, "fetch_feed", flaky)
    collector, _ = make(db, sources, articles, ok_handler)
    assert cycle(collector) == 4
    assert feed_row(db, "https://alpha.example/rss")["last_error_code"] == "internal"


def test_run_forever_can_be_cancelled(db, sources, articles):
    collector, _ = make(db, sources, articles, ok_handler)

    async def run():
        task = asyncio.create_task(collector.run_forever())
        for _ in range(100):
            await asyncio.sleep(0.02)
            if collector.status()["last_cycle_at"]:
                break
        assert collector.status()["running"]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(run())
    assert collector.status()["running"] is False
    assert collector.status()["last_cycle_new"] == 6


def test_last_cycle_time_survives_restart(db, sources, articles):
    collector, clock = make(db, sources, articles, ok_handler)
    cycle(collector)
    # Same (frozen) clock: nothing is due, so the restarted collector does not fetch again.
    fresh = Collector(db, sources, articles, client_factory=mock_client_factory(ok_handler), clock=clock)

    async def start_and_stop():
        task = asyncio.create_task(fresh.run_forever())
        for _ in range(50):
            await asyncio.sleep(0.02)
            if fresh.status()["running"]:
                break
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    asyncio.run(start_and_stop())
    assert fresh.status()["last_cycle_at"] == "2026-09-27T08:00:00Z"
