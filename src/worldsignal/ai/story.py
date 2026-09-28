"""Story-level AI: one headline, a 3-5 sentence summary and a meeting pitch, in Turkish and English,
written from several reports of the same event.

As with single articles, the model may only use the given texts; numbers in the
output are checked against them (:func:`fidelity_issues`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .enrich import CATEGORIES, clean_title, fidelity_issues

STORY_PROMPT_VERSION = 2  # 2: English next to Turkish
MAX_REPORTS = 8
REPORT_CHARS = 700

STORY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title_tr": {"type": "string"},
        "summary_tr": {"type": "string"},
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "why_meeting_tr": {"type": "string"},
        "title_en": {"type": "string"},
        "summary_en": {"type": "string"},
        "why_meeting_en": {"type": "string"},
    },
    "required": ["title_tr", "summary_tr", "category", "why_meeting_tr", "title_en", "summary_en", "why_meeting_en"],
}

STORY_SYSTEM_PROMPT = """You are the foreign news editor of a Turkish television newsroom preparing the morning editorial meeting.
You receive several reports from different outlets, in different languages, about ONE news event.
Write Turkish and English output as JSON.

Strict rules:
- Use ONLY information present in the reports. Never add facts, numbers, names, dates, causes or background from your own knowledge.
- When reports disagree, say so briefly ("X'e göre ..., Y ise ... bildirdi") instead of choosing one.
- Keep numbers and names exactly as in the reports. Neutral news language, no exclamation marks.

Fields:
- title_tr: a natural Turkish headline for the event in sentence case, max 110 characters.
- summary_tr: 3 to 5 Turkish sentences: what happened, where, who, the latest development. Fewer sentences if the reports contain little information.
- category: one of diplomacy, conflict_defense, politics, economy, energy, technology, science_health, environment, disaster, society, justice, sports, culture, other.
- why_meeting_tr: ONE Turkish sentence for the meeting: why this event deserves airtime, based only on what the reports show (e.g. how widely it is covered, what is new).
- title_en, summary_en, why_meeting_en: the same three texts in natural English (same facts, nothing more)."""


@dataclass
class StoryReport:
    source_name: str
    language: str
    title: str
    text: str


@dataclass
class StoryResult:
    title_tr: str
    summary_tr: str
    category: str
    why_tr: str
    title_en: str
    summary_en: str
    why_en: str
    issues: list[str] = field(default_factory=list)


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


def validate_story(data: dict[str, Any], reports: list[StoryReport], source_count: int) -> StoryResult:
    title = clean_title(data.get("title_tr"))
    summary = str(data.get("summary_tr", "")).strip()
    why = str(data.get("why_meeting_tr", "")).strip()
    title_en = clean_title(data.get("title_en"))
    summary_en = str(data.get("summary_en", "")).strip()
    why_en = str(data.get("why_meeting_en", "")).strip()
    if not title or not summary or not title_en or not summary_en:
        raise ValueError("empty_story_text")
    category = data.get("category") if data.get("category") in CATEGORIES else "other"
    # The rendered input also contains the source count, which the model may legitimately quote.
    source_text = render_reports(reports, source_count)
    issues = fidelity_issues(source_text, f"{title}\n{summary}\n{why}\n{title_en}\n{summary_en}\n{why_en}")
    return StoryResult(title, summary, category, why, title_en, summary_en, why_en, issues)
