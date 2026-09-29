"""Statistics (repo/stats.py) on a small, known set of reports."""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from test_stories import NOW, SPECS, FakeEmbedOllama, make_worker, seed_articles
from worldsignal.collector.rss import ParsedEntry
from worldsignal.repo.stats import StatsRepository, period
from worldsignal.repo.stories import StoryRepository

LOCAL = timezone(timedelta(hours=3))


@pytest.fixture
def world(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    asyncio.run(make_worker(db, settings, FakeEmbedOllama()).step())
    stories = StoryRepository(db)
    return {"ids": ids, "db": db, "stats": StatsRepository(db, stories), "stories": stories, "articles": articles,
            "sources": sources}


def now_local():
    return (NOW + timedelta(seconds=1)).astimezone(LOCAL)


def test_periods_follow_the_local_clock():
    now = datetime(2026, 9, 29, 14, 35, tzinfo=LOCAL)
    day = period(24, now)
    assert day.origin == datetime(2026, 9, 28, 15, 0, tzinfo=LOCAL) and day.buckets == 24
    assert day.starts()[-1] == "2026-09-29T11:00:00Z"  # the current hour, in UTC
    week = period(168, now)
    assert week.origin == datetime(2026, 9, 23, 0, 0, tzinfo=LOCAL) and week.step == timedelta(days=1)
    # The previous period is as long as the elapsed part of this one.
    assert week.previous_start == week.origin - (now - week.origin)
    assert period(720, now).buckets == 30
    with pytest.raises(ValueError):
        period(48, now)


def test_overview_counts_reports_sources_and_shares(world):
    db, ids = world["db"], world["ids"]
    hormuz = world["stories"].story_of(ids["a1"])
    with db.transaction() as c:
        c.execute("UPDATE stories SET category = 'conflict_defense' WHERE id = ?", (hormuz,))
    o = world["stats"].overview(period(24, now_local()))
    # 7 reports; Beta Haber and Beta Sister are one media group, so 3 independent sources.
    assert o["totals"]["articles"] == 7 and o["totals"]["sources"] == 3
    assert o["totals"]["stories"] == len({world["stories"].story_of(i) for i in ids.values()})
    assert sum(b["articles"] for b in o["timeline"]) == 7 and len(o["timeline"]) == 24
    # Only the Hormuz story has a category: 4 of 7 reports.
    assert o["categories"]["known"] == 4 and o["categories"]["total"] == 7
    assert o["categories"]["items"] == [{"key": "conflict_defense", "articles": 4, "previous": 0}]
    assert {i["key"]: i["articles"] for i in o["regions"]["items"]} == {"europe": 3, "turkey": 3, "asia": 1}
    by_name = {s["name"]: s for s in o["sources"]}
    assert by_name["Alpha News"]["articles"] == 3 and by_name["Alpha News"]["stories"] == 3
    assert "Gamma Dead" not in by_name  # disabled sources are left out
    # Collection started with these reports: nothing to compare with yet.
    assert o["period"]["comparable"] is False and o["totals"]["previous"]["articles"] == 0


def test_the_previous_period_is_compared_once_collection_covers_it(world):
    beta = next(s for s in world["sources"].list_sources() if s["slug"] == "beta")
    # Collecting since 50 hours ago (before the previous period began); one report 30 hours ago.
    for key, ago in (("first", 50), ("old", 30)):
        at = NOW - timedelta(hours=ago)
        with world["db"].transaction() as c:
            world["articles"].insert_entries(c, source_id=beta["id"], feed_id=beta["feeds"][0]["id"], language="tr",
                                             now=at, entries=[ParsedEntry(key, f"https://x.example/{key}", "Eski haber",
                                                                          "", None, at)])
    o = world["stats"].overview(period(24, now_local()))
    assert o["period"]["comparable"] is True
    assert o["totals"]["previous"]["articles"] == 1
    assert {i["key"]: i["previous"] for i in o["regions"]["items"]}["turkey"] == 1


def test_rising_stories_grew_in_the_latest_window(world):
    ids = world["ids"]
    rising = world["stats"].overview(period(24, now_local()))["rising"]
    assert rising["window_hours"] == 6
    # Hormuz: 4 reports in the last 6 hours, from 3 independent sources. Neutrality has only 2 (below 3).
    assert [(i["story"]["id"], i["recent"], i["previous"], i["sources"]) for i in rising["items"]] == [
        (world["stories"].story_of(ids["a1"]), 4, 0, 3)]
    assert rising["items"][0]["story"]["members"] == []  # the card, not the reports


def test_a_topic_per_hour_with_its_translations(world):
    stats = world["stats"]
    p = period(24, now_local())
    t = stats.topic(p, "hormuz")
    assert t["articles"] == 4 and t["sources"] == 3 and t["previous"] == 0
    busiest = max(t["buckets"], key=lambda b: b["articles"])
    assert 0 < busiest["share"] <= 1
    assert sum(b["articles"] for b in t["buckets"]) == 4
    # The Turkish word alone finds nothing; with its translation it finds the Swiss reports.
    assert stats.topic(p, "tarafsızlık")["articles"] == 0
    assert stats.topic(p, "tarafsızlık", ["neutrality"])["articles"] == 2
    assert stats.topic(p, "!!!") is None
