"""Article enrichment: title and summary in the user's languages (``ai.languages``), category, and the facts
for "my country" relevance.

The model only sees the text we have (title + feed summary, or the full text). The prompt forbids adding facts,
and :func:`fidelity_issues` checks the output mechanically: every number the model writes must appear in the
source. Output that fails the check is stored but flagged, and the UI always keeps the original one click away.

Relevance to the user's country is *not* judged by the model. Language models proved unreliable at geography
(benchmark 2026-09-27: Afghanistan, Israel and Russia were called "neighbours of Türkiye", and listing
non-neighbours in the prompt made it worse). The model therefore only extracts facts that are in the text —
which countries appear, whether Türkiye is mentioned (asked only when the user's country is Türkiye), which of
the user's topics appear — and country.py decides with fixed, explainable rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..country import TOPICS
from .languages import DEFAULT_LANGUAGES
from .languages import name as lang_name

PROMPT_VERSION = 6  # 6: the user's languages and topics

CATEGORIES = (
    "diplomacy",
    "conflict_defense",
    "politics",
    "economy",
    "energy",
    "technology",
    "science_health",
    "environment",
    "disaster",
    "society",
    "justice",
    "sports",
    "culture",
    "other",
)


MAX_SOURCE_CHARS = 6000
MAX_COUNTRIES = 8

# Built-in topics (country.TOPICS) as the prompt names them; the user's own topics are used as written.
TOPIC_NAMES = {
    "black_sea": "the Black Sea",
    "eastern_mediterranean": "the Eastern Mediterranean",
    "nato": "NATO",
    "eu_enlargement": "EU enlargement",
    "migration": "migration and refugees",
    "turkic_states": "the Turkic states",
}


def topic_label(topic: str) -> str:
    return TOPIC_NAMES.get(topic, topic)


@dataclass(frozen=True)
class EnrichTask:
    """What to ask for: the output languages, the user's topics, and whether to ask about Türkiye."""

    languages: tuple[str, ...] = tuple(DEFAULT_LANGUAGES)
    topics: tuple[str, ...] = TOPICS
    ask_turkey: bool = True

    @property
    def schema(self) -> dict[str, Any]:
        props: dict[str, Any] = {}
        for lang in self.languages:
            props[f"title_{lang}"] = {"type": "string"}
            props[f"summary_{lang}"] = {"type": "string"}
        props["category"] = {"type": "string", "enum": list(CATEGORIES)}
        props["countries"] = {"type": "array", "items": {"type": "string"}}
        if self.ask_turkey:
            props["mentions_turkey"] = {"type": "boolean"}
        if self.topics:
            props["topics"] = {"type": "array", "items": {"type": "string", "enum": list(self.topics)}}
        return {"type": "object", "properties": props, "required": list(props)}

    @property
    def system_prompt(self) -> str:
        names = [lang_name(lang) for lang in self.languages]
        fields = []
        for i, lang in enumerate(self.languages):
            name = lang_name(lang)
            if i == 0:
                fields.append(f"- title_{lang}: a natural {name} news headline in sentence case, max 110 characters. "
                              "Translate faithfully; do not sensationalize. If the source is in this language, keep "
                              "close to the original wording.")
                fields.append(f"- summary_{lang}: 1 to 4 {name} sentences summarizing only what the text says.")
            else:
                fields.append(f"- title_{lang}, summary_{lang}: the same headline and summary in natural {name} "
                              f"(same facts as summary_{self.languages[0]}, nothing more).")
        fields.append("- category: one of " + ", ".join(CATEGORIES) + ".")
        fields.append("- countries: ISO 3166-1 alpha-2 codes (e.g. \"US\", \"IR\", \"GR\") of the countries the text "
                      "is about or explicitly names. Cities and regions count for their country. Empty list if none.")
        if self.ask_turkey:
            fields.append("- mentions_turkey: true only if the text explicitly mentions Türkiye/Turkey, Turkish people, "
                          "a Turkish city, company, institution, team or official.")
        if self.topics:
            listed = "; ".join(f"{t} = {topic_label(t)}" if t in TOPIC_NAMES else t for t in self.topics)
            fields.append(f"- topics: those of these topics that the text explicitly talks about ({listed}). "
                          "Use the exact values before \"=\". Usually an empty list.")
        return f"""You are a careful news desk editor.
You receive ONE news item (headline and whatever text the feed provided) in any language.
Produce output in {", ".join(names)} as JSON.

Strict rules:
- Use ONLY information present in the given text. Never add facts, numbers, names, dates, causes or context from your own knowledge.
- If the text is short, the summary must be short. One sentence is fine. Do not pad.
- Keep numbers, names and places exactly as in the source. Write foreign names in their usual spelling in each output language.
- Neutral news language. No opinion, no clickbait, no exclamation marks.

Fields:
""" + "\n".join(fields)


@dataclass
class EnrichInput:
    source_name: str
    language: str
    title: str
    text: str

    def render(self) -> str:
        text = self.text.strip()
        if len(text) > MAX_SOURCE_CHARS:
            text = text[:MAX_SOURCE_CHARS] + " …"
        body = text if text and text != self.title.strip() else "(no text besides the headline)"
        return f"Source: {self.source_name}\nLanguage: {self.language}\nHeadline: {self.title.strip()}\nText: {body}"

    @property
    def source_text(self) -> str:
        return f"{self.title}\n{self.text}"


@dataclass
class EnrichResult:
    texts: dict[str, dict[str, str]]  # {"tr": {"title": …, "summary": …}, …}
    category: str
    countries: list[str]
    topics: list[str]  # of the user's topics that the text talks about
    mentions_turkey: bool
    issues: list[str] = field(default_factory=list)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    """Numbers normalised so 1,500 / 1.500 / 1500 compare equal."""
    return {re.sub(r"[.,]", "", n) for n in _NUMBER.findall(text)}


def fidelity_issues(source: str, output: str) -> list[str]:
    """Mechanical fabrication check: numbers in the output must exist in the source."""
    invented = sorted(_numbers(output) - _numbers(source))
    return [f"number_not_in_source:{n}" for n in invented]


def validate(data: dict[str, Any], inp: EnrichInput, task: EnrichTask = EnrichTask()) -> EnrichResult:
    """Normalise model output; raise ValueError if it is unusable."""
    texts: dict[str, dict[str, str]] = {}
    for lang in task.languages:
        title = clean_title(data.get(f"title_{lang}"))
        if not title:
            raise ValueError(f"empty_title_{lang}")
        texts[lang] = {"title": title, "summary": str(data.get(f"summary_{lang}", "")).strip()}
    category = data.get("category")
    if category not in CATEGORIES:
        category = "other"
    countries: list[str] = []
    for c in data.get("countries") or []:
        code = str(c).strip().upper()
        if re.fullmatch(r"[A-Z]{2}", code) and code not in countries:
            countries.append(code)
    countries = countries[:MAX_COUNTRIES]
    topics = [t for t in dict.fromkeys(data.get("topics") or []) if t in task.topics]
    written = "\n".join(f"{t['title']}\n{t['summary']}" for t in texts.values())
    issues = fidelity_issues(inp.source_text, written)
    return EnrichResult(texts, category, countries, topics, task.ask_turkey and bool(data.get("mentions_turkey")), issues)


def clean_title(value: Any) -> str:
    title = str(value or "").strip().strip('"').strip()
    return title[:159].rstrip() + "…" if len(title) > 160 else title
