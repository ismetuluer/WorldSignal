"""A search typed in one language, translated into the languages of the user's sources.

Most reports are never summarised (the AI cannot keep up with every source), so a word search in Turkish
only finds reports that are in Turkish or that the AI has translated. The search words themselves are
therefore translated into the languages the sources publish in; the word search then runs once per
phrasing ("kuzey kore iha" also finds "North Korea … drones"). Search words only, never article text.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .languages import name as lang_name
from .prompts import render

MAX_LANGUAGES = 8
PER_LANGUAGE = 2
MAX_CHARS = 80
NUM_PREDICT = 400


def schema(languages: list[str]) -> dict[str, Any]:
    phrases = {"type": "array", "items": {"type": "string"}}
    return {"type": "object", "properties": {lang: phrases for lang in languages}, "required": list(languages)}


def system_prompt(languages: list[str], custom: Mapping[str, str] | None = None) -> str:
    names = ", ".join(f"{code} = {lang_name(code)}" for code in languages)
    return render("query", custom, languages=names)


def validate(data: dict[str, Any], languages: list[str]) -> dict[str, list[str]]:
    """Clean phrases per language; nonsense (non-strings, overlong phrases) is dropped."""
    out: dict[str, list[str]] = {}
    for lang in languages:
        raw = data.get(lang)
        phrases: list[str] = []
        for item in raw if isinstance(raw, list) else [raw]:
            phrase = " ".join(str(item).split()) if isinstance(item, str) else ""
            if phrase and len(phrase) <= MAX_CHARS and phrase.casefold() not in {p.casefold() for p in phrases}:
                phrases.append(phrase)
        if phrases:
            out[lang] = phrases[:PER_LANGUAGE]
    return out
