import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from conftest import MINI_CATALOG
from worldsignal.ai.enrich import SCHEMA, EnrichInput, fidelity_issues, validate
from worldsignal.ai.ollama import OllamaClient, OllamaError
from worldsignal.ai.worker import AiWorker
from worldsignal.country import HomeState
from worldsignal.collector.rss import ParsedEntry
from worldsignal.repo.ai import AiRepository
from worldsignal.repo.articles import ArticleFilter

GOOD = {
    "title_tr": "Irak'ta seçim sonuçları açıklandı",
    "summary_tr": "Irak'ta yapılan genel seçimlerin sonuçları açıklandı. Katılım oranı yüzde 41 oldu.",
    "title_en": "Iraq election results announced",
    "summary_en": "The results of Iraq's general election were announced. Turnout was 41 percent.",
    "category": "politics",
    "countries": ["IQ"],
    "mentions_turkey": False,
    "topics": [],
}


class FakeOllama:
    """Records calls and answers like Ollama's /api/chat."""

    def __init__(self, answer=GOOD, status=200, raise_exc=None, loaded=(), chat_only=False):
        self.answer = answer
        self.chat_only = chat_only  # raise_exc only for /api/chat (Ollama up, generation slow)
        self.status = status
        self.raise_exc = raise_exc
        self.loaded = list(loaded)  # models reported by /api/ps
        self.calls = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if self.raise_exc is not None and (not self.chat_only or request.url.path == "/api/chat"):
            raise self.raise_exc(request)
        if request.url.path == "/api/ps":
            # Entries are a name (GPU model) or a full /api/ps dict (e.g. with size_vram 0 for a CPU model).
            return httpx.Response(200, json={"models": [m if isinstance(m, dict) else {"name": m} for m in self.loaded]})
        if request.url.path == "/api/version":
            return httpx.Response(200, json={"version": "0.34.3"})
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [
                {"name": "qwen3:14b", "size": 9_300_000_000, "details": {"parameter_size": "14.8B", "quantization_level": "Q4_K_M", "family": "qwen3"}},
                {"name": "bge-m3:latest", "size": 1_200_000_000, "details": {"parameter_size": "566.70M", "family": "bert"}},
            ]})
        if request.url.path == "/api/show":
            name = json.loads(request.content)["model"]
            return httpx.Response(200, json={"capabilities": ["embedding"] if name.startswith("bge") else ["completion", "tools"]})
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "model 'x' not found"})
        content = self.answer if isinstance(self.answer, str) else json.dumps(self.answer, ensure_ascii=False)
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": content},
            "total_duration": 2_000_000_000, "load_duration": 10_000_000,
            "prompt_eval_count": 300, "eval_count": 80, "eval_duration": 1_000_000_000,
        })

    def client(self, url="http://localhost:11434"):
        return OllamaClient(url, transport=httpx.MockTransport(self.handler))


def run(coro):
    return asyncio.run(coro)


def add_articles(db, sources, articles, n=3, minutes_ago=5):
    sources.seed_from_catalog(MINI_CATALOG)
    beta = next(s for s in sources.list_sources() if s["slug"] == "beta")
    now = datetime.now(UTC)
    with db.transaction() as c:
        articles.insert_entries(c, source_id=beta["id"], feed_id=beta["feeds"][0]["id"], language="tr", now=now, entries=[
            ParsedEntry(f"k{i}", f"https://beta.example/{i}", f"IRAK haberi {i}", "Katılım oranı yüzde 41 oldu.", None,
                        now - timedelta(minutes=minutes_ago + i))
            for i in range(n)
        ])
    return [r["id"] for r in articles.list(ArticleFilter())]


# -- Ollama client -------------------------------------------------------------------
def test_chat_json_sends_schema_and_parses_stats():
    fake = FakeOllama()
    result = run(fake.client().chat_json("qwen3:14b", "sys", "user", SCHEMA))
    assert result.data["category"] == "politics"
    assert result.tokens_per_second == 80.0
    body = json.loads(fake.calls[0].content)
    assert body["format"] == SCHEMA and body["think"] is False and body["stream"] is False
    assert body["options"]["num_predict"] == 1024


@pytest.mark.parametrize(
    ("fake", "code"),
    [
        (FakeOllama(raise_exc=lambda r: httpx.ConnectError("refused", request=r)), "unreachable"),
        (FakeOllama(raise_exc=lambda r: httpx.ReadTimeout("slow", request=r)), "timeout"),
        (FakeOllama(status=404), "model_missing"),
        (FakeOllama(status=500), "http_500"),
        (FakeOllama(answer="not json {"), "bad_response"),
        (FakeOllama(answer="[1, 2]"), "bad_response"),
    ],
)
def test_chat_json_errors(fake, code):
    with pytest.raises(OllamaError) as exc:
        run(fake.client().chat_json("m", "s", "u", SCHEMA))
    assert exc.value.code == code


def test_list_models_and_version():
    fake = FakeOllama()
    assert run(fake.client().version()) == "0.34.3"
    models = run(fake.client().list_models())
    assert [m.name for m in models] == ["bge-m3:latest", "qwen3:14b"] and models[1].parameter_size == "14.8B"
    assert run(fake.client().capabilities("bge-m3:latest")) == ["embedding"]


# -- enrichment validation -----------------------------------------------------------------
def test_validate_normalises_output():
    inp = EnrichInput("Beta", "tr", "IRAK'ta seçim", "Katılım oranı yüzde 41 oldu.")
    r = validate({**GOOD, "category": "nonsense", "title_tr": '  "Başlık"  '}, inp)
    assert r.category == "other" and r.title_tr == "Başlık" and r.issues == []
    r = validate({**GOOD, "countries": ["iq", "IQ", "Iraq", "usa", 5], "topics": ["nato", "bogus", "nato"]}, inp)
    assert r.countries == ["IQ"] and r.topics == ["nato"]
    with pytest.raises(ValueError):
        validate({**GOOD, "title_tr": "  "}, inp)


def test_fidelity_flags_invented_numbers_only():
    src = "Explosion kills 12 people, 1,500 evacuated in 2026"
    assert fidelity_issues(src, "12 kişi öldü, 1.500 kişi tahliye edildi (2026)") == []
    assert fidelity_issues(src, "15 kişi öldü") == ["number_not_in_source:15"]


def test_render_marks_headline_only_items():
    assert "(no text besides the headline)" in EnrichInput("S", "en", "Title", "Title").render()
    long = EnrichInput("S", "en", "T", "x" * 10000).render()
    assert len(long) < 6200


# -- queue ---------------------------------------------------------------------------------
def test_queue_orders_newest_first_and_user_requests_jump(db, sources, articles):
    ids = add_articles(db, sources, articles, n=3)
    ai = AiRepository(db)
    since = (datetime.now(UTC) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert ai.enqueue_recent(since) == 3
    assert ai.enqueue_recent(since) == 0  # idempotent
    assert ai.next_job().article_id == ids[0]  # newest
    assert ai.request(ids[2]) == "pending"
    assert ai.next_job().article_id == ids[2]
    with pytest.raises(KeyError):
        ai.request(99999)


def test_old_automatic_items_leave_queue_but_user_requests_stay(db, sources, articles):
    ids = add_articles(db, sources, articles, n=2, minutes_ago=60 * 30)  # 30 h old
    ai = AiRepository(db)
    assert ai.enqueue_recent((datetime.now(UTC) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")) == 0
    ai.request(ids[0])
    ai.enqueue_recent((datetime.now(UTC) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    assert ai.counts()["pending"] == 1


def test_failures_retry_then_fail_and_can_be_requeued(db, sources, articles):
    ids = add_articles(db, sources, articles, n=1)
    ai = AiRepository(db)
    ai.request(ids[0])
    assert ai.store_failure(ids[0], "bad_response") == "pending"
    assert ai.store_failure(ids[0], "bad_response") == "pending"
    assert ai.store_failure(ids[0], "bad_response") == "failed"
    assert ai.next_job() is None and ai.counts()["failed"] == 1
    assert ai.retry_failed() == 1 and ai.next_job().article_id == ids[0]


# -- worker ----------------------------------------------------------------------------------
def make_worker(db, settings, fake, **prefs):
    settings.set_many({"ai.model": "qwen3:14b", **prefs})
    home = HomeState(settings.get_preferences, "TR")
    return AiWorker(AiRepository(db, home=home.profile), settings, client_factory=fake.client)


def test_worker_processes_queue_and_results_are_searchable(db, sources, articles, settings):
    ids = add_articles(db, sources, articles, n=2)
    fake = FakeOllama()
    worker = make_worker(db, settings, fake)
    assert run(worker.step()) == 0
    assert run(worker.step()) == 0
    assert run(worker.step()) > 0  # queue empty -> idle
    assert worker.status()["state"] == "idle" and worker.status()["done"] == 2
    items = articles.list(ArticleFilter())
    assert items[0]["title_tr"] == GOOD["title_tr"] and items[0]["category"] == "politics"
    # Turkish AI text is searchable ("seçim" only exists in the AI title).
    assert {i["id"] for i in articles.list(ArticleFilter(query="SECIM"))} == set(ids)
    assert len(articles.list(ArticleFilter(categories=["politics"], turkey_only=True))) == 2
    assert articles.list(ArticleFilter(categories=["sports"])) == []
    assert articles.count(ArticleFilter(turkey_only=True)) == 2


def test_worker_flags_invented_numbers(db, sources, articles, settings):
    add_articles(db, sources, articles, n=1)
    fake = FakeOllama(answer={**GOOD, "summary_tr": "Katılım yüzde 99 oldu."})
    run(make_worker(db, settings, fake).step())
    assert articles.list(ArticleFilter())[0]["ai_issues"] == ["number_not_in_source:99"]


@pytest.mark.parametrize("exc_code", ["unreachable", "timeout"])
def test_worker_pauses_without_penalising_articles(db, sources, articles, settings, exc_code):
    add_articles(db, sources, articles, n=1)
    raiser = (lambda r: httpx.ConnectError("x", request=r)) if exc_code == "unreachable" else (lambda r: httpx.ReadTimeout("x", request=r))
    worker = make_worker(db, settings, FakeOllama(raise_exc=raiser, chat_only=exc_code == "timeout"))
    assert run(worker.step()) > 0
    assert worker.status()["state"] == exc_code
    row = AiRepository(db).next_job()
    assert row is not None and row.attempts == 0
    # Original article is still listed, just without Turkish fields.
    assert articles.list(ArticleFilter())[0]["title_tr"] is None


def test_worker_model_missing_and_disabled_and_no_model(db, sources, articles, settings):
    add_articles(db, sources, articles, n=1)
    worker = make_worker(db, settings, FakeOllama(status=404))
    run(worker.step())
    assert worker.status()["state"] == "model_missing"
    settings.set("ai.enabled", False)
    run(worker.step())
    assert worker.status()["state"] == "disabled"
    settings.set_many({"ai.enabled": True, "ai.model": ""})
    run(worker.step())
    assert worker.status()["state"] == "no_model"


def test_worker_bad_output_counts_attempt(db, sources, articles, settings):
    ids = add_articles(db, sources, articles, n=1)
    worker = make_worker(db, settings, FakeOllama(answer={**GOOD, "title_tr": ""}))
    assert run(worker.step()) == 0
    assert AiRepository(db).get(ids[0])["attempts"] == 1
    assert worker.status()["last_error"] == "bad_response"


def test_pending_rows_do_not_leak_partial_fields(db, sources, articles):
    ids = add_articles(db, sources, articles, n=1)
    AiRepository(db).request(ids[0])
    item = articles.list(ArticleFilter())[0]
    assert item["ai_status"] == "pending" and item["title_tr"] is None and item["ai_issues"] == []


def test_worker_waits_while_another_model_uses_the_gpu(db, sources, articles, settings):
    add_articles(db, sources, articles, n=1)
    fake = FakeOllama(loaded=["Qwen3.8-27b:latest", "qwen3:14b"])
    worker = make_worker(db, settings, fake)
    assert run(worker.step()) > 0
    status = worker.status()
    assert status["state"] == "gpu_busy" and status["busy_with"] == "Qwen3.8-27b:latest"
    assert not any(c.url.path == "/api/chat" for c in fake.calls)  # nothing was sent to the GPU
    assert AiRepository(db).next_job().attempts == 0

    # Only our own chat model, plus the story embedding model running on the CPU -> proceed.
    fake.loaded = ["qwen3:14b", {"name": "bge-m3:latest", "size_vram": 0}]
    assert run(worker.step()) == 0
    assert worker.status()["done"] == 1 and worker.status()["busy_with"] is None


def test_worker_can_be_told_not_to_yield(db, sources, articles, settings):
    add_articles(db, sources, articles, n=1)
    worker = make_worker(db, settings, FakeOllama(loaded=["other:7b"]), **{"ai.yield_gpu": False})
    assert run(worker.step()) == 0
    assert worker.status()["done"] == 1


# -- English next to Turkish (prompt v5) -----------------------------------------------------
def test_english_is_stored_and_searchable(db, sources, articles, settings):
    from worldsignal.repo.articles import ArticleFilter

    add_articles(db, sources, articles, n=1)
    run(make_worker(db, settings, FakeOllama()).step())
    item = articles.list(ArticleFilter())[0]
    assert item["title_en"] == "Iraq election results announced" and item["summary_en"].startswith("The results")
    assert articles.count(ArticleFilter(query="turnout")) == 1  # English AI text is indexed
    assert articles.count(ArticleFilter(query="katılım")) == 1


def test_validate_requires_english_too():
    inp = EnrichInput("Beta", "tr", "IRAK'ta seçim", "Katılım oranı yüzde 41 oldu.")
    with pytest.raises(ValueError):
        validate({**GOOD, "title_en": "  "}, inp)
    r = validate({**GOOD, "summary_en": "Turnout was 55 percent."}, inp)
    assert r.issues == ["number_not_in_source:55"]  # the English text is checked as well


def test_old_results_get_english_in_the_background_without_losing_turkish(db, sources, articles, settings):
    ids = add_articles(db, sources, articles, n=2)
    repo = AiRepository(db)
    run(make_worker(db, settings, FakeOllama()).step())
    run(make_worker(db, settings, FakeOllama()).step())
    # Simulate results written before English existed.
    with db.transaction() as c:
        c.execute("UPDATE article_ai SET title_en = NULL, summary_en = NULL, prompt_version = 4")
    since = "2000-01-01T00:00:00Z"
    job = repo.next_job(since)
    assert job is not None and job.upgrade
    assert repo.next_job() is None  # without a window no upgrade work is offered

    # A failed redo keeps the finished Turkish result.
    broken = FakeOllama(answer="not json")
    run(make_worker(db, settings, broken).step())
    row = repo.get(job.article_id)
    assert row["status"] == "done" and row["title_tr"] and row["title_en"] is None

    fake = FakeOllama()
    for _ in range(3):
        run(make_worker(db, settings, fake).step())
    assert all(repo.get(i)["title_en"] == "Iraq election results announced" for i in ids)
    assert repo.next_job(since) is None
