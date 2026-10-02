"""The language of a report from the letters of its text, for the cases a feed's label cannot be right: a source
whose feed is labelled English but carries a Japanese or Arabic section (Reuters, CNN, Rudaw ...).

Only the script is read, never the words: it is certain where it applies and silent everywhere else. A text
in Latin letters keeps the label it came with."""

from __future__ import annotations

import re

# (language, the letters it is written in). Arabic script covers Persian and Urdu too; their extra letters tell them apart.
_RANGES: tuple[tuple[str, str], ...] = (
    ("ja", "぀-ヿ"),          # kana: the one sure sign of Japanese
    ("ko", "가-힯ᄀ-ᇿ"),
    ("zh", "一-鿿"),
    ("ar", "؀-ۿݐ-ݿ"),
    ("ru", "Ѐ-ӿ"),
    ("he", "֐-׿"),
    ("el", "Ͱ-Ͽἀ-῿"),
    ("th", "฀-๿"),
)
_SCRIPT = {code: re.compile(f"[{chars}]") for code, chars in _RANGES}
_LETTER = re.compile(r"[^\W\d_]")
_PERSIAN = re.compile("[پچژگی]")
_URDU = re.compile("[ٹڈڑںھہے]")
_UKRAINIAN = re.compile("[іїєґІЇЄҐ]")
# Which script each language label is written in; any label not listed is Latin.
_LABEL_SCRIPT = {"ja": "ja", "ko": "ko", "zh": "zh", "ar": "ar", "fa": "ar", "ur": "ar", "ps": "ar",
                 "ru": "ru", "uk": "ru", "bg": "ru", "sr": "ru", "be": "ru", "mk": "ru", "kk": "ru",
                 "he": "he", "el": "el", "th": "th"}
MIN_LETTERS = 6  # a title shorter than this proves nothing
SHARE = 0.6  # of the letters, this share must be in one script (a Latin brand name in a Japanese title is fine)


def detect(text: str) -> str | None:
    """The language of ``text`` when it is written in a non-Latin script, else None."""
    letters = _LETTER.findall(text or "")
    if len(letters) < MIN_LETTERS:
        return None
    counts = {code: len(rx.findall(text)) for code, rx in _SCRIPT.items()}
    # Chinese characters inside Japanese text are part of it: kana decides.
    if counts["ja"]:
        counts["ja"] += counts["zh"]
        counts["zh"] = 0
    code, count = max(counts.items(), key=lambda kv: kv[1])
    if count / len(letters) < SHARE:
        return None
    if code == "ar":
        return "fa" if _PERSIAN.search(text) else "ur" if _URDU.search(text) else "ar"
    if code == "ru":
        return "uk" if _UKRAINIAN.search(text) else "ru"
    return code


def correct(label: str | None, text: str) -> str | None:
    """``label`` (the feed's language) unless the text is written in another script than the label's: then the
    language the letters show. A label of the right script is never touched (Ukrainian stays Ukrainian)."""
    found = detect(text)
    if found is None or (found == "zh" and label == "ja"):  # an all-kanji Japanese title looks Chinese
        return label
    if label is not None and _LABEL_SCRIPT.get(label, "latin") == _LABEL_SCRIPT.get(found, "latin"):
        return label
    return found
