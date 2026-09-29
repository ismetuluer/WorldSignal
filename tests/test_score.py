from datetime import UTC, datetime, timedelta

from worldsignal.stories.score import REGION_CAP, Interest, Member, counted_sources, independent_sources, score_story
from worldsignal.stories.worker import weights_from

NOW = datetime(2026, 9, 27, 12, 0, tzinfo=UTC)


def m(i, owner, hours_ago=1.0, rel=1.0, region="europe", text="", turkey=None, category=None):
    return Member(i, owner, rel, NOW - timedelta(hours=hours_ago), region, text, category, turkey)


def test_same_media_group_counts_once():
    members = [m(1, "Turkuvaz"), m(2, "Turkuvaz", rel=1.5), m(3, "BBC")]
    assert independent_sources(members) == {"Turkuvaz": 1.5, "BBC": 1.0}
    r = score_story(members, NOW)
    assert r.source_count == 2
    assert {"kind": "sources", "count": 2} in r.tags


def test_more_independent_sources_score_higher():
    few = score_story([m(1, "A"), m(2, "B")], NOW)
    many = score_story([m(i, f"S{i}") for i in range(9)], NOW)
    same_group = score_story([m(i, "Turkuvaz") for i in range(9)], NOW)
    assert many.score > few.score > 0
    assert same_group.source_count == 1 and same_group.score < few.score


def test_freshness_decays_and_spreading_tag():
    fresh = score_story([m(i, f"S{i}", hours_ago=0.5) for i in range(4)], NOW)
    old = score_story([m(i, f"S{i}", hours_ago=30) for i in range(4)], NOW)
    assert fresh.score > old.score
    assert {"kind": "spreading", "count": 4, "hours": 3} in fresh.tags
    assert not any(t["kind"] == "spreading" for t in old.tags)
    assert {"kind": "age", "hours": 30.0} in old.tags


def test_turkey_relevance_takes_strongest_member():
    r = score_story([m(1, "A", turkey="none"), m(2, "B", turkey="indirect"), m(3, "C", turkey="direct")], NOW)
    assert r.turkey_relevance == "direct" and r.components["turkey"] == 1.0
    assert {"kind": "turkey", "level": "direct"} in r.tags
    base = score_story([m(1, "A"), m(2, "B"), m(3, "C")], NOW)
    assert r.score > base.score


def test_interest_profile_matches_keywords_turkish_aware_categories_and_regions():
    interest = Interest(keywords=["İSRAİL", "doğalgaz", "yok"], categories=["energy"], regions=["middle_east"])
    members = [m(1, "A", text="Irak ve israil arasında DOĞALGAZ anlaşması", region="middle_east")]
    r = score_story(members, NOW, interest=interest, category="energy")
    tag = next(t for t in r.tags if t["kind"] == "interest")
    assert tag["matches"] == ["İSRAİL", "doğalgaz", "category:energy"]
    assert r.components["interest"] == 1.0


def test_weights_are_configurable_and_score_is_bounded():
    members = [m(i, f"S{i}", hours_ago=0, turkey="direct") for i in range(20)]
    r = score_story(members, NOW, interest=Interest(keywords=["x"]))
    assert 0 <= r.score <= 100
    only_turkey = score_story([m(1, "A", hours_ago=100, turkey="direct")], NOW,
                              weights={"sources": 0, "freshness": 0, "turkey": 1, "interest": 0})
    assert only_turkey.score == 100.0
    assert score_story([], NOW).score == 0.0


def test_my_country_off_leaves_the_country_link_out_of_the_score():
    prefs = {"score.w_sources": 0.45, "score.w_freshness": 0.25, "score.w_turkey": 0.2, "score.w_interest": 0.1}
    assert weights_from(prefs)["turkey"] == 0.2
    assert weights_from({**prefs, "home.enabled": True})["turkey"] == 0.2
    off = weights_from({**prefs, "home.enabled": False})
    assert off == {"sources": 0.45, "freshness": 0.25, "turkey": 0.0, "interest": 0.1}


def test_one_region_cannot_fill_the_source_count_alone():
    """Many outlets from one region (the user's own press) count at most REGION_CAP; the rest need other regions."""
    home = [m(i, f"TR{i}", region="turkey") for i in range(14)]
    assert counted_sources(home) == REGION_CAP
    world = [m(i, f"W{i}", region=r) for i, r in enumerate(["europe", "asia", "middle_east", "north_america"] * 3)]
    local_story, world_story = score_story(home, NOW), score_story(world, NOW)
    assert local_story.source_count == 14 and world_story.source_count == 12
    assert world_story.score > local_story.score
    # The most reliable outlets of a region are the ones counted; a media group still counts once.
    mixed = [m(1, "A", rel=1.5, region="turkey"), m(2, "A", rel=1.0, region="turkey")] +         [m(i, f"B{i}", rel=0.5, region="turkey") for i in range(3, 3 + REGION_CAP)]
    assert counted_sources(mixed) == 1.5 + 0.5 * (REGION_CAP - 1)
