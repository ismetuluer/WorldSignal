"""Text normalisation for search.

SQLite's FTS5 ``unicode61`` tokenizer folds case with generic Unicode rules,
which breaks Turkish: ``IRAK`` and ``ırak`` never match, and ``İ`` lowercases
to ``i`` + a combining dot. We therefore normalise text in Python *before* it
is indexed and apply the exact same function to search queries.

The fold is intentionally lenient (dotted/dotless i are merged, Latin
diacritics are removed by the tokenizer) because newsroom users often type
without Turkish characters and headlines are frequently in capitals.
"""

from __future__ import annotations

import html
import re
from collections.abc import Sequence

_I_FOLD = str.maketrans({"I": "i", "İ": "i", "ı": "i"})
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def fold_for_search(text: str | None) -> str:
    """Case-fold ``text`` so that Turkish I/İ/ı/i all compare equal."""
    if not text:
        return ""
    # Removing the combining dot (U+0307) covers already-decomposed "i̇".
    return text.translate(_I_FOLD).replace("̇", "").lower()


# UTF-8 read as Windows-1252 leaves a lead character (Ã, Ä, Å, Â …) before a continuation character.
_MOJIBAKE = re.compile("[ÂÃÄÅ][-¿ŒœŠšŸŽžƒˆ˜–—"
                       "‘-„†-•…‰‹›€™]")


def repair_mojibake(text: str | None) -> str:
    """Undo UTF-8 text that a feed's server or a proxy had read as Windows-1252 ("SoykÄ±rÄ±m" -> "Soykırım").
    Only text that shows the pattern and decodes cleanly back is changed; anything else is returned as it is."""
    if not text or not _MOJIBAKE.search(text):
        return text or ""
    try:
        fixed = text.encode("cp1252").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text
    return fixed if len(fixed) < len(text) else text


def strip_html(text: str | None) -> str:
    """Turn an RSS summary (often HTML) into clean single-spaced text."""
    if not text:
        return ""
    text = repair_mojibake(text)
    text = _TAGS.sub(" ", text)
    text = html.unescape(text)
    return _WS.sub(" ", text).strip()


_QUERY_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


MAX_ALTERNATIVES = 24


def build_fts_query(user_query: str, alternatives: Sequence[str] = ()) -> str | None:
    """Convert free text typed by the user into a safe FTS5 MATCH expression.

    Every word becomes a quoted prefix term, and all terms must match. User
    input never reaches FTS5 syntax directly, so characters such as ``"``,
    ``*`` or ``NEAR`` cannot cause query errors.
    ``alternatives`` are other phrasings of the same search (its translations, ai/query.py): a text
    matching all words of any one of them matches too.
    Returns ``None`` when the query contains no searchable word.
    """
    groups = []
    for text in [user_query, *alternatives[:MAX_ALTERNATIVES]]:
        tokens = _QUERY_TOKEN.findall(fold_for_search(text))
        group = " AND ".join(f'"{t}"*' for t in tokens[:12])
        if group and group not in groups:
            groups.append(group)
    if not groups:
        return None
    return groups[0] if len(groups) == 1 else " OR ".join(f"({g})" for g in groups)
