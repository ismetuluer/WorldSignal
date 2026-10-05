from datetime import UTC, datetime

import httpx
import pytest
from fastapi.testclient import TestClient

from conftest import MINI_CATALOG, fixture_bytes
from worldsignal.api import app as app_module
from worldsignal.apikeys import SecretStore
from worldsignal.fulltext.bridge import ExtensionBridge
from worldsignal.api.app import AppContext, create_app
from worldsignal.collector.rss import ParsedEntry
from worldsignal.ai.worker import AiWorker
from worldsignal.collector.service import Collector
from worldsignal.repo.ai import AiRepository
from worldsignal.fulltext.worker import FullTextWorker
from worldsignal.repo.fulltext import FullTextRepository
from worldsignal.repo.history import HistoryRepository
from worldsignal.backup import BackupManager
from worldsignal.maintenance import Maintenance
from worldsignal.notify import Notifier
from worldsignal.repo.notebook import NotebookRepository
from worldsignal.repo.stories import StoryRepository
from worldsignal.stories.worker import StoryWorker
from worldsignal.home_sync import HomeSync

TOKEN = "test-token"
H = {"X-WorldSignal-Token": TOKEN}
TODAY = "2026-09-27"


@pytest.fixture
def ctx(db, data_paths, settings, sources, articles, home, tmp_path):
    sources.seed_from_catalog(MINI_CATALOG)
    ui = tmp_path / "ui"
    (ui / "assets").mkdir(parents=True)
    (ui / "index.html").write_text("<!doctype html><title>WS</title>", encoding="utf-8")
    (ui / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    return AppContext(
        db=db, paths=data_paths, token=TOKEN, settings=settings, sources=sources, articles=articles,
        collector=Collector(db, sources, articles), ai=AiRepository(db),
        ai_worker=AiWorker(AiRepository(db), settings), stories=StoryRepository(db),
        story_worker=StoryWorker(StoryRepository(db), settings),
        notebook=NotebookRepository(db, StoryRepository(db), today=lambda: TODAY),
        fulltext=FullTextRepository(db),
        fulltext_worker=FullTextWorker(FullTextRepository(db), settings),
        history=HistoryRepository(db, StoryRepository(db)), maintenance=Maintenance(HistoryRepository(db, StoryRepository(db)), settings),
        backups=BackupManager(db, data_paths.backups, data_paths.root), notifier=Notifier(db, settings),
        home=home, home_sync=HomeSync(home, articles, StoryRepository(db), settings),
        ui_dir=ui, run_collector=False,
        keys=SecretStore(tmp_path / "secrets.json", protect=bytes, unprotect=bytes),
        bridge=ExtensionBridge(FullTextRepository(db), settings, resting=lambda: False),
    )


@pytest.fixture
def client(ctx):
    with TestClient(create_app(ctx)) as c:
        yield c


def add_articles(ctx):
    beta = next(s for s in ctx.sources.list_sources() if s["slug"] == "beta")
    now = datetime.now(UTC)
    with ctx.db.transaction() as c:
        ctx.articles.insert_entries(c, source_id=beta["id"], feed_id=beta["feeds"][0]["id"], language="tr", now=now, entries=[
            ParsedEntry(f"k{i}", f"https://beta.example/{i}", f"IRAK haberi {i}", "özet", None, now) for i in range(5)
        ])


def test_health_is_public_but_everything_else_needs_token(client):
    assert client.get("/api/health").json()["ok"] is True
    for path in ("/api/status", "/api/sources", "/api/articles", "/api/settings", "/api/meta"):
        r = client.get(path)
        assert r.status_code == 401 and r.json()["detail"]["code"] == "unauthorized"
        assert client.get(path, headers={"X-WorldSignal-Token": "wrong"}).status_code == 401
        assert client.get(path, headers=H).status_code == 200


def test_unknown_api_route_is_json_404(client):
    r = client.get("/api/nope", headers=H)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "not_found"


def test_ui_is_served_with_spa_fallback(client):
    assert "WS" in client.get("/").text
    assert "WS" in client.get("/some/deep/link").text
    assert client.get("/assets/app.js").text == "console.log(1)"
    # Path traversal must not escape the UI directory.
    assert "WS" in client.get("/..%2F..%2Fpyproject.toml").text


def test_settings_patch_validates(client):
    r = client.patch("/api/settings", headers=H, json={"ui.language": "en", "ui.theme": "dark"})
    assert r.status_code == 200 and r.json()["ui.language"] == "en"
    assert client.patch("/api/settings", headers=H, json={"ui.language": "xx"}).status_code == 422
    assert client.patch("/api/settings", headers=H, json={"ui.theme": "pink"}).status_code == 422
    assert client.patch("/api/settings", headers=H, json={"nope": 1}).status_code == 422
    assert client.patch("/api/settings", headers=H, json={"feed.window_hours": 0}).status_code == 422
    assert client.get("/api/settings", headers=H).json()["home.enabled"] is True
    assert client.patch("/api/settings", headers=H, json={"home.enabled": False}).json()["home.enabled"] is False
    assert client.patch("/api/settings", headers=H, json={"home.enabled": "maybe"}).status_code == 422


def test_home_country_can_be_changed(client, ctx):
    add_articles(ctx)
    related = lambda: client.get("/api/articles?turkey=true", headers=H).json()["total"]  # noqa: E731
    assert related() == 0  # rated only once the AI has read them
    with ctx.db.transaction() as c:  # the AI found Iraq (a neighbour of Türkiye) in every report
        c.execute("""INSERT INTO article_ai (article_id, status, countries, queued_at)
                     SELECT id, 'done', '["IQ"]', first_seen_at FROM articles""")
    assert ctx.home_sync.sync() == 5 and related() == 5
    info = client.get("/api/home", headers=H).json()
    assert info["code"] == "TR" and "GR" in info["neighbours"] and "KZ" in info["related"] and "nato" in info["topics"]
    assert "ZA" in info["countries"] and not info["syncing"]
    meta = client.get("/api/meta", headers=H).json()
    assert meta["home_country"] == "TR" and meta["system_country"] == "TR"

    for bad in ({"home.country": "XX"}, {"home.country": "tr"}, {"home.country": "ZA", "home.related": ["QQ"]},
                {"home.topics": ["x"]}, {"home.topics": ["y" * 61]}, {"home.keywords": ["x"]}):
        assert client.patch("/api/settings", headers=H, json=bad).status_code == 422, bad
    client.patch("/api/settings", headers=H, json={"home.topics": ["nato", " Kıbrıs sorunu ", "Kıbrıs sorunu"],
                                                   "home.keywords": [" Kapadokya ", "Kapadokya"]})
    saved = client.get("/api/settings", headers=H).json()
    assert saved["home.keywords"] == ["Kapadokya"] and saved["home.topics"] == ["nato", "Kıbrıs sorunu"]
    assert client.get("/api/home", headers=H).json()["topics"] == ["nato", "Kıbrıs sorunu"]  # the user's own topic
    # A new country starts from its own defaults: no related countries, no topics.
    client.patch("/api/settings", headers=H, json={"home.country": "ZA"})
    info = client.get("/api/home", headers=H).json()
    assert info["code"] == "ZA" and info["related"] == [] and info["topics"] == [] and "MZ" in info["neighbours"]
    assert client.get("/api/meta", headers=H).json()["home_country"] == "ZA"
    assert ctx.home_sync.sync() == 5 and related() == 0
    assert ctx.home_sync.sync() is None  # nothing changed since
    client.patch("/api/settings", headers=H, json={"home.country": ""})  # back to Windows' region
    assert ctx.home_sync.sync() == 5 and related() == 5
    assert "home.applied" not in client.get("/api/settings", headers=H).json()


def test_feed_filters_are_remembered(client):
    assert client.get("/api/settings", headers=H).json()["feed.filters"]["sources"] == []
    chosen = {"regions": ["turkey"], "groups": ["sports"], "langs": ["tr"], "sources": [3, 5], "categories": ["sports"],
              "turkey": True}
    r = client.patch("/api/settings", headers=H, json={"feed.filters": chosen})
    assert r.status_code == 200 and r.json()["feed.filters"] == chosen
    assert client.get("/api/settings", headers=H).json()["feed.filters"] == chosen
    for bad in ({**chosen, "groups": ["nope"]}, {**chosen, "categories": ["gossip"]}, {**chosen, "extra": 1}):
        assert client.patch("/api/settings", headers=H, json={"feed.filters": bad}).status_code == 422
    # A partial object fills in the rest.
    r = client.patch("/api/settings", headers=H, json={"feed.filters": {"turkey": True}})
    assert r.json()["feed.filters"] == {"regions": [], "groups": [], "langs": [], "sources": [], "categories": [],
                                        "turkey": True}


def test_articles_endpoint_search_and_cursor(client, ctx):
    add_articles(ctx)
    r = client.get("/api/articles", headers=H, params={"q": "ırak", "limit": 2}).json()
    assert len(r["items"]) == 2 and r["next"] and r["total"] == 5
    r2 = client.get("/api/articles", headers=H, params={"q": "ırak", "limit": 2, "before": r["next"]}).json()
    assert {i["id"] for i in r2["items"]}.isdisjoint({i["id"] for i in r["items"]})
    assert r2["total"] is None
    assert client.get("/api/articles", headers=H, params={"q": "!!!"}).json() == {"items": [], "next": None, "total": 0}
    assert client.get("/api/articles", headers=H, params={"before": "garbage"}).status_code == 422
    assert client.get("/api/articles", headers=H, params={"hours": 24, "region": "asia"}).json()["items"] == []


def test_source_crud(client, ctx):
    r = client.post("/api/sources", headers=H, json={
        "name": "  Yeni Kaynak  ", "feed_url": "https://yeni.example/rss", "region": "turkey", "language": "tr",
    })
    assert r.status_code == 201
    src = r.json()
    assert src["name"] == "Yeni Kaynak" and src["origin"] == "user" and len(src["feeds"]) == 1

    assert client.post("/api/sources", headers=H, json={"name": "X", "feed_url": "https://yeni.example/rss"}).status_code == 409
    assert client.post("/api/sources", headers=H, json={"name": "X", "feed_url": "not a url"}).status_code == 422
    assert client.post("/api/sources", headers=H, json={"name": "   ", "feed_url": "https://a.example/r"}).status_code == 422
    assert client.post("/api/sources", headers=H, json={"name": "X", "feed_url": "https://b.example/r", "region": "mars"}).status_code == 422

    r = client.patch(f"/api/sources/{src['id']}", headers=H, json={"reliability": 1.8, "enabled": False})
    assert r.json()["reliability"] == 1.8 and r.json()["enabled"] is False
    assert client.patch(f"/api/sources/{src['id']}", headers=H, json={"reliability": 5}).status_code == 422
    assert client.patch(f"/api/sources/{src['id']}", headers=H, json={"slug": "x"}).status_code == 422
    assert client.patch("/api/sources/9999", headers=H, json={"name": "x"}).status_code == 404

    r = client.post(f"/api/sources/{src['id']}/feeds", headers=H, json={"url": "https://yeni.example/rss2", "label": "İkinci"})
    feed2 = next(f for f in r.json()["feeds"] if f["label"] == "İkinci")
    r = client.patch(f"/api/feeds/{feed2['id']}", headers=H, json={"fetch_interval_min": 30, "enabled": False})
    assert next(f for f in r.json()["feeds"] if f["id"] == feed2["id"])["fetch_interval_min"] == 30
    assert client.patch(f"/api/feeds/{feed2['id']}", headers=H, json={"fetch_interval_min": 1}).status_code == 422
    assert client.delete(f"/api/feeds/{feed2['id']}", headers=H).status_code == 204
    assert client.delete(f"/api/feeds/{feed2['id']}", headers=H).status_code == 404

    assert client.delete(f"/api/sources/{src['id']}", headers=H).status_code == 204
    assert all(s["id"] != src["id"] for s in client.get("/api/sources", headers=H).json())


def test_feed_test_endpoint(client, monkeypatch):
    def handler(request):
        if request.url.host == "good.example":
            return httpx.Response(200, content=fixture_bytes("rss_turkish.xml"))
        if request.url.host == "html.example":
            return httpx.Response(200, content=fixture_bytes("not_a_feed.html"))
        if request.url.host == "site.example":  # a web page with a feed link, and a news sitemap in robots.txt
            if request.url.path == "/robots.txt":
                return httpx.Response(200, text="User-agent: *\nAllow: /\nSitemap: https://site.example/news-sitemap.xml\n")
            return httpx.Response(200, content=b'<html><head><link rel="alternate" type="application/rss+xml" href="/feed"></head></html>')
        if request.url.host == "closed.example" and request.url.path == "/robots.txt":
            return httpx.Response(200, text="Sitemap: https://closed.example/sitemap-news.xml\n")
        return httpx.Response(403)

    monkeypatch.setattr(app_module, "make_client", lambda: httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    good = client.post("/api/feeds/test", headers=H, json={"url": "https://good.example/rss"}).json()
    assert good["ok"] and good["item_count"] == 4 and good["language"] == "tr"
    assert good["sample_titles"][0] == "IRAK'ta seçim sonuçları açıklandı"
    html = client.post("/api/feeds/test", headers=H, json={"url": "https://html.example/"}).json()
    assert html == {"ok": False, "error_code": "not_a_feed", "error_detail": html["error_detail"], "suggestions": []}
    site = client.post("/api/feeds/test", headers=H, json={"url": "https://site.example/"}).json()
    assert site["error_code"] == "not_a_feed" and site["suggestions"] == [
        {"url": "https://site.example/feed", "kind": "rss", "title": ""},
        {"url": "https://site.example/news-sitemap.xml", "kind": "sitemap", "title": ""},
    ]
    blocked = client.post("/api/feeds/test", headers=H, json={"url": "https://blocked.example/rss"}).json()
    assert blocked["error_code"] == "http_403" and blocked["suggestions"] == []
    # The home page refuses programs, but robots.txt still names a news sitemap.
    closed = client.post("/api/feeds/test", headers=H, json={"url": "https://closed.example/"}).json()
    assert closed["error_code"] == "http_403"
    assert closed["suggestions"] == [{"url": "https://closed.example/sitemap-news.xml", "kind": "sitemap", "title": ""}]


def test_collector_run_and_status(client):
    assert client.post("/api/collector/run", headers=H).json()["scheduled"] == 2
    status = client.get("/api/status", headers=H).json()
    assert status["collector"]["running"] is False and "articles" in status


def test_meta(client, ctx):
    add_articles(ctx)
    meta = client.get("/api/meta", headers=H).json()
    assert "turkey" in meta["regions"] and meta["languages"] == ["tr"] and meta["ui_languages"] == ["tr", "en"]
    assert meta["kinds"] == ["exclusive", "opinion"]
    # The remembered feed filters accept the virtual groups; unknown ones are refused.
    filters = {"regions": [], "groups": ["opinion", "turkey"], "langs": [], "sources": [], "categories": [], "turkey": False}
    assert client.patch("/api/settings", headers=H, json={"feed.filters": filters}).status_code == 200
    filters["groups"] = ["gossip"]
    assert client.patch("/api/settings", headers=H, json={"feed.filters": filters}).status_code == 422


def test_search_words_are_translated_for_the_lists(client, ctx, monkeypatch):
    add_articles(ctx)
    asked = []

    async def expand(text, languages):
        asked.append((text, languages))
        return {"en": ["Iraq news"]}

    monkeypatch.setattr(ctx.ai_worker, "expand_query", expand)
    r = client.get("/api/search/translations", headers=H, params={"q": " ırak "}).json()
    assert r == {"state": "ok", "queries": {"en": ["Iraq news"]}}
    # The languages of the enabled sources, the most common first.
    assert asked == [("ırak", ctx.articles.source_languages())] and asked[0][1]
    assert client.get("/api/search/translations", headers=H, params={"q": ""}).status_code == 422

    # A translation that matches nothing does not hide what the typed words find, and vice versa.
    both = {"q": "ırak", "qx": ["Iraq news", " ", "x" * 201]}
    assert client.get("/api/articles", headers=H, params=both).json()["total"] == 5
    assert client.get("/api/articles", headers=H, params={"q": "bağdat", "qx": ["irak haberi 3"]}).json()["total"] == 1
    assert client.get("/api/stories", headers=H, params={"q": "bağdat", "qx": ["irak"]}).status_code == 200
    assert client.get("/api/articles", headers=H, params={"q": "a", "qx": [str(i) for i in range(30)]}).status_code == 422


def test_statistics_endpoints(client, ctx):
    add_articles(ctx)
    r = client.get("/api/stats", headers=H, params={"hours": 168}).json()
    assert r["totals"]["articles"] == 5 and len(r["timeline"]) == 7 and r["period"]["hours"] == 168
    assert {"categories", "regions", "countries", "sources", "rising"} <= set(r)
    assert client.get("/api/stats", headers=H, params={"hours": 48}).status_code == 422
    t = client.get("/api/stats/topic", headers=H, params={"q": "ırak", "qx": ["Iraq"], "hours": 24}).json()
    assert t["articles"] == 5 and len(t["buckets"]) == 24 and t["buckets"][-1]["share"] == 1.0
    assert client.get("/api/stats/topic", headers=H, params={"q": "!!!"}).json()["buckets"] == []
    assert client.get("/api/stats/topic", headers=H, params={"q": ""}).status_code == 422


def test_search_words_without_ai_say_why(client, ctx):
    client.patch("/api/settings", headers=H, json={"ai.enabled": False})
    assert client.get("/api/search/translations", headers=H, params={"q": "deprem"}).json() == {
        "state": "disabled", "queries": {}}


def test_ai_endpoints(client, ctx, monkeypatch):
    add_articles(ctx)
    status = client.get("/api/ai/status", headers=H).json()
    assert status["pending"] == 0 and status["state"] == "starting"
    assert client.get("/api/status", headers=H).json()["ai"]["done"] == 0

    first = client.get("/api/articles", headers=H).json()["items"][0]
    assert first["ai_status"] is None and first["ai_texts"] == {}
    assert client.post(f"/api/articles/{first['id']}/ai", headers=H).json() == {"status": "pending"}
    assert client.post("/api/articles/99999/ai", headers=H).status_code == 404
    assert client.get("/api/articles", headers=H).json()["items"][0]["ai_status"] == "pending"
    assert client.post("/api/ai/retry", headers=H).json() == {"requeued": 0}

    r = client.patch("/api/settings", headers=H, json={"ai.url": "http://127.0.0.1:11434/", "ai.model": " qwen3:14b "})
    assert r.json()["ai.url"] == "http://127.0.0.1:11434" and r.json()["ai.model"] == "qwen3:14b"
    assert client.patch("/api/settings", headers=H, json={"ai.url": "not a url"}).status_code == 422
    assert client.patch("/api/settings", headers=H, json={"ai.max_age_hours": 0}).status_code == 422
    # The AI's languages: known codes, one to four, no duplicates.
    assert client.get("/api/settings", headers=H).json()["ai.languages"] is None  # interface language + English
    for bad in ([], ["tr", "en", "de", "fr", "es"], ["xx"], ["TR"]):
        assert client.patch("/api/settings", headers=H, json={"ai.languages": bad}).status_code == 422, bad
    r = client.patch("/api/settings", headers=H, json={"ai.languages": ["pt", "ar", "pt"]})
    assert r.json()["ai.languages"] == ["pt", "ar"]
    assert "pt" in client.get("/api/meta", headers=H).json()["ai_output_languages"]
    assert "politics" in client.get("/api/meta", headers=H).json()["categories"]
    assert client.get("/api/articles", headers=H, params={"turkey": "true", "category": "politics"}).json()["total"] == 0


def test_ai_test_endpoint(client, monkeypatch):
    from test_ai import FakeOllama

    fake = FakeOllama()
    monkeypatch.setattr(app_module, "OllamaClient", lambda url: fake.client(url))
    ok = client.post("/api/ai/test", headers=H, json={"url": "http://localhost:11434"}).json()
    assert ok["ok"] and ok["version"] == "0.34.3"
    assert {m["name"]: m["capabilities"] for m in ok["models"]} == {
        "bge-m3:latest": ["embedding"], "qwen3:14b": ["completion", "tools"],
    }
    down = FakeOllama(raise_exc=lambda r: httpx.ConnectError("x", request=r))
    monkeypatch.setattr(app_module, "OllamaClient", lambda url: down.client(url))
    assert client.post("/api/ai/test", headers=H, json={"url": "http://localhost:1"}).json()["error_code"] == "unreachable"


def test_story_endpoints(client, ctx):
    from test_stories import SPECS, FakeEmbedOllama, seed_articles

    ids = seed_articles(ctx.db, ctx.sources, ctx.articles, SPECS)
    ctx.settings.set("stories.threshold", 0.8)
    worker = StoryWorker(ctx.stories, ctx.settings, client_factory=FakeEmbedOllama().client)
    import asyncio

    asyncio.run(worker.step())
    r = client.get("/api/stories", headers=H, params={"hours": 24}).json()
    assert r["total"] == 3 and r["items"][0]["source_count"] == 3
    top = r["items"][0]
    assert top["representative"] and top["sources"] and top["timeline"]
    assert client.get("/api/stories", headers=H, params={"min_sources": 2}).json()["total"] == 2
    assert client.get("/api/stories", headers=H, params={"sort": "bogus"}).status_code == 422

    detail = client.get(f"/api/stories/{top['id']}", headers=H).json()
    assert len(detail["members"]) == 4
    assert client.get("/api/stories/99999", headers=H).status_code == 404

    moved = client.post(f"/api/articles/{ids['s1']}/detach", headers=H).json()
    assert moved["previous_story_id"] == top["id"] and moved["story_id"] != top["id"]
    assert client.get(f"/api/stories/{top['id']}", headers=H).json()["article_count"] == 3
    assert client.post("/api/articles/99999/detach", headers=H).status_code == 404

    merged = client.post(f"/api/stories/{moved['story_id']}/merge", headers=H, json={"into": top["id"]}).json()
    assert merged["id"] == top["id"] and merged["article_count"] == 4
    assert client.post(f"/api/stories/{top['id']}/merge", headers=H, json={"into": 99999}).status_code == 404

    assert client.post(f"/api/stories/{top['id']}/summarize", headers=H).json() == {"status": "pending"}
    assert client.post("/api/stories/99999/summarize", headers=H).status_code == 404
    looked = client.post("/api/stories/regroup", headers=H, json={"dry_run": True}).json()
    assert set(looked) == {"changed", "created"} and looked["created"] >= 0
    assert set(client.post("/api/stories/regroup", headers=H, json={"dry_run": False}).json()) == {"changed", "created"}
    assert "stories" in client.get("/api/status", headers=H).json()


def test_story_settings_validation(client):
    ok = client.patch("/api/settings", headers=H, json={
        "interest.keywords": [" İsrail ", "enerji", "enerji", ""],
        "interest.categories": ["energy"], "interest.regions": ["middle_east"],
        "score.w_turkey": 0.5, "stories.threshold": 0.8,
    })
    assert ok.status_code == 422  # empty keyword rejected
    ok = client.patch("/api/settings", headers=H, json={
        "interest.keywords": [" İsrail ", "enerji", "enerji"], "interest.categories": ["energy"],
        "interest.regions": ["middle_east"], "score.w_turkey": 0.5, "stories.threshold": 0.8,
    }).json()
    assert ok["interest.keywords"] == ["İsrail", "enerji"] and ok["score.w_turkey"] == 0.5
    for bad in ({"interest.categories": ["nope"]}, {"interest.regions": ["mars"]}, {"stories.threshold": 0.2},
                {"score.w_sources": 2}):
        assert client.patch("/api/settings", headers=H, json=bad).status_code == 422


def test_changing_embedding_model_switches_to_its_measured_threshold(client):
    r = client.patch("/api/settings", headers=H, json={"stories.embed_model": " qwen3-embedding:0.6b "}).json()
    assert r["stories.embed_model"] == "qwen3-embedding:0.6b" and r["stories.threshold"] == 0.67
    assert r["stories.cohesion"] == 0.0
    # An explicit threshold in the same change wins; an unknown model keeps the current threshold.
    r = client.patch("/api/settings", headers=H, json={"stories.embed_model": "bge-m3:latest", "stories.threshold": 0.6}).json()
    assert r["stories.threshold"] == 0.6 and r["stories.cohesion"] == 0.55
    r = client.patch("/api/settings", headers=H, json={"stories.embed_model": "my-embedder:latest"}).json()
    assert r["stories.embed_model"] == "my-embedder:latest" and r["stories.threshold"] == 0.6


def test_notebook_endpoints(client, ctx):
    import asyncio

    from test_stories import SPECS, FakeEmbedOllama, seed_articles

    seed_articles(ctx.db, ctx.sources, ctx.articles, SPECS)
    ctx.settings.set("stories.threshold", 0.8)
    asyncio.run(StoryWorker(ctx.stories, ctx.settings, client_factory=FakeEmbedOllama().client).step())
    s1, s2 = [s["id"] for s in client.get("/api/stories", headers=H).json()["items"][:2]]

    # Story note
    assert client.get(f"/api/stories/{s1}/note", headers=H).json() == {"note": None}
    note = client.put(f"/api/stories/{s1}/note", headers=H, json={"body": "Notum"}).json()["note"]
    assert note["body"] == "Notum" and note["day"] == TODAY
    assert client.put("/api/stories/99999/note", headers=H, json={"body": "x"}).status_code == 404
    assert client.put(f"/api/stories/{s1}/note", headers=H, json={"body": "x" * 20_001}).status_code == 422

    # Meeting list
    a = client.post("/api/meeting", headers=H, json={"story_id": s1})
    assert a.status_code == 201
    b = client.post("/api/meeting", headers=H, json={"story_id": s2}).json()
    assert client.post("/api/meeting", headers=H, json={"story_id": 99999}).status_code == 404
    listing = client.get("/api/meeting", headers=H).json()
    assert listing["day"] == TODAY and [i["story_id"] for i in listing["items"]] == [s1, s2]
    order = client.put("/api/meeting/order", headers=H, json={"day": TODAY, "ids": [b["id"], a.json()["id"]]}).json()
    assert [i["story_id"] for i in order["items"]] == [s2, s1]
    assert client.put("/api/meeting/order", headers=H, json={"day": TODAY, "ids": [b["id"]]}).status_code == 409
    assert client.put("/api/meeting/order", headers=H, json={"day": "yesterday", "ids": []}).status_code == 422
    assert client.patch(f"/api/meeting/{b['id']}", headers=H, json={"comment": "Kısa gerekçe"}).json()["comment"] == "Kısa gerekçe"
    assert client.patch(f"/api/meeting/{b['id']}", headers=H, json={"comment": "x" * 301}).status_code == 422
    assert client.delete(f"/api/meeting/{b['id']}", headers=H).status_code == 204
    assert client.delete(f"/api/meeting/{b['id']}", headers=H).status_code == 404

    # Day notes and calendar
    assert client.put(f"/api/notebook/{TODAY}/note", headers=H, json={"body": "Gün notu"}).json()["day_note"]["body"] == "Gün notu"
    assert client.put("/api/notebook/2026-13-01/note", headers=H, json={"body": "x"}).status_code == 422
    day = client.get(f"/api/notebook/{TODAY}", headers=H).json()
    assert day["day_note"]["body"] == "Gün notu" and len(day["meeting"]) == 1 and len(day["notes"]) == 1
    cal = client.get("/api/notebook", headers=H, params={"month": "2026-09"}).json()
    assert cal["days"] == [{"day": TODAY, "notes": 1, "meeting": 1, "day_note": True}]
    assert client.get("/api/notebook", headers=H, params={"month": "Eylül"}).status_code == 422


def test_fulltext_endpoints(client, ctx, monkeypatch):
    add_articles(ctx)
    aid = client.get("/api/articles", headers=H).json()["items"][0]["id"]
    assert client.get(f"/api/articles/{aid}/fulltext", headers=H).json() == {"fulltext": None}
    assert client.post(f"/api/articles/{aid}/fulltext", headers=H).json() == {"status": "pending"}
    assert client.get(f"/api/articles/{aid}/fulltext", headers=H).json()["fulltext"]["reason"] == "user"
    assert client.post("/api/articles/999999/fulltext", headers=H).status_code == 404
    assert client.post(f"/api/articles/{aid}/fulltext/translate", headers=H).json()["detail"]["code"] == "no_fulltext"

    status = client.get("/api/status", headers=H).json()["fulltext"]
    assert status["pending"] == 1 and status["paused_sources"] == []

    src = client.get("/api/sources", headers=H).json()[0]
    assert src["fulltext_mode"] in ("off", "http", "browser")
    assert client.patch(f"/api/sources/{src['id']}", headers=H, json={"fulltext_mode": "browser"}).json()["fulltext_mode"] == "browser"
    assert client.patch(f"/api/sources/{src['id']}", headers=H, json={"fulltext_mode": "stealth"}).status_code == 422

    ok = client.patch("/api/settings", headers=H, json={"extension.profile": "own", "fulltext.per_site_hour": 3}).json()
    assert ok["extension.profile"] == "own" and ok["fulltext.per_site_hour"] == 3
    assert client.patch("/api/settings", headers=H, json={"fulltext.profile": "other"}).status_code == 422
    assert client.patch("/api/settings", headers=H, json={"fulltext.per_site_hour": 100}).status_code == 422

    monkeypatch.setattr(app_module, "browser_for", lambda path: None)
    monkeypatch.setattr(app_module, "find_browsers", lambda: [])
    assert client.get("/api/fulltext/browsers", headers=H).json()["chosen"] is None
    assert client.post("/api/fulltext/login", headers=H, json={}).json()["detail"]["code"] == "no_browser"
    assert client.post(f"/api/fulltext/sources/{src['id']}/resume", headers=H).json() == {"status": "resumed"}


def test_subscription_sites_login_and_test(client, ctx, monkeypatch):
    from pathlib import Path

    from worldsignal.fulltext.fetch import BrowserInfo

    add_articles(ctx)
    sources = client.get("/api/sources", headers=H).json()
    site = next(s for s in sources if s["enabled"] and s["articles_24h"] > 0)
    client.patch(f"/api/sources/{site['id']}", headers=H, json={"fulltext_mode": "browser", "paywalled": True})
    listing = client.get("/api/fulltext/sites", headers=H).json()
    entry = next(s for s in listing["sites"] if s["id"] == site["id"])
    assert entry["last"] is None and entry["queued"] == 0 and listing["login_window_open"] is False

    # "Try": the site's newest article is fetched at once (a user request).
    tried = client.post(f"/api/fulltext/sites/{site['id']}/test", headers=H).json()
    assert tried["status"] == "pending"
    assert client.get(f"/api/articles/{tried['article_id']}/fulltext", headers=H).json()["fulltext"]["reason"] == "user"
    assert next(s for s in client.get("/api/fulltext/sites", headers=H).json()["sites"] if s["id"] == site["id"])["queued"] == 1
    now = datetime.now(UTC)
    job = ctx.fulltext.next_job(now, per_site_hour=20)
    assert job.article_id == tried["article_id"]
    ctx.fulltext.mark_attempt(job.article_id, now)
    ctx.fulltext.store_failure(job, "paywall", now)  # what a signed-out profile gets
    last = next(s for s in client.get("/api/fulltext/sites", headers=H).json()["sites"] if s["id"] == site["id"])["last"]
    assert last is not None and last["error_code"] == "paywall"
    empty = next(s for s in sources if s["articles_24h"] == 0)
    assert client.post(f"/api/fulltext/sites/{empty['id']}/test", headers=H).json()["detail"]["code"] == "no_articles"

    # "Open site": the site's home page in World Signal's own profile (where the extension is, extension.profile = own).
    opened = []
    monkeypatch.setattr(app_module, "browser_for", lambda path: BrowserInfo("Brave", Path("brave.exe"), Path("main")))
    monkeypatch.setattr(app_module, "open_login_window", lambda b, profile, url: opened.append(url))
    ctx.settings.set("extension.profile", "own")
    assert client.post("/api/fulltext/login", headers=H, json={"source_id": site["id"]}).json() == {"status": "opened"}
    assert opened == [site["homepage"]]
    assert client.post("/api/fulltext/login", headers=H, json={}).json() == {"status": "opened"}
    assert opened[-1] == "about:blank"
    assert client.post("/api/fulltext/login", headers=H, json={"source_id": 99999}).status_code == 404


def test_mail_draft_prefers_outlook_and_falls_back_to_the_default_program(client, monkeypatch):
    from worldsignal import mailer

    opened = []
    monkeypatch.setattr(mailer, "outlook_installed", lambda: True)
    monkeypatch.setattr(mailer, "outlook_draft", lambda subject, html: opened.append(("outlook", subject, html)) or True)
    body = {"subject": "Toplantı önerileri — 28.09.2026", "html": "<b>1. Başlık</b>", "text": "1. Başlık",
            "cut_note": "Devamı panoda."}
    assert client.post("/api/mail/draft", headers=H, json=body).json() == {"method": "outlook", "cut": False}
    assert opened == [("outlook", body["subject"], body["html"])]

    # Outlook missing (or its automation refused): the default mail program, plain text.
    monkeypatch.setattr(mailer, "outlook_installed", lambda: False)
    monkeypatch.setattr(mailer.os, "startfile", lambda link: opened.append(("default", link)), raising=False)
    assert client.post("/api/mail/draft", headers=H, json=body).json() == {"method": "default", "cut": False}
    assert opened[-1][1].startswith("mailto:?subject=Toplant%C4%B1%20") and "body=1.%20Ba%C5%9Fl%C4%B1k" in opened[-1][1]

    long_text = "\n".join(f"{i}. Çok uzun bir başlık satırı" for i in range(200))
    r = client.post("/api/mail/draft", headers=H, json={**body, "text": long_text}).json()
    assert r == {"method": "default", "cut": True}
    link = opened[-1][1]
    assert len(link) < 8000 and "Devam%C4%B1%20panoda." in link

    def no_program(link):
        raise OSError("no association")

    monkeypatch.setattr(mailer.os, "startfile", no_program, raising=False)
    r = client.post("/api/mail/draft", headers=H, json=body)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "no_mail_program"
    assert client.post("/api/mail/draft", headers=H, json={**body, "subject": ""}).status_code == 422
