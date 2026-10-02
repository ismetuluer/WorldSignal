"""Key points for the meeting (0.13.4): the story summary lists the names, figures and statements, and the stories on
today's meeting list get them first."""

from test_ai_depth import FakeModel, ai_worker, run, world  # noqa: F401  (world is a fixture)
from test_stories import STORY_ANSWER
from worldsignal.ai.story import MAX_POINTS, StoryReport, clean_points, story_prompt, story_schema, validate_story
from worldsignal.repo.notebook import NotebookRepository, local_today, story_snapshot

POINTS_TR = ["İran Devrim Muhafızları", "1 insansız araç", "ABD: \"Kabul edilemez\""]


def test_the_prompt_asks_for_short_points_from_the_reports_only():
    schema = story_schema(("tr", "en"))
    assert schema["properties"]["points_tr"]["type"] == "array" and "points_en" in schema["required"]
    prompt = story_prompt(("tr", "en"))
    assert "points_tr" in prompt and "names" in prompt and "figures" in prompt and "statements" in prompt
    assert "Use ONLY information present in the reports" in prompt


def test_points_are_kept_one_per_line_without_bullets_or_repeats():
    assert clean_points(["- Ankara", "2) 40 milyon $", "• Ankara", "  ", "*  Bakan:   açıklama "]) == [
        "Ankara", "40 milyon $", "Bakan: açıklama"]
    assert clean_points("not a list") == [] and clean_points(None) == []
    assert len(clean_points([f"nokta {i}" for i in range(9)])) == MAX_POINTS
    reports = [StoryReport("Reuters", "en", "Iran seizes drone", "Iran seized 1 drone.")]
    written = validate_story({**STORY_ANSWER, "points_tr": POINTS_TR, "points_en": []}, reports, 3)
    assert written.texts["tr"]["points"] == "\n".join(POINTS_TR) and written.texts["en"]["points"] == ""
    # A figure that is in no report is flagged, as in the summary.
    flagged = validate_story({**STORY_ANSWER, "points_tr": ["750 kişi gözaltında"]}, reports, 3)
    assert any("750" in issue for issue in flagged.issues)


def test_meeting_stories_get_their_points_first_even_when_summarised_before(world):
    ids, stories, db = world["ids"], world["stories"], world["db"]
    hormuz, storm = stories.story_of(ids["a1"]), stories.story_of(ids["a3"])
    old = {"tr": {"title": "Eski başlık", "summary": "Eski özet.", "why": "w", "conflict": ""}}
    stories.store_story_ai(hormuz, texts=old, category="conflict_defense", issues=[], model="m", article_count=4)
    nb = NotebookRepository(db, stories)
    nb.add_to_meeting(storm)  # a single-source story the automatic summaries never take
    nb.add_to_meeting(hormuz)  # summarised before key points existed
    assert "points" not in nb.meeting(local_today())[1]["texts"]["tr"]  # still to be written

    model = FakeModel({**STORY_ANSWER, "points_tr": POINTS_TR, "points_en": ["Iran's Revolutionary Guards"],
                       "countries": [], "topics": [], "mentions_turkey": False})
    worker = ai_worker(world, model, "fast")
    run(worker.step())
    run(worker.step())
    done = {s: stories.get(s)["ai_texts"] for s in (storm, hormuz)}
    assert all(t["tr"]["points"] == "\n".join(POINTS_TR) for t in done.values())
    story_calls = [c for c in model.calls if "points_tr" in c["format"]["properties"]]
    assert len(story_calls) == 2  # the list's order: the storm, then Hormuz
    items = nb.meeting(local_today())
    assert items[0]["texts"]["tr"]["points"].splitlines() == POINTS_TR

    # With points (even none) a story is not written again for them.
    assert stories.next_story_job("2000-01-01T00:00:00Z", 99, automatic=False, meeting_day=local_today()) is None


def test_the_meeting_lists_the_closest_sources_first():
    story = {
        "ai_status": "done", "ai_texts": {}, "category": None,
        "representative": {"id": 3, "title": "T", "ai_texts": {}},
        "members": [
            {"id": 1, "source_name": "Chained", "url": "https://c/1", "sort_at": "2026-09-27T01:00:00Z", "similarity": 0.58},
            {"id": 2, "source_name": "Close", "url": "https://b/1", "sort_at": "2026-09-27T02:00:00Z", "similarity": 0.91},
            {"id": 3, "source_name": "Lead", "url": "https://a/1", "sort_at": "2026-09-27T03:00:00Z", "similarity": None},
        ],
    }
    assert [s["name"] for s in story_snapshot(story)["sources"]] == ["Lead", "Close", "Chained"]
