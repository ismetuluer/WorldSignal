""""My country" relevance (country.py) and keeping stored ratings in step (home_sync.py)."""

import pytest

from worldsignal.country import TOPICS, HomeState, countries, profile

TR = profile({"home.country": "TR"})
ZA = profile({"home.country": "ZA"})


def test_country_data_is_complete():
    data = countries()
    assert len(data) > 200 and {"KZ", "CY", "ZA", "US"} <= set(data)
    assert data["TR"]["label"]["tr"] == "Türkiye" and data["ZA"]["label"]["tr"] == "Güney Afrika"
    assert set(data["TR"]["neighbours"]) == {"AM", "AZ", "BG", "GE", "GR", "IQ", "IR", "SY"}  # land borders only
    assert "UA" not in data["TR"]["neighbours"] and "JP" not in data["US"]["neighbours"]


@pytest.mark.parametrize(
    ("countries_", "mentions", "topics", "text", "level", "links"),
    [
        # The rules World Signal had for Türkiye before 0.9, unchanged.
        (["GR"], False, [], "Coast guard rescues migrants off Lesbos", "indirect", ["neighbour:GR"]),
        (["AF", "PK"], False, [], "Pakistan rejects Afghan claims", "none", []),  # the benchmark's mistake
        (["IL"], False, [], "Visitors at Temple Mount", "none", []),
        (["RU", "UA"], False, [], "Russian strikes kill 2 in Ukraine", "none", []),  # a sea neighbour only
        (["RU", "UA"], False, ["black_sea"], "Drone attack on Black Sea fleet", "indirect", ["topic:black_sea"]),
        (["KZ"], False, [], "Kazakhstan elections", "indirect", ["related:KZ"]),
        (["CY"], False, [], "Nicosia talks", "indirect", ["neighbour:CY"]),
        (["AZ", "KZ"], False, [], "Pipeline deal", "indirect", ["neighbour:AZ", "related:KZ"]),
        ([], True, [], "Parliament recycling saves trees", "direct", ["home_mentioned"]),
        (["TR"], False, [], "Mardin'de kavga", "direct", ["home_mentioned"]),
        ([], False, [], "Deputy chair of Turkey's AK Party resigns", "direct", ["home_mentioned"]),
        ([], False, [], "Эрдоган: Турция готова", "direct", ["home_mentioned"]),
        ([], False, [], "Türkiye'nin ihracatı arttı", "direct", ["home_mentioned"]),
        ([], False, [], "US and China agree to meet again", "none", []),
        ([], False, [], "Greek islands fight wildfires", "none", []),  # neighbours come from the AI's list
    ],
)
def test_turkiye_rules(countries_, mentions, topics, text, level, links):
    assert TR.relevance(text, countries_, topics, mentions) == (level, links)


@pytest.mark.parametrize(("countries_", "text", "level", "links"), [
    (["ZA"], "Rand falls after budget", "direct", ["home_mentioned"]),
    ([], "South Africa wins the final", "direct", ["home_mentioned"]),  # its name in the text
    ([], "Güney Afrika'nın ihracatı arttı", "direct", ["home_mentioned"]),
    (["ZW"], "Zimbabwe holds elections", "indirect", ["neighbour:ZW"]),
    (["TR"], "Turkey quake kills dozens", "none", []),  # Türkiye's rules do not apply to a South African
    (["KZ"], "Kazakhstan elections", "none", []),
    (["NE"], "Niger coup", "none", []),
])
def test_any_country_works(countries_, text, level, links):
    assert ZA.relevance(text, countries_, []) == (level, links)
    assert ZA.relevance(text, countries_, [], mentions_home=False) == (level, links)


def test_the_ai_answer_about_turkiye_only_counts_for_turkiye():
    # The AI is asked whether Türkiye is mentioned; for other countries only its country list counts.
    assert TR.relevance("x", [], [], mentions_home=True)[0] == "direct"
    assert profile({"home.country": "NG"}).relevance("Niger coup", ["NE"], [])[0] == "indirect"  # a neighbour
    assert profile({"home.country": "NE"}).relevance("Nigeria votes", [], []) == ("none", [])  # "Niger" ≠ "Nigeria"


def test_defaults_and_user_choices():
    assert TR.related == ("AZ", "KZ", "UZ", "KG", "TM") and TR.topics == TOPICS
    assert set(TR.neighbours) == {"AM", "AZ", "BG", "GE", "GR", "IQ", "IR", "SY", "CY"}
    assert ZA.related == () and ZA.topics == ()
    mine = profile({"home.country": "ZA", "home.related": ["NG", "ZA", "XX"], "home.topics": ["migration", " ", "x"],
                    "home.keywords": ["Springboks", " "]})
    assert mine.related == ("NG",) and mine.topics == ("migration",) and mine.keywords == ("Springboks",)
    assert mine.relevance("Springboks win the final", [], []) == ("direct", ["home_mentioned"])
    assert mine.relevance("Lagos floods", ["NG"], []) == ("indirect", ["related:NG"])
    assert mine.relevance("Boats cross", ["IT"], ["migration"]) == ("indirect", ["topic:migration"])
    assert mine.key != ZA.key


def test_an_empty_country_follows_windows_and_unknown_codes_fall_back():
    assert profile({"home.country": ""}, system_country="DE").code == "DE"
    assert profile({"home.country": ""}, system_country=None).code == "TR"
    assert profile({"home.country": "XX"}).code == "TR"


def test_home_state_rebuilds_only_when_home_settings_change():
    prefs = {"home.country": "TR", "ai.enabled": True}
    state = HomeState(lambda: dict(prefs))
    first = state.profile()
    prefs["ai.enabled"] = False
    assert state.profile() is first
    prefs["home.country"] = "ZA"
    assert state.profile().code == "ZA"
