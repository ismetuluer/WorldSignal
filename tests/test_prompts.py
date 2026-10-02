"""The AI instructions the user can rewrite (ai/prompts.py): defaults unchanged, templates filled, the setting guarded."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from test_ai import FakeOllama, add_articles, make_worker, run  # noqa: F401  (shared helpers)
from test_api import H, client, ctx  # noqa: F401  (fixtures)
from worldsignal.ai import prompts, query, translate
from worldsignal.ai.enrich import EnrichTask, batch_prompt
from worldsignal.ai.story import story_prompt

GOLDEN = json.loads((Path(__file__).parent / "prompts_golden.json").read_text(encoding="utf-8"))


def current() -> dict[str, str]:
    tasks = {"a": EnrichTask(("tr", "en"), ("nato", "Futebol"), ask_turkey=True),
             "b": EnrichTask(("pt",), (), ask_turkey=False, facts=False),
             "c": EnrichTask(("tr", "ar", "en"), ("nato",), ask_turkey=False, with_summary=False)}
    out = {"story_none": story_prompt(("tr", "en"), None), "tr_de": translate.system_prompt("de"),
           "q": query.system_prompt(["en", "de", "ar"])}
    for name, task in tasks.items():
        out |= {f"sys_{name}": task.system_prompt, f"batch_{name}": batch_prompt(task), f"story_{name}": story_prompt(task.languages, task)}
    return out


def test_the_default_instructions_are_exactly_what_was_sent_before_templates_existed():
    assert current() == GOLDEN


def test_a_custom_article_template_is_filled_in():
    text = "Write like a wire service.\n{input}\nLanguages: {languages}\n{fields}"
    task = EnrichTask(("tr",), (), ask_turkey=False, facts=False, instructions={"article": text})
    out = task.system_prompt
    assert out.startswith("Write like a wire service.\nYou receive ONE news item")
    assert "Languages: Turkish" in out and "- title_tr:" in out and "{" not in out
    assert "several numbered" in batch_prompt(task)  # the batch keeps its own {input}


def test_missing_placeholders_are_added_because_the_model_cannot_work_without_them():
    task = EnrichTask(("tr",), (), ask_turkey=False, facts=False, instructions={"article": "Be brief."})
    out = task.system_prompt
    assert out.startswith("Be brief.\nYou receive ONE news item") and "Fields:\n- title_tr:" in out
    story = story_prompt(("tr",), None, {"story": "Edit the story."})
    assert story.startswith("Edit the story.") and "Fields:\n- title_tr:" in story


def test_unknown_braces_are_left_alone_and_blank_means_default():
    assert translate.system_prompt("de", {"translate": 'Into {language}. Answer {"translation": "..."} {x}'}) == \
        'Into German. Answer {"translation": "..."} {x}'
    assert translate.system_prompt("de", {"translate": "   "}) == GOLDEN["tr_de"]
    assert query.system_prompt(["en"], {"query": "Words into {languages}."}) == "Words into en = English."
    assert prompts.render("query", None, languages="x") == prompts.render("query", {}, languages="x")


def test_what_the_user_text_must_contain():
    assert prompts.problems("translate", "Translate it.") == ["no_language"]
    assert prompts.problems("query", "Translate it.") == ["no_languages"]
    assert prompts.problems("article", "x") == ["no_fields"]
    assert prompts.problems("article", "x{fields}") == []
    assert prompts.problems("article", "x{fields}" + "y" * prompts.MAX_CHARS) == ["too_long"]


def test_the_setting_is_guarded(client):
    ok = client.patch("/api/settings", headers=H, json={"ai.prompts": {"article": "Short.", "story": "  "}})
    assert ok.status_code == 200 and ok.json()["ai.prompts"] == {"article": "Short."}  # blank = default, dropped
    assert client.get("/api/settings", headers=H).json()["ai.prompts"] == {"article": "Short."}
    for bad in ({"nonsense": "x"}, {"translate": "no placeholder"}, {"query": "none"}, {"article": "y" * 7000}):
        assert client.patch("/api/settings", headers=H, json={"ai.prompts": bad}).status_code == 422
    assert client.patch("/api/settings", headers=H, json={"ai.prompts": {}}).json()["ai.prompts"] == {}
    assert client.get("/api/meta", headers=H).json()["ai_prompt_defaults"] == prompts.DEFAULTS


def test_the_worker_sends_the_users_instructions(db, sources, articles, settings):
    add_articles(db, sources, articles, n=1)
    fake = FakeOllama()
    worker = make_worker(db, settings, fake, **{"ai.prompts": {"article": "Custom desk rules.\n{input}\n{languages}\n{fields}"}})
    run(worker.step())
    sent = [json.loads(c.content) for c in fake.calls if c.url.path == "/api/chat"]
    assert sent and "Custom desk rules." in sent[0]["messages"][0]["content"]


# -- the material: layout of a report and the amounts sent ----------------------------------------------------------
from worldsignal.ai.enrich import EnrichInput, render_batch  # noqa: E402
from worldsignal.ai.story import StoryReport, pick_reports, render_reports  # noqa: E402


def test_the_default_layout_is_what_was_sent_before():
    inp = EnrichInput("Reuters", "en", " A headline ", "Body text.")
    assert inp.render() == "Source: Reuters\nLanguage: en\nHeadline: A headline\nText: Body text."
    assert EnrichInput("R", "en", "T", "T").render().endswith("Text: (no text besides the headline)")
    assert render_batch([inp, inp]).startswith("[1]\nSource: Reuters") and "\n\n[2]\n" in render_batch([inp, inp])
    reports = [StoryReport("BBC", "en", "Title", "Body"), StoryReport("AA", "tr", "Baslik", "Baslik")]
    assert render_reports(reports, 2) == ("The event is covered by 2 independent outlets. Reports:\n\n"
                                          "[1] BBC (en): Title\nBody\n\n[2] AA (tr): Baslik")


def test_a_custom_layout_and_limits_are_used():
    task = EnrichTask(inputs={"article": "<<{source}>> {title} // {text}"}, limits={"article_chars": 200, "batch_chars": 100})
    inp = EnrichInput("Reuters", "en", "Head", "x" * 500)
    assert inp.render(task) == "<<Reuters>> Head // " + "x" * 200 + " …"
    assert render_batch([inp], task) == "[1]\n<<Reuters>> Head // " + "x" * 100  # cut as before, without a mark
    story = EnrichTask(inputs={"story_intro": "{count} outlets:", "story_report": "{n}. {source}: {title} | {text}"},
                       limits={"story_reports": 2, "story_report_chars": 100})
    members = [{"source_name": f"S{i}", "language": "en", "title": f"T{i}", "summary": "y" * 300} for i in range(5)]
    picked = pick_reports(members, story)
    assert len(picked) == 2
    assert render_reports(picked, 5, story) == "5 outlets:\n\n1. S0: T0 | " + "y" * 100 + "\n\n2. S1: T1 | " + "y" * 100


def test_limits_stay_inside_their_range_and_unknown_braces_survive():
    assert prompts.limit({"batch_size": 1000}, "batch_size") == 25 and prompts.limit({"batch_size": 0}, "batch_size") == 2
    assert prompts.limit({"batch_size": True}, "batch_size") == 10 and prompts.limit(None, "story_reports") == 8
    assert prompts.render_input("article", {"article": "{title} {x} {n}"}, title="T", n=3) == "T {x} {n}"  # {n} is not an article field
    assert prompts.render_input("article", {"article": "  "}, source="S", language="l", title="T", text="x") == \
        "Source: S\nLanguage: l\nHeadline: T\nText: x"


def test_the_material_settings_are_guarded(client):
    ok = client.patch("/api/settings", headers=H, json={"ai.inputs": {"article": "{title}: {text}", "story_intro": " "},
                                                        "ai.limits": {"batch_size": 5}})
    assert ok.status_code == 200 and ok.json()["ai.inputs"] == {"article": "{title}: {text}"} and ok.json()["ai.limits"] == {"batch_size": 5}
    for bad in ({"ai.inputs": {"nonsense": "x"}}, {"ai.inputs": {"article": "no title here"}}, {"ai.inputs": {"article": "{title}" + "x" * 1100}},
                {"ai.limits": {"batch_size": 1}}, {"ai.limits": {"batch_size": 99}}, {"ai.limits": {"nope": 5}}):
        assert client.patch("/api/settings", headers=H, json=bad).status_code == 422
    meta = client.get("/api/meta", headers=H).json()
    assert meta["ai_input_defaults"] == prompts.INPUT_DEFAULTS and meta["ai_limit_ranges"]["batch_size"] == [10, 2, 25]


def test_the_worker_uses_the_users_batch_size_and_layout(db, sources, articles, settings):
    add_articles(db, sources, articles, n=6)
    fake = FakeOllama()
    worker = make_worker(db, settings, fake, **{"ai.depth": "fast", "ai.limits": {"batch_size": 3},
                                                 "ai.inputs": {"article": "ITEM {title}"}})
    run(worker.step())
    sent = [json.loads(c.content) for c in fake.calls if c.url.path == "/api/chat"]
    user = sent[0]["messages"][1]["content"]
    assert user.count("ITEM ") <= 3 and "[1]\nITEM " in user


def test_the_look_settings_are_guarded(client):
    ok = client.patch("/api/settings", headers=H, json={"ui.font": "Georgia, 'Times New Roman', serif", "ui.font_scale": 115,
                                                        "ui.text_color_light": "#223344", "ui.text_color_dark": ""})
    assert ok.status_code == 200 and ok.json()["ui.font_scale"] == 115 and ok.json()["ui.text_color_dark"] == ""
    for bad in ({"ui.font": "x; background: url(//evil)"}, {"ui.font": "a{b}"}, {"ui.font_scale": 50}, {"ui.font_scale": 200},
                {"ui.text_color_light": "red"}, {"ui.text_color_dark": "#12345"}, {"ui.text_color_light": "#12345g"}):
        assert client.patch("/api/settings", headers=H, json=bad).status_code == 422, bad


def test_the_shortcut_setting_is_guarded(client):
    good = {"search": ["/", "s"], "next": ["j", "arrowdown"], "open": ["enter", "space", "f2"], "meeting": ["t"]}
    assert client.patch("/api/settings", headers=H, json={"ui.shortcuts": good}).json()["ui.shortcuts"] == good
    for bad in ({"nonsense": ["x"]}, {"next": []}, {"next": ["j", "k", "l", "m", "n"]}, {"next": ["escape"]}, {"next": ["tab"]},
                {"next": ["ab"]}, {"next": ["f13"]}, {"next": ["j"], "prev": ["j"]}, {"next": ["j", "j"]}, {"next": [" "]}):
        assert client.patch("/api/settings", headers=H, json={"ui.shortcuts": bad}).status_code == 422, bad
    assert client.patch("/api/settings", headers=H, json={"ui.shortcuts": {}}).json()["ui.shortcuts"] == {}
