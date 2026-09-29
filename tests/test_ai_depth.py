"""How much the AI writes (ai.depth): every report / stories cover their reports / fast batches of headlines."""

import asyncio
import json
import re
from datetime import UTC, datetime

import httpx
import pytest

from test_stories import SPECS, STORY_ANSWER, FakeEmbedOllama, make_worker, seed_articles
from worldsignal.ai.enrich import EnrichInput, EnrichTask, batch_schema, render_batch, validate_batch
from worldsignal.ai.ollama import OllamaClient
from worldsignal.ai.worker import AiWorker
from worldsignal.home_sync import HomeSync
from worldsignal.repo.ai import AiRepository
from worldsignal.repo.stories import StoryRepository


def run(coro):
    return asyncio.run(coro)


class FakeModel:
    """Answers story summaries, single reports and batches of reports like Ollama's /api/chat."""

    def __init__(self, story=None, drop=()):
        self.story = story or {**STORY_ANSWER, "countries": ["IR", "US"], "mentions_turkey": True, "topics": []}
        self.drop = set(drop)  # item numbers a batch answer leaves out
        self.calls: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        body = json.loads(request.content)
        self.calls.append(body)
        text = body["messages"][1]["content"]
        props = body["format"]["properties"]
        if "items" in props:
            numbers = [int(n) for n in re.findall(r"^\[(\d+)\]$", text, re.M)]
            answer = {"items": [{"n": n, "title_tr": f"Başlık {n}", "title_en": f"Headline {n}", "category": "politics",
                                 "countries": ["FR"], "mentions_turkey": False, "topics": []}
                                for n in numbers if n not in self.drop]}
        elif "Reports:" in text:
            answer = self.story
        else:
            answer = {"title_tr": "Tek başlık", "summary_tr": "Tek özet.", "title_en": "Single", "summary_en": "One.",
                      "category": "other", "countries": [], "mentions_turkey": False, "topics": []}
        return httpx.Response(200, json={"message": {"content": json.dumps(answer, ensure_ascii=False)},
                                         "total_duration": 1, "eval_count": 1, "eval_duration": 1})

    def client(self, url="http://localhost:11434"):
        return OllamaClient(url, transport=httpx.MockTransport(self.handler))

    def kinds(self):
        return ["batch" if "items" in c["format"]["properties"] else
                "story" if "Reports:" in c["messages"][1]["content"] else "report" for c in self.calls]


@pytest.fixture
def world(db, sources, articles, settings, home):
    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama()).step())
    stories = StoryRepository(db)
    return {"ids": ids, "db": db, "settings": settings, "stories": stories, "home": home, "articles": articles,
            "ai": AiRepository(db, home=home.profile)}


def ai_worker(world, model, depth):
    world["settings"].set_many({"ai.model": "m", "ai.depth": depth})
    return AiWorker(world["ai"], world["settings"], client_factory=model.client, stories=world["stories"],
                    home=world["home"].profile)


def queued(world):
    return {r[0] for r in world["db"].conn.execute("SELECT article_id FROM article_ai WHERE status = 'pending'")}


def test_every_report_is_read_on_its_own_at_full_depth(world):
    worker = ai_worker(world, FakeModel(), "full")
    run(worker.step())
    assert queued(world) >= {world["ids"]["a1"], world["ids"]["b1"], world["ids"]["a3"]}


def test_a_summarised_story_covers_its_reports_and_rates_them(world):
    ids, stories = world["ids"], world["stories"]
    model = FakeModel()
    worker = ai_worker(world, model, "stories")
    run(worker.step())  # Hormuz first (3 independent sources)
    hormuz = stories.story_of(ids["a1"])
    # Only the single report (the storm) is queued; the Hormuz and Swiss reports are covered by their stories.
    assert queued(world) == {ids["a3"]}
    row = world["db"].conn.execute(
        "SELECT ai_countries, ai_mentions_home, ai_home_relevance, ai_home_links, turkey_relevance FROM stories "
        "WHERE id = ?", (hormuz,)).fetchone()
    # The summary found Türkiye mentioned: the story is rated "direct" although none of its reports was read.
    assert json.loads(row["ai_countries"]) == ["IR", "US"] and row["ai_mentions_home"] == 1
    assert row["ai_home_relevance"] == "direct" and json.loads(row["ai_home_links"]) == ["home_mentioned"]
    stories.recompute([hormuz], datetime.now(UTC), {}, None)
    assert stories.get(hormuz)["turkey_relevance"] == "direct"
    # The story prompt asked for the facts with the same fields as a report.
    schema = model.calls[0]["format"]["properties"]
    assert {"countries", "mentions_turkey"} <= set(schema)
    run(worker.step())  # the Swiss story
    run(worker.step())  # then the single report, on its own with a summary ("stories", not "fast")
    assert model.kinds() == ["story", "story", "report"]


def test_old_summaries_without_facts_are_redone_when_reports_are_not_read(world):
    ids, stories = world["ids"], world["stories"]
    hormuz = stories.story_of(ids["a1"])
    texts = {lang: {"title": "t", "summary": "s", "why": ""} for lang in ("tr", "en")}
    stories.store_story_ai(hormuz, texts=texts, category="other",
                           issues=[], model="m", article_count=4)  # written by 0.12: no facts
    since = "2000-01-01T00:00:00Z"
    assert stories.next_story_job(since, 2)["id"] != hormuz  # "full" reads the reports anyway
    assert stories.next_story_job(since, 2, need_facts=True)["id"] == hormuz


def test_a_story_that_failed_for_good_leaves_its_reports_to_be_read(world):
    ids = world["ids"]
    with world["db"].transaction() as c:
        c.execute("UPDATE stories SET ai_status = 'failed' WHERE id = ?", (world["stories"].story_of(ids["a1"]),))
    world["ai"].enqueue_recent("2000-01-01T00:00:00Z", 2)
    assert {ids["a1"], ids["b1"]} <= queued(world) and ids["a2"] not in queued(world)


def test_fast_reads_single_reports_ten_at_a_time_without_summaries(world, sources, articles):
    seed_articles(world["db"], sources, articles,
                            [("gamma-live", f"x{i}", f"Unrelated report number {i} about item {i}", 5 + i) for i in range(12)])
    run(make_worker(world["db"], world["settings"], FakeEmbedOllama()).step())
    model = FakeModel(drop={3})
    worker = ai_worker(world, model, "fast")
    for _ in range(4):
        run(worker.step())
    assert model.kinds()[:2] == ["story", "story"] and model.kinds()[2] == "batch"
    batch = model.calls[2]
    assert "summary_tr" not in batch["format"]["properties"]["items"]["items"]["properties"]
    assert len(re.findall(r"^\[\d+\]$", batch["messages"][1]["content"], re.M)) == 10
    done = world["db"].conn.execute("SELECT article_id, brief, texts FROM article_ai WHERE status = 'done'").fetchall()
    assert len(done) >= 9 and all(r["brief"] == 1 for r in done)
    assert {json.loads(r["texts"])["tr"]["summary"] for r in done} == {""}  # headlines only
    # The item the model left out waits for another try.
    left_out = world["db"].conn.execute("SELECT status, attempts FROM article_ai WHERE error_code = 'bad_response'").fetchone()
    assert left_out["status"] == "pending" and left_out["attempts"] == 1
    # Asking for a report read in a batch writes its summary, on its own and first.
    brief_id = done[0]["article_id"]
    assert world["ai"].request(brief_id, ("tr", "en")) == "pending"
    run(worker.step())
    assert model.kinds()[-1] == "report"
    row = world["ai"].get(brief_id)
    assert row["brief"] == 0 and row["texts"]["tr"]["summary"] == "Tek özet."
    assert world["ai"].request(brief_id, ("tr", "en")) == "done"


def test_a_batch_answer_is_matched_by_number():
    task = EnrichTask(("tr", "en"), (), ask_turkey=True, with_summary=False)
    inputs = [EnrichInput("S", "en", f"Title {i}", "text " * 300) for i in range(3)]
    rendered = render_batch(inputs)
    assert rendered.count("text") < 3 * 300  # each report's text is cut for a batch
    data = {"items": [{"n": 3, "title_tr": "Üç", "title_en": "Three", "category": "politics", "countries": ["fr", "XXX"],
                       "mentions_turkey": True},
                      {"n": 1, "title_tr": "", "title_en": "One", "category": "nope", "countries": []},
                      {"n": 9, "title_tr": "Dokuz", "title_en": "Nine", "category": "other", "countries": []}]}
    results = validate_batch(data, inputs, task)
    assert results[0] is None and results[1] is None  # empty headline; left out
    assert results[2].texts == {"tr": {"title": "Üç", "summary": ""}, "en": {"title": "Three", "summary": ""}}
    assert results[2].countries == ["FR"] and results[2].mentions_turkey is True
    assert set(batch_schema(task)["properties"]["items"]["items"]["required"]) >= {"n", "title_tr", "countries"}


def test_changing_the_country_rates_story_facts_again(world):
    ids, stories, settings = world["ids"], world["stories"], world["settings"]
    run(ai_worker(world, FakeModel({**STORY_ANSWER, "countries": ["GR"], "mentions_turkey": False, "topics": []}),
                  "stories").step())
    hormuz = stories.story_of(ids["a1"])
    level = lambda: world["db"].conn.execute("SELECT ai_home_relevance FROM stories WHERE id = ?", (hormuz,)).fetchone()[0]  # noqa: E731
    assert level() == "indirect"  # Greece is a neighbour of Türkiye
    settings.set("home.country", "JP")
    HomeSync(world["home"], world["articles"], stories, settings).sync()
    assert level() == "none"
