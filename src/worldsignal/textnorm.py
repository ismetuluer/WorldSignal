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

_I_FOLD = str.maketrans({"I": "i", "İ": "i", "ı": "i"})
_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def fold_for_search(text: str | None) -> str:
    """Case-fold ``text`` so that Turkish I/İ/ı/i all compare equal."""
    if not text:
        return ""
    # Removing the combining dot (U+0307) covers already-decomposed "i̇".
    return text.translate(_I_FOLD).replace("̇", "").lower()


def strip_html(text: str | None) -> str:
    """Turn an RSS summary (often HTML) into clean single-spaced text."""
    if not text:
        return ""
    text = _TAGS.sub(" ", text)
    text = html.unescape(text)
    return _WS.sub(" ", text).strip()


_QUERY_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)


def build_fts_query(user_query: str) -> str | None:
    """Convert free text typed by the user into a safe FTS5 MATCH expression.

    Every word becomes a quoted prefix term, and all terms must match. User
    input never reaches FTS5 syntax directly, so characters such as ``"``,
    ``*`` or ``NEAR`` cannot cause query errors.
    Returns ``None`` when the query contains no searchable word.
    """
    tokens = _QUERY_TOKEN.findall(fold_for_search(user_query))
    if not tokens:
        return None
    return " AND ".join(f'"{t}"*' for t in tokens[:12])
