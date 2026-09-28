"""Article enrichment: Turkish and English title and summary, category and Türkiye relevance.

The model only sees the text we have (title + feed summary; full text from
phase 5 on). The prompt forbids adding facts, and :func:`fidelity_issues`
checks the output mechanically: every number the model writes must appear in
the source. Output that fails the check is stored but flagged, and the UI
always keeps the original one click away.

Türkiye relevance is *not* judged by the model. Language models proved
unreliable at geography (benchmark 2026-09-27: Afghanistan, Israel and Russia
were called "neighbours of Türkiye", and listing non-neighbours in the prompt
made it worse). The model therefore only extracts facts that are in the text —
which countries appear, whether Türkiye is mentioned, which topics appear — and
:func:`turkey_relevance` decides with fixed, explainable rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

PROMPT_VERSION = 5  # 5: English next to Turkish

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

# Topics that make a story relevant to Türkiye even when it is not mentioned.
TURKEY_TOPICS = ("black_sea", "eastern_mediterranean", "nato", "eu_enlargement", "migration", "turkic_states")

# ISO 3166-1 alpha-2 codes.
NEIGHBOURS = frozenset({"GR", "BG", "GE", "AM", "AZ", "IR", "IQ", "SY", "CY"})
TURKIC_STATES = frozenset({"AZ", "KZ", "UZ", "KG", "TM"})

MAX_SOURCE_CHARS = 6000
MAX_COUNTRIES = 8

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title_tr": {"type": "string"},
        "summary_tr": {"type": "string"},
        "title_en": {"type": "string"},
        "summary_en": {"type": "string"},
        "category": {"type": "string", "enum": list(CATEGORIES)},
        "countries": {"type": "array", "items": {"type": "string"}},
        "mentions_turkey": {"type": "boolean"},
        "topics": {"type": "array", "items": {"type": "string", "enum": list(TURKEY_TOPICS)}},
    },
    "required": ["title_tr", "summary_tr", "title_en", "summary_en", "category", "countries", "mentions_turkey", "topics"],
}

SYSTEM_PROMPT = """You are a careful news desk editor at a Turkish television newsroom.
You receive ONE news item (headline and whatever text the feed provided) in any language.
Produce Turkish and English output as JSON.

Strict rules:
- Use ONLY information present in the given text. Never add facts, numbers, names, dates, causes or context from your own knowledge.
- If the text is short, the summary must be short. One sentence is fine. Do not pad.
- Keep numbers, names and places exactly as in the source. Write foreign names in their usual Turkish spelling (e.g. "Vladimir Putin", "Beyaz Saray").
- Neutral news language. No opinion, no clickbait, no exclamation marks.

Fields:
- title_tr: a natural Turkish news headline in sentence case, max 110 characters. Translate faithfully; do not sensationalize.
- summary_tr: 1 to 4 Turkish sentences summarizing only what the text says.
- title_en: the same headline in natural English news style, max 110 characters. If the source is English, keep close to the original wording.
- summary_en: the same summary in English (same facts as summary_tr, nothing more).
- category: one of diplomacy, conflict_defense, politics, economy, energy, technology, science_health, environment, disaster, society, justice, sports, culture, other.
- countries: ISO 3166-1 alpha-2 codes (e.g. "US", "IR", "GR") of the countries the text is about or explicitly names. Cities and regions count for their country. Empty list if none.
- mentions_turkey: true only if the text explicitly mentions Türkiye/Turkey, Turkish people, a Turkish city, company, institution, team or official.
- topics: those of black_sea, eastern_mediterranean, nato, eu_enlargement, migration, turkic_states that the text explicitly talks about. Usually an empty list."""

# Mechanical backstop: explicit Türkiye words in the source (several languages).
_TURKEY_WORDS = re.compile(
    r"Türkiye|Turkiye|\bTurkey\b|\bTurkish|\bTürk|\bAnkara\b|Erdoğan|Erdogan|İstanbul|\bIstanbul|"
    r"Türkei|Turquie|Turquía|Turchia|Турци|Турецк|تركيا|التركي",
)


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
    title_tr: str
    summary_tr: str
    title_en: str
    summary_en: str
    category: str
    countries: list[str]
    turkey_relevance: str  # none | indirect | direct
    turkey_links: list[str]  # why: "turkey_mentioned", "neighbour:GR", "turkic:KZ", "topic:nato"
    issues: list[str] = field(default_factory=list)


_NUMBER = re.compile(r"\d+(?:[.,]\d+)*")


def _numbers(text: str) -> set[str]:
    """Numbers normalised so 1,500 / 1.500 / 1500 compare equal."""
    return {re.sub(r"[.,]", "", n) for n in _NUMBER.findall(text)}


def fidelity_issues(source: str, output: str) -> list[str]:
    """Mechanical fabrication check: numbers in the output must exist in the source."""
    invented = sorted(_numbers(output) - _numbers(source))
    return [f"number_not_in_source:{n}" for n in invented]


def turkey_relevance(
    countries: list[str], mentions_turkey: bool, topics: list[str], source_text: str
) -> tuple[str, list[str]]:
    """Decide Türkiye relevance with fixed rules. Returns (level, links explaining why)."""
    if mentions_turkey or "TR" in countries or _TURKEY_WORDS.search(source_text):
        return "direct", ["turkey_mentioned"]
    links = [f"neighbour:{c}" for c in countries if c in NEIGHBOURS]
    links += [f"turkic:{c}" for c in countries if c in TURKIC_STATES and c not in NEIGHBOURS]
    links += [f"topic:{t}" for t in topics]
    return ("indirect", links) if links else ("none", [])


def validate(data: dict[str, Any], inp: EnrichInput) -> EnrichResult:
    """Normalise model output; raise ValueError if it is unusable."""
    title = clean_title(data.get("title_tr"))
    summary = str(data.get("summary_tr", "")).strip()
    title_en = clean_title(data.get("title_en"))
    summary_en = str(data.get("summary_en", "")).strip()
    if not title or not title_en:
        raise ValueError("empty_title")
    category = data.get("category")
    if category not in CATEGORIES:
        category = "other"
    countries: list[str] = []
    for c in data.get("countries") or []:
        code = str(c).strip().upper()
        if re.fullmatch(r"[A-Z]{2}", code) and code not in countries:
            countries.append(code)
    countries = countries[:MAX_COUNTRIES]
    topics = [t for t in dict.fromkeys(data.get("topics") or []) if t in TURKEY_TOPICS]
    level, links = turkey_relevance(countries, bool(data.get("mentions_turkey")), topics, inp.source_text)
    issues = fidelity_issues(inp.source_text, f"{title}\n{summary}\n{title_en}\n{summary_en}")
    return EnrichResult(title, summary, title_en, summary_en, category, countries, level, links, issues)


def clean_title(value: Any) -> str:
    title = str(value or "").strip().strip('"').strip()
    return title[:159].rstrip() + "…" if len(title) > 160 else title
