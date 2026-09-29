"""A story names the outlet that reported it first, and where the outlets contradict each other (0.13.2)."""

import json

from test_ai_depth import FakeModel, ai_worker, run, world  # noqa: F401  (world is a fixture)
from test_stories import STORY_ANSWER
from worldsignal.ai.story import StoryReport, story_prompt, story_schema, validate_story

DISAGREE = "Reuters 12 ölü, Al Jazeera ise 20 ölü bildirdi."


def test_the_story_prompt_asks_for_a_conflict_only_when_outlets_contradict_each_other():
    schema = story_schema(("tr", "en"))
    assert {"conflict_tr", "conflict_en"} <= set(schema["properties"])
    prompt = story_prompt(("tr", "en"))
    assert "conflict_tr" in prompt and "contradict" in prompt and "empty string" in prompt


def test_a_stored_conflict_is_read_per_language_and_missing_ones_are_empty():
    reports = [StoryReport("Reuters", "en", "Blast", "Twelve died.")]
    answer = {**STORY_ANSWER, "conflict_tr": "Reuters 12 ölü bildirdi, Al Jazeera 20.", "conflict_en": "Reuters says 12."}
    written = validate_story(answer, reports, 1)
    assert written.texts["tr"]["conflict"].startswith("Reuters 12") and written.texts["en"]["conflict"] == "Reuters says 12."
    assert validate_story(STORY_ANSWER, reports, 1).texts["tr"]["conflict"] == ""  # the model left it out


def test_the_worker_stores_the_conflict_and_the_story_names_who_was_first(world):
    ids, stories = world["ids"], world["stories"]
    hormuz = stories.story_of(ids["a1"])
    model = FakeModel({**STORY_ANSWER, "conflict_tr": DISAGREE, "conflict_en": "", "countries": [], "topics": [],
                       "mentions_turkey": False})
    run(ai_worker(world, model, "stories").step())
    story = stories.get(hormuz)
    assert story["ai_texts"]["tr"]["conflict"] == DISAGREE and story["ai_texts"]["en"]["conflict"] == ""
    # SPECS: Alpha reported the Hormuz drone first (50 minutes ago), Beta 40, Gamma Live 30.
    assert story["first"]["source"] == "Alpha News" and json.dumps(story["first"])
    # A story with one outlet has no "first".
    storm = stories.get(stories.story_of(ids["a3"]))
    assert storm["first"] is None
