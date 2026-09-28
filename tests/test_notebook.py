"""Notebook: story notes, meeting list, day notes, and how they survive story changes."""

import pytest

from test_stories import SPECS, FakeEmbedOllama, make_worker, run, seed_articles
from worldsignal.repo.notebook import MAX_COMMENT, NotebookRepository, story_snapshot, valid_day
from worldsignal.repo.stories import StoryRepository

TODAY = "2026-09-27"


@pytest.fixture
def world(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama()).step())
    stories = StoryRepository(db)
    day = {"value": TODAY}
    nb = NotebookRepository(db, stories, today=lambda: day["value"])
    return {
        "nb": nb, "stories": stories, "day": day, "db": db,
        "hormuz": stories.story_of(ids["a1"]), "swiss": stories.story_of(ids["a2"]), "storm": stories.story_of(ids["a3"]),
        "ids": ids,
    }


def test_valid_day():
    assert valid_day("2026-09-27") and valid_day("2024-02-29")
    assert not valid_day("2026-02-30") and not valid_day("27.09.2026") and not valid_day("2026-9-7")


def test_story_note_create_update_delete(world):
    nb, sid = world["nb"], world["hormuz"]
    assert nb.story_note(sid) is None
    note = nb.save_story_note(sid, "İlk not: Hürmüz'de ıslak imza, ŞÇĞÜÖİ")
    assert note["body"].startswith("İlk not") and note["day"] == TODAY and note["title"]
    world["day"]["value"] = "2026-09-28"
    note2 = nb.save_story_note(sid, "Güncellendi")
    assert note2["id"] == note["id"] and note2["day"] == TODAY  # stays filed under the day it was started
    assert nb.save_story_note(sid, "   \n") is None and nb.story_note(sid) is None
    with pytest.raises(KeyError):
        nb.save_story_note(99999, "x")
    long = nb.save_story_note(sid, "a" * 50_000)
    assert len(long["body"]) == 20_000


def test_meeting_list_add_order_comment_remove(world):
    nb = world["nb"]
    a = nb.add_to_meeting(world["hormuz"])
    b = nb.add_to_meeting(world["swiss"])
    c = nb.add_to_meeting(world["storm"])
    assert nb.add_to_meeting(world["hormuz"])["id"] == a["id"]  # idempotent
    assert [i["id"] for i in nb.meeting(TODAY)] == [a["id"], b["id"], c["id"]]
    assert a["sources"] and {"name", "url"} <= set(a["sources"][0])

    nb.reorder(TODAY, [c["id"], a["id"], b["id"]])
    assert [i["position"] for i in nb.meeting(TODAY)] == [0, 1, 2]
    assert [i["id"] for i in nb.meeting(TODAY)] == [c["id"], a["id"], b["id"]]
    with pytest.raises(ValueError):
        nb.reorder(TODAY, [c["id"], a["id"]])  # missing an item
    with pytest.raises(ValueError):
        nb.reorder(TODAY, [c["id"], a["id"], b["id"], b["id"]])

    assert nb.update_item(a["id"], "  Açılışta verilmeli  ")["comment"] == "Açılışta verilmeli"
    assert len(nb.update_item(a["id"], "x" * 1000)["comment"]) == MAX_COMMENT
    nb.remove_item(c["id"])
    assert [(i["id"], i["position"]) for i in nb.meeting(TODAY)] == [(a["id"], 0), (b["id"], 1)]
    assert sorted(nb.meeting_story_ids(TODAY)) == sorted([world["hormuz"], world["swiss"]])
    with pytest.raises(KeyError):
        nb.remove_item(c["id"])

    # A new day starts an empty list; yesterday's stays in the notebook.
    world["day"]["value"] = "2026-09-28"
    assert nb.meeting("2026-09-28") == []
    assert len(nb.meeting(TODAY)) == 2


def test_todays_list_follows_the_story_but_past_days_keep_their_snapshot(world):
    nb, stories, db = world["nb"], world["stories"], world["db"]
    item = nb.add_to_meeting(world["hormuz"])
    assert item["texts"] == {}  # no AI summary yet (original text is never copied)
    stories.store_story_ai(world["hormuz"], texts={
        "tr": {"title": "Hürmüz'de İHA krizi", "summary": "Türkçe özet.", "why": "Enerji için kritik."},
        "en": {"title": "Drone crisis in Hormuz", "summary": "English summary.", "why": "Key for energy."},
    }, category="conflict_defense", issues=[], model="m", article_count=4)
    fresh = nb.meeting(TODAY)[0]
    assert fresh["texts"]["en"] == {"title": "Drone crisis in Hormuz", "summary": "English summary.", "why": "Key for energy."}
    assert fresh["texts"]["tr"] == {"title": "Hürmüz'de İHA krizi", "summary": "Türkçe özet.", "why": "Enerji için kritik."}
    assert fresh["title"] == "Hürmüz'de İHA krizi"

    world["day"]["value"] = "2026-09-28"
    stories.store_story_ai(world["hormuz"], texts={"tr": {"title": "Yeni başlık", "summary": "Yeni özet.", "why": "w"}},
                           category="conflict_defense", issues=[], model="m", article_count=4)
    assert nb.meeting(TODAY)[0]["title"] == "Hürmüz'de İHA krizi"  # that morning's proposal as it was
    with db.transaction() as c:
        c.execute("DELETE FROM stories WHERE id = ?", (world["hormuz"],))
    past = nb.meeting(TODAY)[0]
    assert past["story_id"] is None and past["title"] == "Hürmüz'de İHA krizi"


def test_merge_moves_notes_and_meeting_items(world):
    nb, stories = world["nb"], world["stories"]
    nb.save_story_note(world["swiss"], "İsviçre notu")
    nb.save_story_note(world["hormuz"], "Hürmüz notu")
    nb.add_to_meeting(world["swiss"])
    nb.update_item(nb.add_to_meeting(world["hormuz"])["id"], "birinci")
    nb.update_item(nb.meeting(TODAY)[0]["id"], "ikinci")
    stories.merge(world["swiss"], world["hormuz"])
    assert nb.story_note(world["hormuz"])["body"] == "Hürmüz notu\n\nİsviçre notu"
    assert nb.story_note(world["swiss"]) is None
    items = nb.meeting(TODAY)
    assert len(items) == 1 and items[0]["story_id"] == world["hormuz"] and items[0]["position"] == 0
    assert items[0]["comment"] == "birinci ikinci"

    # Merge into a story without a note or item: they simply move.
    nb.save_story_note(world["storm"], "Fırtına")
    swiss_like = world["storm"]
    stories.merge(swiss_like, world["hormuz"])
    assert "Fırtına" in nb.story_note(world["hormuz"])["body"]


def test_day_notes_and_calendar(world):
    nb = world["nb"]
    assert nb.save_day_note(TODAY, "Sabah toplantısı: ekonomi ağırlıklı") ["body"].startswith("Sabah")
    nb.save_story_note(world["hormuz"], "not")
    nb.add_to_meeting(world["swiss"])
    world["day"]["value"] = "2026-10-01"
    nb.add_to_meeting(world["storm"])
    assert nb.days("2026-09") == [{"day": TODAY, "notes": 1, "meeting": 1, "day_note": True}]
    assert nb.days("2026-10") == [{"day": "2026-10-01", "notes": 0, "meeting": 1, "day_note": False}]
    day = nb.day(TODAY)
    assert day["day_note"]["body"].startswith("Sabah") and len(day["notes"]) == 1 and len(day["meeting"]) == 1
    assert day["notes"][0]["story_exists"] is True and day["today"] == "2026-10-01"
    assert nb.save_day_note(TODAY, "") is None and nb.day(TODAY)["day_note"] is None
    assert nb.day("2020-01-01") == {"day": "2020-01-01", "today": "2026-10-01", "day_note": None, "meeting": [], "notes": []}


def test_snapshot_uses_only_ai_text():
    story = {
        "ai_status": None, "ai_texts": {}, "category": "politics",
        "representative": {"title": "Original headline", "ai_texts": {}, "summary": "Publisher text"},
        "members": [
            {"source_name": "A", "url": "https://a/2", "sort_at": "2026-09-27T02:00:00Z"},
            {"source_name": "A", "url": "https://a/1", "sort_at": "2026-09-27T01:00:00Z"},
            {"source_name": "B", "url": "https://b/1", "sort_at": "2026-09-27T03:00:00Z"},
        ],
    }
    snap = story_snapshot(story)
    assert snap["title"] == "Original headline" and snap["texts"] == {}
    # The representative report's AI text stands in for a story without its own summary.
    story["representative"]["ai_texts"] = {"pt": {"title": "Manchete", "summary": "Resumo."}}
    snap = story_snapshot(story)
    assert snap["title"] == "Manchete" and snap["texts"] == {"pt": {"title": "Manchete", "summary": "Resumo.", "why": ""}}
    assert snap["sources"] == [{"name": "A", "url": "https://a/1"}, {"name": "B", "url": "https://b/1"}]
