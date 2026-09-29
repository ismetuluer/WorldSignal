"""Story-level AI: one headline, a 3-5 sentence summary and a meeting pitch in each of the user's languages,
written from several reports of the same event.

As with single articles, the model may only use the given texts; numbers in the
output are checked against them (:func:`fidelity_issues`). Given the report task (``facts``), it also extracts the
facts for "my country" the same way (countries, the home country, the user's topics); country.py decides.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from .enrich import CATEGORIES, MAX_COUNTRIES, EnrichTask, clean_title, fidelity_issues
from .languages import DEFAULT_LANGUAGES
from .languages import name as lang_name

STORY_PROMPT_VERSION = 4  # 4: the facts for "my country"
MAX_REPORTS = 8
REPORT_CHARS = 700


def story_schema(languages: tuple[str, ...], facts: EnrichTask | None = None) -> dict[str, Any]:
    props: dict[str, Any] = {}
    for lang in languages:
        props[f"title_{lang}"] = {"type": "string"}
        props[f"summary_{lang}"] = {"type": "string"}
        props[f"why_meeting_{lang}"] = {"type": "string"}
    props["category"] = {"type": "string", "enum": list(CATEGORIES)}
    if facts is not None:
        props.update(facts.fact_schema())
    return {"type": "object", "properties": props, "required": list(props)}


def story_prompt(languages: tuple[str, ...], facts: EnrichTask | None = None) -> str:
    first, name = languages[0], lang_name(languages[0])
    fields = [
        f"- title_{first}: a natural {name} headline for the event in sentence case, max 110 characters.",
        f"- summary_{first}: 3 to 5 {name} sentences: what happened, where, who, the latest development. "
        "Fewer sentences if the reports contain little information.",
        f"- why_meeting_{first}: ONE {name} sentence for the meeting: why this event deserves airtime, based only "
        "on what the reports show (e.g. how widely it is covered, what is new).",
    ]
    for lang in languages[1:]:
        fields.append(f"- title_{lang}, summary_{lang}, why_meeting_{lang}: the same three texts in natural "
                      f"{lang_name(lang)} (same facts, nothing more).")
    fields.append("- category: one of " + ", ".join(CATEGORIES) + ".")
    if facts is not None:
        fields.extend(facts.fact_fields("reports"))
    return f"""You are the foreign news editor of a newsroom preparing the morning editorial meeting.
You receive several reports from different outlets, in different languages, about ONE news event.
Write output in {", ".join(lang_name(lang) for lang in languages)} as JSON.

Strict rules:
- Use ONLY information present in the reports. Never add facts, numbers, names, dates, causes or background from your own knowledge.
- When reports disagree, say so briefly (according to X ..., while Y reported ...) instead of choosing one.
- Keep numbers and names exactly as in the reports. Neutral news language, no exclamation marks.

Fields:
""" + "\n".join(fields)


@dataclass
class StoryReport:
    source_name: str
    language: str
    title: str
    text: str


@dataclass
class StoryResult:
    texts: dict[str, dict[str, str]]  # {"tr": {"title": …, "summary": …, "why": …}, …}
    category: str
    issues: list[str] = field(default_factory=list)
    # The facts for "my country" (None: not asked).
    countries: list[str] | None = None
    topics: list[str] = field(default_factory=list)
    mentions_home: bool = False


def render_reports(reports: list[StoryReport], source_count: int) -> str:
    parts = [f"The event is covered by {source_count} independent outlets. Reports:"]
    for n, r in enumerate(reports[:MAX_REPORTS], 1):
        text = r.text.strip()
        if text == r.title.strip():
            text = ""
        parts.append(f"[{n}] {r.source_name} ({r.language}): {r.title.strip()}\n{text[:REPORT_CHARS]}".rstrip())
    return "\n\n".join(parts)


def pick_reports(members: list[dict[str, Any]]) -> list[StoryReport]:
    """One report per source first (most recent), so the model sees different outlets."""
    seen: set[str] = set()
    first, rest = [], []
    for m in members:  # members arrive newest first
        report = StoryReport(m["source_name"], m["language"], m["title"], m.get("summary") or "")
        (rest if m["source_name"] in seen else first).append(report)
        seen.add(m["source_name"])
    return (first + rest)[:MAX_REPORTS]


def validate_story(data: dict[str, Any], reports: list[StoryReport], source_count: int,
                   languages: tuple[str, ...] = tuple(DEFAULT_LANGUAGES), facts: EnrichTask | None = None) -> StoryResult:
    texts: dict[str, dict[str, str]] = {}
    for lang in languages:
        title = clean_title(data.get(f"title_{lang}"))
        summary = str(data.get(f"summary_{lang}", "")).strip()
        if not title or not summary:
            raise ValueError("empty_story_text")
        texts[lang] = {"title": title, "summary": summary, "why": str(data.get(f"why_meeting_{lang}", "")).strip()}
    category = data.get("category") if data.get("category") in CATEGORIES else "other"
    # The rendered input also contains the source count, which the model may legitimately quote.
    source_text = render_reports(reports, source_count)
    written = "\n".join("\n".join(t.values()) for t in texts.values())
    result = StoryResult(texts, category, fidelity_issues(source_text, written))
    if facts is not None:
        countries: list[str] = []
        for c in data.get("countries") or []:
            code = str(c).strip().upper()
            if re.fullmatch(r"[A-Z]{2}", code) and code not in countries:
                countries.append(code)
        result.countries = countries[:MAX_COUNTRIES]
        result.topics = [t for t in dict.fromkeys(data.get("topics") or []) if t in facts.topics]
        result.mentions_home = facts.ask_turkey and bool(data.get("mentions_turkey"))
    return result
