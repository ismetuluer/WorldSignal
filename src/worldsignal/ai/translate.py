"""Translation of an article's full text into Turkish and English, on the user's request.

The text is split at paragraph boundaries into chunks the model can translate in one answer.
A chunk is translated faithfully (no summarising, no additions); numbers are checked like in
summaries. Nothing is translated into the language the article is already in.
"""

from __future__ import annotations

from typing import Any

from .enrich import fidelity_issues

CHUNK_CHARS = 1800
NUM_PREDICT = 2048

LANG_NAMES = {"tr": "Turkish", "en": "English"}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"translation": {"type": "string"}},
    "required": ["translation"],
}


def system_prompt(target: str) -> str:
    return f"""You are a professional news translator.
Translate the given part of a news article into {LANG_NAMES[target]}.

Strict rules:
- Translate everything, sentence by sentence. Do not summarise, shorten, explain or add anything.
- Keep names, numbers, dates, quotes and paragraph breaks exactly.
- Return JSON: {{"translation": "..."}}"""


def chunks(text: str, size: int = CHUNK_CHARS) -> list[str]:
    """Paragraph-aligned pieces of at most ``size`` characters (a longer paragraph is split at sentences)."""
    out: list[str] = []
    current = ""
    for para in [p.strip() for p in text.split("\n") if p.strip()]:
        pieces = [para]
        if len(para) > size:
            pieces, buf = [], ""
            for sentence in para.replace(". ", ".\u0000").split("\u0000"):
                if buf and len(buf) + len(sentence) + 1 > size:
                    pieces.append(buf)
                    buf = ""
                buf = f"{buf} {sentence}".strip()
            if buf:
                pieces.append(buf)
        for piece in pieces:
            if current and len(current) + len(piece) + 2 > size:
                out.append(current)
                current = ""
            current = f"{current}\n\n{piece}".strip()
    if current:
        out.append(current)
    return out


def targets(source_language: str) -> list[str]:
    return [lang for lang in ("tr", "en") if lang != source_language]


def check(source: str, translated: str) -> list[str]:
    return fidelity_issues(source, translated)
