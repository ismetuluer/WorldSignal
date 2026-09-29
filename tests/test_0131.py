"""0.13.1: "my country" off leaves the AI's country questions out, optional country labels, working hours,
and repairing headlines whose Turkish letters a feed delivered broken."""

import asyncio
from datetime import UTC, datetime

import pytest

from test_ai_depth import FakeModel, ai_worker, queued, run, world  # noqa: F401  (world is a fixture)
from test_repositories import NOW, entry, insert, seed
from worldsignal.ai.enrich import EnrichTask
from worldsignal.home_sync import HomeSync
from worldsignal.repo.history import HistoryRepository
from worldsignal.textnorm import repair_mojibake
from worldsignal.worktime import WorkHours, is_resting


# -- "my country" off ------------------------------------------------------------------------------
def test_country_questions_are_left_out_of_the_prompt_when_it_is_off():
    on, off = EnrichTask(("tr", "en")), EnrichTask(("tr", "en"), facts=False)
    assert {"countries", "mentions_turkey", "topics"} <= set(on.schema["properties"])
    assert not {"countries", "mentions_turkey", "topics"} & set(off.schema["properties"])
    assert "mentions_turkey" in on.system_prompt and "mentions_turkey" not in off.system_prompt
    assert "topics:" not in off.system_prompt and "countries:" not in off.system_prompt


def test_a_story_is_asked_no_country_questions_and_not_written_again_for_them(world):
    ids, stories, settings = world["ids"], world["stories"], world["settings"]
    settings.set("home.enabled", False)
    model = FakeModel()
    worker = ai_worker(world, model, "stories")
    run(worker.step())
    schema = model.calls[0]["format"]["properties"]
    assert "countries" not in schema and "mentions_turkey" not in schema
    hormuz = stories.story_of(ids["a1"])
    # An older summary without facts is left alone while it is off ...
    texts = {lang: {"title": "t", "summary": "s", "why": ""} for lang in ("tr", "en")}
    stories.store_story_ai(hormuz, texts=texts, category="other", issues=[], model="m", article_count=4)
    since = "2000-01-01T00:00:00Z"
    swiss = stories.story_of(ids["a2"])
    job = stories.next_story_job(since, 2, need_facts=False)
    assert job is None or job["id"] != hormuz
    # ... and written again for its facts once it is on.
    assert stories.next_story_job(since, 2, need_facts=True)["id"] in {hormuz, swiss}


def test_the_ai_worker_does_not_redo_summaries_for_facts_while_it_is_off(world):
    settings = world["settings"]
    model = FakeModel()
    run(ai_worker(world, model, "stories").step())  # Hormuz, with its facts
    settings.set("home.enabled", False)
    texts = {lang: {"title": "t", "summary": "s", "why": ""} for lang in ("tr", "en")}
    hormuz = world["stories"].story_of(world["ids"]["a1"])
    world["stories"].store_story_ai(hormuz, texts=texts, category="other", issues=[], model="m", article_count=4)
    with world["db"].transaction() as c:  # as an older summary: written without facts
        c.execute("UPDATE stories SET ai_countries = NULL WHERE id = ?", (hormuz,))
    before = len(model.calls)
    worker = ai_worker(world, model, "stories")
    settings.set("home.enabled", False)
    run(worker.step())  # the Swiss story, but not Hormuz again
    assert model.kinds()[before:] == ["story"]
    row = world["db"].conn.execute("SELECT ai_countries FROM stories WHERE id = ?", (hormuz,)).fetchone()
    assert row["ai_countries"] is None  # still without facts: nobody asked for them


# -- country labels ---------------------------------------------------------------------------------
def test_labels_are_not_rated_again_while_they_or_the_country_are_off(world):
    stories, settings = world["stories"], world["settings"]
    sync = HomeSync(world["home"], world["articles"], stories, settings)
    assert sync.sync() is not None  # first time: everything is rated
    settings.set("home.country", "JP")
    settings.set("home.labels", False)
    assert sync.sync() is None  # the country changed, labels are off: nothing happens
    settings.set("home.labels", True)
    settings.set("home.enabled", False)
    assert sync.sync() is None
    settings.set("home.enabled", True)
    assert sync.sync() is not None  # switched on again: what changed meanwhile is rated now


# -- working hours -------------------------------------------------------------------------------------
@pytest.mark.parametrize("hour,resting", [(3, True), (6, True), (7, False), (12, False), (22, False), (23, True)])
def test_working_hours_rest_outside_the_window(hour, resting):
    prefs = {"work.limited": True, "work.start": 7, "work.end": 23}
    assert is_resting(prefs, hour) is resting
    assert not is_resting({**prefs, "work.limited": False}, hour)  # default: always working


def test_working_hours_may_wrap_past_midnight_and_equal_times_mean_all_day():
    night_shift = {"work.limited": True, "work.start": 20, "work.end": 6}
    assert [is_resting(night_shift, h) for h in (5, 6, 12, 19, 20, 23)] == [False, True, True, True, False, False]
    assert not any(is_resting({"work.limited": True, "work.start": 8, "work.end": 8}, h) for h in range(24))


def test_work_hours_follow_the_clock_and_the_settings(settings):
    now = datetime(2026, 9, 29, 3, 0, tzinfo=UTC)
    work = WorkHours(settings, clock=lambda: now, zone=UTC)
    assert not work.resting()
    settings.set_many({"work.limited": True, "work.start": 7, "work.end": 23})
    assert work.resting()


def test_the_collector_rests_outside_working_hours_but_scan_now_overrides(db, sources, articles):
    from worldsignal.collector.service import Collector

    class Client:
        pass

    resting = {"on": True}
    collector = Collector(db, sources, articles, resting=lambda: resting["on"])
    seed(sources)
    assert asyncio.run(collector.run_cycle(Client())) == 0
    assert collector.status()["resting"] is True
    fetched = []

    async def fake_fetch(client, url, *args, **kwargs):
        fetched.append(url)
        raise __import__("worldsignal.collector.rss", fromlist=["FetchError"]).FetchError("network", "test")

    import worldsignal.collector.service as service
    original = service.fetch_feed
    service.fetch_feed = fake_fetch
    try:
        collector.request_run()  # "scan now"
        asyncio.run(collector.run_cycle(Client()))
        assert fetched  # it read the feeds although it was resting
        assert collector.status()["resting"] is False
    finally:
        service.fetch_feed = original


def test_resting_the_ai_only_does_what_the_user_asked_for(world):
    settings, ai = world["settings"], world["ai"]
    ids = world["ids"]
    ai.enqueue_recent("2000-01-01T00:00:00Z", None)
    ai.request(ids["a3"])
    model = FakeModel()
    worker = ai_worker(world, model, "full")
    worker.resting = lambda: True
    run(worker.step())
    assert model.kinds() == ["report"]  # the one the user asked for
    assert not model.calls[0]["messages"][1]["content"].startswith("Reports:")
    run(worker.step())
    run(worker.step())
    assert len(model.calls) == 1 and worker.status()["state"] == "resting"
    worker.resting = lambda: False
    run(worker.step())
    assert len(model.calls) == 2  # back to work: the queue continues


def test_resting_full_text_reads_only_the_users_requests(db, sources, articles):
    from worldsignal.repo.fulltext import FullTextRepository

    by_slug = seed(sources)
    insert(db, articles, by_slug["alpha"], [entry("x1", "Alpha one"), entry("x2", "Alpha two")])
    repo = FullTextRepository(db)
    first, second = [r[0] for r in db.conn.execute("SELECT id FROM articles ORDER BY id")]
    repo.enqueue([first], "auto")
    assert repo.next_job(NOW, 10, user_only=True) is None
    assert repo.next_job(NOW, 10) is not None
    repo.request(second)
    assert repo.next_job(NOW, 10, user_only=True).article_id == second


# -- broken Turkish letters --------------------------------------------------------------------------------
@pytest.mark.parametrize("broken,fixed", [
    ("SoykÄ±rÄ±m", "Soykırım"),
    ("petrolÃ¼n", "petrolün"),
    ("Ãœlke ÅŸimdi Ä°stanbul ÄŸ", "Ülke şimdi İstanbul ğ"),
    ("BelÃ§ika yaÄŸÄ±ÅŸlÄ±", "Belçika yağışlı"),
])
def test_repair_mojibake(broken, fixed):
    assert repair_mojibake(broken) == fixed


@pytest.mark.parametrize("text", [
    "Soykırım", "Belçika saldırıları", "Café Ã olé", "Ã", "", "Ankara", "Ä ±",
])
def test_repair_leaves_correct_text_alone(text):
    assert repair_mojibake(text) == text
    assert repair_mojibake(None) == ""


def test_stored_headlines_are_repaired_once_with_their_search_index(db, sources, articles):
    by_slug = seed(sources)
    insert(db, articles, by_slug["beta"], [
        entry("m1", "SoykÄ±rÄ±m davasÄ±", summary="Ãœlke gÃ¼ndemi"),
        entry("m2", "Normal başlık"),
    ])
    history = HistoryRepository(db, __import__("worldsignal.repo.stories", fromlist=["StoryRepository"]).StoryRepository(db))
    # The feed parser repairs new reports; these two were stored before, as the broken text.
    with db.transaction() as c:
        c.execute("UPDATE articles SET title = ? WHERE dedupe_key = 'm1'", ("SoykÄ±rÄ±m davasÄ±",))
    assert history.repair_mojibake() >= 0
    titles = sorted(r[0] for r in db.conn.execute("SELECT title FROM articles"))
    assert not any("Ä" in t for t in titles)
    assert history.repair_mojibake() == 0  # nothing left to do the second time
    found = db.conn.execute(
        "SELECT COUNT(*) FROM articles_fts WHERE articles_fts MATCH ?", ('"soykirim"',)).fetchone()[0]
    assert found == 1


def test_the_feed_parser_repairs_broken_letters():
    from worldsignal.collector.rss import parse_feed

    broken_title = "SoykÄ±rÄ±m davasÄ±"
    xml = (f'<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel><title>T</title><item>'
           f"<title>{broken_title}</title><link>https://x.example/1</link>"
           f"<description>{broken_title}</description></item></channel></rss>").encode("utf-8")
    feed = parse_feed(xml)
    assert feed.entries[0].title == "Soykırım davası"
    assert feed.entries[0].summary == "Soykırım davası"
