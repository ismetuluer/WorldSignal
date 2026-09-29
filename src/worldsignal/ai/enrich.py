"""Article enrichment: title and summary in the user's languages (``ai.languages``), category, and the facts
for "my country" relevance.

The model only sees the text we have (title + feed summary, or the full text). The prompt forbids adding facts,
and :func:`fidelity_issues` checks the output mechanically: every number the model writes must appear in the
source. Output that fails the check is stored but flagged, and the UI always keeps the original one click away.

Relevance to the user's country is *not* judged by the model. Language models proved unreliable at geography
(benchmark 2026-09-27: Afghanistan, Israel and Russia were called "neighbours of Türkiye", and listing
non-neighbours in the prompt made it worse). The model therefore only extracts facts that are in the text —
which countries appear, whether Türkiye is mentioned (asked only when the user's country is Türkiye), which of
the user's topics appear — and country.py decides with fixed, explainable rules. Story summaries (story.py) ask
for the same facts with the same wording (:meth:`EnrichTask.fact_fields`).

With ``ai.depth = "fast"`` single reports are read ``BATCH_SIZE`` at a time for their headline, category and facts
only (``with_summary=False``); the summary is written when the user asks for it.
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
BATCH_SIZE = 10
BATCH_TEXT_CHARS = 600  # per report in a batch: headline and the start of its text are enough without a summary

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
    with_summary: bool = True  # False: headline, category and facts only ("fast", read in batches)
    facts: bool = True  # False ("my country" is off): the country and topic questions are not asked at all

    def fact_schema(self) -> dict[str, Any]:
        """The facts for "my country": the same for reports and stories."""
        if not self.facts:
            return {}
        props: dict[str, Any] = {"countries": {"type": "array", "items": {"type": "string"}}}
        if self.ask_turkey:
            props["mentions_turkey"] = {"type": "boolean"}
        if self.topics:
            props["topics"] = {"type": "array", "items": {"type": "string", "enum": list(self.topics)}}
        return props

    def fact_fields(self, what: str = "text") -> list[str]:
        if not self.facts:
            return []
        fields = [f"- countries: ISO 3166-1 alpha-2 codes (e.g. \"US\", \"IR\", \"GR\") of the countries the {what} "
                  "is about or explicitly names. Cities and regions count for their country. Empty list if none."]
        if self.ask_turkey:
            fields.append(f"- mentions_turkey: true only if the {what} explicitly mentions Türkiye/Turkey, Turkish "
                          "people, a Turkish city, company, institution, team or official.")
        if self.topics:
            listed = "; ".join(f"{t} = {topic_label(t)}" if t in TOPIC_NAMES else t for t in self.topics)
            fields.append(f"- topics: those of these topics that the {what} explicitly talks about ({listed}). "
                          "Use the exact values before \"=\". Usually an empty list.")
        return fields

    @property
    def schema(self) -> dict[str, Any]:
        props: dict[str, Any] = {}
        for lang in self.languages:
            props[f"title_{lang}"] = {"type": "string"}
            if self.with_summary:
                props[f"summary_{lang}"] = {"type": "string"}
        props["category"] = {"type": "string", "enum": list(CATEGORIES)}
        props.update(self.fact_schema())
        return {"type": "object", "properties": props, "required": list(props)}

    @property
    def system_prompt(self) -> str:
        return self._prompt("You receive ONE news item (headline and whatever text the feed provided) in any language.")

    def _prompt(self, intro: str) -> str:
        names = [lang_name(lang) for lang in self.languages]
        fields = []
        for i, lang in enumerate(self.languages):
            name = lang_name(lang)
            if i == 0:
                fields.append(f"- title_{lang}: a natural {name} news headline in sentence case, max 110 characters. "
                              "Translate faithfully; do not sensationalize. If the source is in this language, keep "
                              "close to the original wording.")
                if self.with_summary:
                    fields.append(f"- summary_{lang}: 1 to 4 {name} sentences summarizing only what the text says.")
            elif self.with_summary:
                fields.append(f"- title_{lang}, summary_{lang}: the same headline and summary in natural {name} "
                              f"(same facts as summary_{self.languages[0]}, nothing more).")
            else:
                fields.append(f"- title_{lang}: the same headline in natural {name}, in sentence case.")
        fields.append("- category: one of " + ", ".join(CATEGORIES) + ".")
        fields.extend(self.fact_fields())
        return f"""You are a careful news desk editor.
{intro}
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


def batch_schema(task: EnrichTask) -> dict[str, Any]:
    item = task.schema
    item = {**item, "properties": {"n": {"type": "integer"}, **item["properties"]}, "required": ["n", *item["required"]]}
    return {"type": "object", "properties": {"items": {"type": "array", "items": item}}, "required": ["items"]}


def batch_prompt(task: EnrichTask) -> str:
    return task._prompt(
        "You receive several numbered news items (headline and whatever text the feed provided) in any language.\n"
        "Treat every item on its own: never mix facts between items. Return one object per item, with n = its "
        "number, in \"items\".")


def render_batch(inputs: list[EnrichInput]) -> str:
    parts = []
    for n, inp in enumerate(inputs, 1):
        short = EnrichInput(inp.source_name, inp.language, inp.title, inp.text.strip()[:BATCH_TEXT_CHARS])
        parts.append(f"[{n}]\n{short.render()}")
    return "\n\n".join(parts)


def validate_batch(data: dict[str, Any], inputs: list[EnrichInput], task: EnrichTask) -> list[EnrichResult | None]:
    """One result per input, in order; None where the model left an item out or gave an unusable one."""
    results: list[EnrichResult | None] = [None] * len(inputs)
    items = data.get("items")
    for item in items if isinstance(items, list) else []:
        n = item.get("n") if isinstance(item, dict) else None
        if isinstance(n, int) and 1 <= n <= len(inputs) and results[n - 1] is None:
            try:
                results[n - 1] = validate(item, inputs[n - 1], task)
            except ValueError:
                continue
    return results


def clean_title(value: Any) -> str:
    title = str(value or "").strip().strip('"').strip()
    return title[:159].rstrip() + "…" if len(title) > 160 else title
