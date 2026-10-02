"""The instructions the program sends to an AI model, as templates the user may edit (Settings → AI → Instructions).

Four tasks have one: ``article`` (headline, summary and category of a report, also in batches), ``story`` (the summary
of a story), ``translate`` (a full text) and ``query`` (search words). A template is plain text with placeholders the
program fills in:

- ``{input}``      how the model receives the material (a single report, several numbered reports ...)
- ``{languages}``  the names of the user's output languages
- ``{language}``   the one language to translate into (task ``translate``)
- ``{fields}``     the technical description of the answer fields; the program builds it from the user's languages and
                   topics, and it has to stay in the instructions or the answer cannot be read (it is added at the
                   end when the user's text leaves it out)

What cannot be edited here is everything the program checks: the answer's JSON structure (a schema is sent with every
request), the numbers-in-the-source check and the limits on lengths. A changed instruction only affects work that is
done afterwards; summaries already written stay as they are.
"""

from __future__ import annotations

import re
from collections.abc import Mapping

TASKS = ("article", "story", "translate", "query")
MAX_CHARS = 6000
PLACEHOLDER = re.compile(r"\{(input|languages|language|fields)\}")

DEFAULTS: dict[str, str] = {
    "article": """You are a careful news desk editor.
{input}
Produce output in {languages} as JSON.

Strict rules:
- Use ONLY information present in the given text. Never add facts, numbers, names, dates, causes or context from your own knowledge.
- If the text is short, the summary must be short. One sentence is fine. Do not pad.
- Keep numbers, names and places exactly as in the source. Write foreign names in their usual spelling in each output language.
- Neutral news language. No opinion, no clickbait, no exclamation marks.

Fields:
{fields}""",
    "story": """You are the foreign news editor of a newsroom preparing the morning editorial meeting.
You receive several reports from different outlets, in different languages, about ONE news event.
Write output in {languages} as JSON.

Strict rules:
- Use ONLY information present in the reports. Never add facts, numbers, names, dates, causes or background from your own knowledge.
- When reports disagree, say so briefly (according to X ..., while Y reported ...) instead of choosing one.
- Keep numbers and names exactly as in the reports. Neutral news language, no exclamation marks.

Fields:
{fields}""",
    "translate": """You are a professional news translator.
Translate the given part of a news article into {language}.

Strict rules:
- Translate everything, sentence by sentence. Do not summarise, shorten, explain or add anything.
- Keep names, numbers, dates, quotes and paragraph breaks exactly.
- Return JSON: {"translation": "..."}""",
    "query": """You translate search words for a news search engine.
The user types a few words; translate them into these languages: {languages}.

Rules:
- For each language give the translation, plus one other wording only if headlines often use it
  (for example "drone" and "UAV"). Expand abbreviations (İHA = drone) and spell names the way that language does.
- The search matches the beginnings of words, so use the shortest base form of every word: singular nouns,
  "North Korea drone", not "North Korean drones".
- Only the words that were typed: never add words such as "news", "latest" or "results".
- If the words are already in that language, repeat them.
- Return JSON with one list per language code.""",
}

# Which placeholders each task knows; the others are left as typed.
KNOWN: dict[str, frozenset[str]] = {
    "article": frozenset({"input", "languages", "fields"}),
    "story": frozenset({"languages", "fields"}),
    "translate": frozenset({"language"}),
    "query": frozenset({"languages"}),
}
NEEDS_FIELDS = frozenset({"article", "story"})


def chosen(custom: Mapping[str, str] | None, task: str) -> str:
    """The user's template for ``task``, or the default when there is none (or it is blank)."""
    text = (custom or {}).get(task)
    return text if isinstance(text, str) and text.strip() else DEFAULTS[task]


def render(task: str, custom: Mapping[str, str] | None, **parts: str) -> str:
    """The instructions for ``task`` with the placeholders filled in. A template without ``{fields}`` still gets the
    field description at its end, and one without ``{input}`` gets that line after its first line, because the model
    could not do the work without them."""
    template = chosen(custom, task)
    present = set(PLACEHOLDER.findall(template))
    if task in NEEDS_FIELDS and "fields" not in present:
        template = template.rstrip() + "\n\nFields:\n{fields}"
    if task == "article" and "input" not in present:
        head, sep, rest = template.partition("\n")
        template = f"{head}\n{{input}}{sep}{rest}"

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        return parts[name] if name in KNOWN[task] and name in parts else match.group(0)

    return PLACEHOLDER.sub(fill, template)


def problems(task: str, text: str) -> list[str]:
    """What is wrong with a template the user typed (empty list: fine). Codes are translated by the interface."""
    found: list[str] = []
    if len(text) > MAX_CHARS:
        found.append("too_long")
    present = set(PLACEHOLDER.findall(text))
    if task in NEEDS_FIELDS and "fields" not in present:
        found.append("no_fields")
    if task == "translate" and "language" not in present:
        found.append("no_language")
    if task == "query" and "languages" not in present:
        found.append("no_languages")
    return found


# ---- the material: how each report is laid out in the request, and how much of it is sent -----------------------------
# Every request carries, besides the instructions above, the reports themselves. Their layout is a template too (the
# placeholders are the fields of a report), and the amounts are limits the user may raise or lower.
INPUT_TASKS = ("article", "story_intro", "story_report")
INPUT_DEFAULTS: dict[str, str] = {
    "article": "Source: {source}\nLanguage: {language}\nHeadline: {title}\nText: {text}",
    "story_intro": "The event is covered by {count} independent outlets. Reports:",
    "story_report": "[{n}] {source} ({language}): {title}\n{text}",
}
INPUT_KNOWN: dict[str, frozenset[str]] = {
    "article": frozenset({"source", "language", "title", "text"}),
    "story_intro": frozenset({"count"}),
    "story_report": frozenset({"n", "source", "language", "title", "text"}),
}
INPUT_REQUIRED: dict[str, str] = {"article": "title", "story_report": "title"}
INPUT_PLACEHOLDER = re.compile(r"\{(source|language|title|text|count|n)\}")
MAX_INPUT_CHARS = 1000

# name: (default, lowest, highest)
LIMITS: dict[str, tuple[int, int, int]] = {
    "article_chars": (6000, 200, 60000),      # characters of one report's text sent for its own summary
    "batch_chars": (600, 100, 6000),          # characters per report when several are read in one request ("fast")
    "batch_size": (10, 2, 25),                # reports per request in a batch
    "story_reports": (8, 2, 30),              # reports shown to the model for a story
    "story_report_chars": (700, 100, 6000),   # characters of each of them
}


def limit(custom: Mapping[str, int] | None, name: str) -> int:
    """The user's value for a limit, kept inside its range, or the default."""
    default, low, high = LIMITS[name]
    value = (custom or {}).get(name)
    return min(high, max(low, value)) if isinstance(value, int) and not isinstance(value, bool) else default


def render_input(kind: str, custom: Mapping[str, str] | None, **parts: object) -> str:
    """One report (or the intro of a story's reports) laid out by the user's template, or the default."""
    text = (custom or {}).get(kind)
    template = text if isinstance(text, str) and text.strip() else INPUT_DEFAULTS[kind]

    def fill(match: re.Match[str]) -> str:
        name = match.group(1)
        return str(parts[name]) if name in INPUT_KNOWN[kind] and name in parts else match.group(0)

    return INPUT_PLACEHOLDER.sub(fill, template)


def input_problems(kind: str, text: str) -> list[str]:
    found: list[str] = []
    if len(text) > MAX_INPUT_CHARS:
        found.append("too_long")
    needed = INPUT_REQUIRED.get(kind)
    if needed and "{" + needed + "}" not in text:
        found.append("no_" + needed)
    return found
