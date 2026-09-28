"""The languages the AI writes headlines, summaries and translations in (setting ``ai.languages``).

Every AI text is stored per language: ``{"tr": {"title": …, "summary": …}, "pt": {…}}``. The user picks up to
MAX_LANGUAGES; each one costs generation time, so the default is two. Names are English because the prompts are.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

OUTPUT_LANGUAGES: dict[str, str] = {
    "tr": "Turkish", "en": "English", "de": "German", "fr": "French", "es": "Spanish", "it": "Italian",
    "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "ro": "Romanian", "bg": "Bulgarian",
    "el": "Greek", "ru": "Russian", "uk": "Ukrainian", "ka": "Georgian", "az": "Azerbaijani", "kk": "Kazakh",
    "uz": "Uzbek", "ar": "Arabic", "fa": "Persian", "he": "Hebrew", "ur": "Urdu", "hi": "Hindi", "bn": "Bengali",
    "id": "Indonesian", "ms": "Malay", "zh": "Chinese (Simplified)", "ja": "Japanese", "ko": "Korean",
    "sw": "Swahili",
}
DEFAULT_LANGUAGES = ["tr", "en"]
MAX_LANGUAGES = 4


def normalise(langs: Iterable[Any] | None) -> list[str]:
    """Known codes, no duplicates, at most MAX_LANGUAGES; the default when nothing usable is left."""
    out = [c for c in dict.fromkeys(str(x).strip().lower() for x in langs or []) if c in OUTPUT_LANGUAGES]
    return out[:MAX_LANGUAGES] or list(DEFAULT_LANGUAGES)


def effective(prefs: dict[str, Any]) -> list[str]:
    """The languages the AI writes in: the setting, or (unset) the interface language and English."""
    chosen = prefs.get("ai.languages")
    if chosen:
        return normalise(chosen)
    return normalise([prefs.get("ui.language") or "en", "en"])


def name(code: str) -> str:
    return OUTPUT_LANGUAGES.get(code, code)


def missing(texts: dict[str, Any] | None, langs: Iterable[str]) -> list[str]:
    """Languages of ``langs`` that ``texts`` has no title for."""
    have = texts or {}
    return [lang for lang in langs if not (isinstance(have.get(lang), dict) and have[lang].get("title"))]
