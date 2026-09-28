"""Story building: embedding, clustering, scoring, manual corrections and story AI."""

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta

import httpx
import numpy as np
import pytest

from conftest import MINI_CATALOG
from worldsignal.ai.ollama import OllamaClient
from worldsignal.ai.worker import AiWorker
from worldsignal.collector.rss import ParsedEntry
from worldsignal.repo.ai import AiRepository
from worldsignal.repo.stories import StoryFilter, StoryRepository
from worldsignal.stories.embedding import embed_text
from worldsignal.stories.worker import StoryWorker

NOW = datetime.now(UTC).replace(microsecond=0)
VOCAB = ["hormuz", "drone", "swiss", "neutrality", "storm", "flood", "madrid", "eviction", "gaza", "football"]


def fake_vector(text: str) -> list[float]:
    """Bag of topic words: articles sharing words are similar, others orthogonal."""
    words = set(re.findall(r"\w+", text.lower()))
    v = [1.0 if w in words else 0.0 for w in VOCAB] + [0.05]  # small shared component
    return v


class FakeEmbedOllama:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.requests: list[dict] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.fail:
            raise httpx.ConnectError("down", request=request)
        body = json.loads(request.content)
        self.requests.append(body)
        return httpx.Response(200, json={"embeddings": [fake_vector(t) for t in body["input"]]})

    def client(self, url="http://localhost:11434"):
        return OllamaClient(url, transport=httpx.MockTransport(self.handler))


def run(coro):
    return asyncio.run(coro)


def seed_articles(db, sources, articles, specs):
    """specs: list of (source_slug, key, title, minutes_ago)."""
    sources.seed_from_catalog(MINI_CATALOG)
    existing = {s["slug"] for s in sources.list_sources()}
    # A third independent outlet and a second outlet of Beta's media group.
    if "gamma-live" not in existing:
        sources.create_source({"name": "Gamma Live", "owner": "Gamma Group", "region": "asia"}, "https://gl.example/rss")
        sources.create_source({"name": "Beta Sister", "owner": "Beta", "region": "turkey", "language": "tr"},
                              "https://bs.example/rss")
    by_slug = {s["slug"]: s for s in sources.list_sources()}
    for slug, key, title, minutes_ago in specs:
        s = by_slug[slug]
        with db.transaction() as c:
            articles.insert_entries(c, source_id=s["id"], feed_id=s["feeds"][0]["id"], language=s["language"], now=NOW,
                                    entries=[ParsedEntry(key, f"https://x.example/{key}", title, "", None,
                                                         NOW - timedelta(minutes=minutes_ago))])
    return {r["url"].rsplit("/", 1)[1]: r["id"] for r in articles.list(__import__("worldsignal.repo.articles", fromlist=["ArticleFilter"]).ArticleFilter(limit=500))}


SPECS = [
    ("alpha", "a1", "Iran seizes US drone in Hormuz", 50),
    ("beta", "b1", "hormuz drone seized by Iran", 40),
    ("gamma-live", "g1", "Hormuz drone incident", 30),
    ("beta-sister", "s1", "Hormuz drone: details", 20),
    ("alpha", "a2", "Swiss reject neutrality initiative", 45),
    ("beta", "b2", "swiss neutrality vote result", 35),
    ("alpha", "a3", "Storm floods New Jersey", 25),
]


def make_worker(db, settings, fake, threshold=0.8):
    settings.set_many({"stories.threshold": threshold, "stories.embed_model": "bge-m3:latest"})
    return StoryWorker(StoryRepository(db), settings, client_factory=fake.client)


def story_members(repo, article_id):
    return {m["id"] for m in repo.get(repo.story_of(article_id))["members"]}


def test_embed_text_prefixes():
    assert embed_text("bge-m3:latest", "T", "S", with_summary=True) == "T. S"
    assert embed_text("embeddinggemma:latest", "T", "T", with_summary=True) == "task: clustering | query: T"
    assert embed_text("qwen3-embedding:0.6b", "T", "S", with_summary=False).endswith("Query: T")


def test_worker_embeds_on_cpu_clusters_and_scores(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    fake = FakeEmbedOllama()
    worker = make_worker(db, settings, fake)
    run(worker.step())
    assert fake.requests[0]["options"] == {"num_gpu": 0}  # never on the GPU
    repo = StoryRepository(db)
    assert story_members(repo, ids["a1"]) == {ids["a1"], ids["b1"], ids["g1"], ids["s1"]}
    assert story_members(repo, ids["a2"]) == {ids["a2"], ids["b2"]}
    assert story_members(repo, ids["a3"]) == {ids["a3"]}

    hormuz = repo.get(repo.story_of(ids["a1"]))
    # 4 outlets, but Beta and Beta Sister share a media group -> 3 independent sources.
    assert hormuz["article_count"] == 4 and hormuz["source_count"] == 3
    assert {"kind": "sources", "count": 3} in hormuz["score_parts"]["tags"]
    assert hormuz["first_seen_at"] < hormuz["last_seen_at"]
    items, total = repo.list(StoryFilter())
    assert total == 3 and items[0]["id"] == hormuz["id"]  # most sources first
    assert repo.counts() == {"embedded": 7, "clustered": 7, "stories": 3, "multi_source": 2}
    assert worker.status()["state"] == "ok"


def test_new_articles_join_existing_story_later(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS[:2])
    fake = FakeEmbedOllama()
    worker = make_worker(db, settings, fake)
    run(worker.step())
    first_story = StoryRepository(db).story_of(ids["a1"])
    ids.update(seed_articles(db, sources, articles, [("gamma-live", "g9", "Iran hormuz drone video", 1)]))
    run(worker.step())
    assert StoryRepository(db).story_of(ids["g9"]) == first_story


def test_threshold_controls_merging(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama(), threshold=0.95).step())
    repo = StoryRepository(db)
    # "Hormuz drone incident" vs "hormuz drone seized by Iran": same words -> still together at 0.95,
    # but nothing unrelated is merged.
    assert repo.story_of(ids["a2"]) != repo.story_of(ids["a1"])


def test_ollama_down_pauses_without_losing_work(db, sources, articles, settings):
    seed_articles(db, sources, articles, SPECS[:2])
    worker = make_worker(db, settings, FakeEmbedOllama(fail=True))
    assert run(worker.step()) > 0
    assert worker.status()["state"] == "unreachable"
    assert StoryRepository(db).counts()["embedded"] == 0


def test_manual_detach_and_merge_are_respected(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    fake = FakeEmbedOllama()
    worker = make_worker(db, settings, fake)
    run(worker.step())
    repo = StoryRepository(db)
    hormuz = repo.story_of(ids["a1"])

    new = repo.detach(ids["s1"])
    assert new != hormuz and story_members(repo, ids["s1"]) == {ids["s1"]}
    run(worker.step())  # automatic clustering must not pull it back
    assert repo.story_of(ids["s1"]) == new

    swiss = repo.story_of(ids["a2"])
    repo.merge(swiss, hormuz)
    assert repo.get(swiss) is None
    assert {ids["a2"], ids["b2"]} <= story_members(repo, ids["a1"])
    with pytest.raises(KeyError):
        repo.merge(99999, hormuz)
    with pytest.raises(KeyError):
        repo.detach(99999)


def test_detaching_the_only_member_removes_the_empty_story(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama()).step())
    repo = StoryRepository(db)
    lonely = repo.story_of(ids["a3"])
    repo.detach(ids["a3"])
    assert repo.get(lonely) is None


def test_model_switch_drops_incomparable_vectors(db, sources, articles, settings):
    seed_articles(db, sources, articles, SPECS[:2])
    fake = FakeEmbedOllama()
    run(make_worker(db, settings, fake).step())
    settings.set("stories.embed_model", "embeddinggemma:latest")
    run(StoryWorker(StoryRepository(db), settings, client_factory=fake.client).step())
    rows = db.conn.execute("SELECT DISTINCT model FROM article_embeddings").fetchall()
    assert [r[0] for r in rows] == ["embeddinggemma:latest"]
    assert fake.requests[-1]["input"][0].startswith("task: clustering | query: ")


def test_story_filters(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama()).step())
    repo = StoryRepository(db)
    assert repo.list(StoryFilter(min_sources=2))[1] == 2
    assert repo.list(StoryFilter(regions=["asia"]))[1] == 1  # only the Hormuz story has Gamma Live
    assert repo.list(StoryFilter(query="neutrality"))[0][0]["id"] == repo.story_of(ids["a2"])
    assert repo.list(StoryFilter(query="!!!")) == ([], 0)
    # Most recent activity: the Hormuz story's latest report is 20 minutes old.
    assert repo.list(StoryFilter(sort="recent"))[0][0]["id"] == repo.story_of(ids["a1"])


# -- story AI -----------------------------------------------------------------------------------
STORY_ANSWER = {
    "title_tr": "İran, Hürmüz'de ABD'ye ait insansız aracı ele geçirdi",
    "summary_tr": "İran, Hürmüz Boğazı'nda ABD'ye ait bir insansız aracı ele geçirdi. Olay birçok kaynakta yer aldı.",
    "category": "conflict_defense",
    "why_meeting_tr": "Olay 3 bağımsız kaynakta geçiyor.",
    "title_en": "Iran seizes US drone in Hormuz",
    "summary_en": "Iran seized a US drone in the Strait of Hormuz. The incident was widely reported.",
    "why_meeting_en": "The event is covered by 3 independent outlets.",
}


class FakeChat:
    def __init__(self, answer=STORY_ANSWER):
        self.answer = answer
        self.prompts: list[str] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        body = json.loads(request.content)
        self.prompts.append(body["messages"][1]["content"])
        answer = self.answer
        if "Reports:" not in body["messages"][1]["content"]:  # article job
            answer = {"title_tr": "Başlık", "summary_tr": "Özet.", "category": "other", "countries": [],
                      "mentions_turkey": False, "topics": []}
        return httpx.Response(200, json={"message": {"content": json.dumps(answer, ensure_ascii=False)},
                                         "total_duration": 1, "eval_count": 1, "eval_duration": 1})

    def client(self, url="http://localhost:11434"):
        return OllamaClient(url, transport=httpx.MockTransport(self.handler))


def test_story_summaries_come_first_and_by_score(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama()).step())
    repo = StoryRepository(db)
    chat = FakeChat()
    settings.set("ai.model", "gemma4-26b-a4b:latest")
    ai_worker = AiWorker(AiRepository(db), settings, client_factory=chat.client, stories=repo)
    run(ai_worker.step())
    hormuz = repo.get(repo.story_of(ids["a1"]))
    assert hormuz["ai_status"] == "done" and hormuz["ai_title_tr"] == STORY_ANSWER["title_tr"]
    assert hormuz["ai_article_count"] == 4 and hormuz["ai_issues"] == []
    assert "3 independent outlets" in chat.prompts[0]
    # One report per outlet first.
    assert chat.prompts[0].count("[") >= 4

    run(ai_worker.step())  # the Swiss story (2 sources) next
    assert repo.get(repo.story_of(ids["a2"]))["ai_status"] == "done"
    run(ai_worker.step())  # single-source story is not summarised -> an article job instead
    assert repo.get(repo.story_of(ids["a3"]))["ai_status"] is None
    assert "Reports:" not in chat.prompts[-1]


def test_story_summary_flags_invented_numbers_and_user_requests(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama()).step())
    repo = StoryRepository(db)
    settings.set("ai.model", "m")
    chat = FakeChat({**STORY_ANSWER, "summary_tr": "Olayda 12 kişi yaralandı.", "why_meeting_tr": "Önemli.", "why_meeting_en": "Important."})
    worker = AiWorker(AiRepository(db), settings, client_factory=chat.client, stories=repo)
    lonely = repo.story_of(ids["a3"])
    repo.request_summary(lonely)
    run(worker.step())
    story = repo.get(lonely)
    assert story["ai_status"] == "done" and story["ai_issues"] == ["number_not_in_source:12"]
    with pytest.raises(KeyError):
        repo.request_summary(99999)


def test_story_summary_is_refreshed_when_story_grows(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS[:2])
    fake = FakeEmbedOllama()
    story_worker = make_worker(db, settings, fake)
    run(story_worker.step())
    repo = StoryRepository(db)
    settings.set("ai.model", "m")
    worker = AiWorker(AiRepository(db), settings, client_factory=FakeChat().client, stories=repo)
    run(worker.step())
    sid = repo.story_of(ids["a1"])
    since = (NOW - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert repo.next_story_job(since, 2) is None
    seed_articles(db, sources, articles, [("gamma-live", "g5", "hormuz drone new footage", 2),
                                          ("gamma-live", "g6", "hormuz drone reaction", 1)])
    run(story_worker.step())
    assert repo.get(sid)["article_count"] == 4
    assert repo.next_story_job(since, 2)["id"] == sid


def test_story_summaries_wait_while_reports_are_still_being_matched(db, sources, articles, settings, monkeypatch):
    """First start: thousands of reports are matched into stories over several minutes and stories keep
    growing. Automatic summaries wait until matching has caught up; a summary the user asked for does not."""
    import worldsignal.ai.worker as ai_mod

    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama()).step())
    repo = StoryRepository(db)
    settings.set("ai.model", "m")
    chat = FakeChat()
    worker = AiWorker(AiRepository(db), settings, client_factory=chat.client, stories=repo)
    since = (NOW - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    seed_articles(db, sources, articles, [("gamma-live", f"late{i}", f"unmatched report {i}", 1) for i in range(3)])
    assert repo.embedding_backlog(since) == 3
    monkeypatch.setattr(ai_mod, "STORY_BACKLOG_LIMIT", 2)
    run(worker.step())
    assert "Reports:" not in chat.prompts[-1]  # an article instead of a story summary
    assert repo.get(repo.story_of(ids["a1"]))["ai_status"] is None
    swiss = repo.story_of(ids["a2"])
    repo.request_summary(swiss)
    run(worker.step())
    assert repo.get(swiss)["ai_status"] == "done"  # the user's request is not held back
    assert repo.next_story_job(since, 2, automatic=False) is None
    monkeypatch.setattr(ai_mod, "STORY_BACKLOG_LIMIT", 100)
    run(worker.step())
    assert repo.get(repo.story_of(ids["a1"]))["ai_status"] == "done"


@pytest.mark.parametrize("kind", ["story", "ai"])
def test_wake_during_a_step_is_not_lost(db, settings, kind):
    """A wake() that arrives while a step runs (e.g. the collector stored new articles) starts the
    next step right away instead of after the idle delay."""
    worker = StoryWorker(StoryRepository(db), settings) if kind == "story" else AiWorker(AiRepository(db), settings)
    calls = []

    async def step():
        calls.append(1)
        if len(calls) == 1:
            worker.wake()
            await asyncio.sleep(0.01)  # the wake is delivered while the step is still running
            return 60
        raise asyncio.CancelledError

    worker.step = step

    async def scenario():
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(worker.run_forever(), timeout=5)

    run(scenario())
    assert len(calls) == 2


def test_representative_is_the_most_typical_report_not_an_outlier():
    from worldsignal.repo.stories import pick_representative, to_blob

    def row(aid, vec, title_tr=None, reliability=1.0):
        return {"id": aid, "vector": to_blob(vec) if vec is not None else None, "title_tr": title_tr,
                "reliability": reliability, "sort_at": f"2026-09-27T0{aid}:00:00Z"}

    rows = [
        row(1, [1.0, 0.1, 0.0]),
        row(2, [1.0, 0.0, 0.05]),
        row(3, [0.95, 0.05, 0.0]),
        row(4, [0.2, 0.0, 1.0], title_tr="Alakasız ama Türkçe", reliability=2.0),  # chained-in outlier
    ]
    assert pick_representative(rows) in (1, 2, 3)
    # Among typical reports, a Turkish title wins.
    rows[2]["title_tr"] = "Türkçe başlık"
    assert pick_representative(rows) == 3
    # No vectors at all: most reliable with a Turkish title.
    assert pick_representative([{**r, "vector": None} for r in rows]) == 4


def test_choose_story_requires_a_close_member_and_cohesion():
    from worldsignal.stories.worker import choose_story

    sims = np.array([0.9, 0.2, 0.1, 0.62, 0.6])
    stories = np.array([7, 7, 7, 8, 8])
    # Story 7 has one very close member but is otherwise unrelated (a chained story); story 8 is coherent.
    assert choose_story(sims, stories, 0.55, 0.0) == (7, 0.9)  # nearest-neighbour rule alone
    assert choose_story(sims, stories, 0.55, 0.45) == (8, 0.62)
    assert choose_story(sims, stories, 0.7, 0.45) == (None, None)
    assert choose_story(np.array([]), np.array([], dtype=np.int64), 0.5, 0.0) == (None, None)


def test_story_summaries_without_english_are_redone(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama()).step())
    repo = StoryRepository(db)
    sid = repo.story_of(ids["a1"])
    since = "2000-01-01T00:00:00Z"
    repo.store_story_ai(sid, title="Eski", summary="Eski özet.", why="w", category=None, issues=[], model="m",
                        article_count=4)  # written before English existed
    assert repo.next_story_job(since, 2)["id"] == sid
    settings.set("ai.model", "m")
    run(AiWorker(AiRepository(db), settings, client_factory=FakeChat().client, stories=repo).step())
    story = repo.get(sid)
    assert story["ai_title_en"] == "Iran seizes US drone in Hormuz" and story["ai_why_en"].startswith("The event")
