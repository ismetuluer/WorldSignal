"""Labels the publisher puts on the article page itself, not in the RSS: "Exclusive" / "Scoop".

Most paid publishers (NYT, FT, Bloomberg, WSJ ...) send no such label in their feeds, but their pages show it. The browser
extension hands the whole page to the program, so the label can be read there. Four signals, any one is enough:

* a keyword / tag meta (``keywords``, ``news_keywords``, ``article:tag``, ``parsely-tags`` ...) or a structured-data
  ``keywords`` / ``articleSection`` entry that is exactly "exclusive" or "scoop" (also in the languages of flags.py);
* a small element holding only the label ("Exclusive", "EXCLUSIVE:", "Scoop") inside the article, not in navigation,
  footer or a sidebar;
* the page's own headline (``og:title`` / ``<title>``) or its description (``og:description``: The Guardian's and The
  Independent's style) opening with the marker, as in the feeds.

Nothing else is looked at: the article text is never searched for the word (an article *about* an exclusive is not one).
"""

from __future__ import annotations

import json
import re

from lxml import html as lxml_html

from ..flags import EXCLUSIVE_WORDS, is_exclusive

_WORDS = {w.lower() for w in EXCLUSIVE_WORDS} | {"exclusives", "exclusive story", "exclusive report", "scoop"}
_LABEL = re.compile(r"^\W*(?:" + "|".join(re.escape(w) for w in sorted(_WORDS, key=len, reverse=True)) + r")\W*$", re.IGNORECASE)
_KEYWORD_META = {
    "keywords", "news_keywords", "article:tag", "parsely-tags", "sailthru.tags", "sailthru.keywords", "dc.subject",
    "article:section", "parsely-section", "cxenseparse:recs:category",
}
_MAX_LABEL = 24  # characters: a label, not a sentence
_NOT_IN = ("nav", "footer", "aside", "form")
_ARTICLE_SCAN = 80  # elements at the top of the article that are looked at (the label sits above the headline)


def _is_label(text: str) -> bool:
    text = " ".join(text.split())
    return 0 < len(text) <= _MAX_LABEL and bool(_LABEL.match(text))


def _keyword_hit(value: str) -> bool:
    return any(_is_label(part) for part in re.split(r"[,;|]", value))


def _json_values(node: object) -> list[str]:
    """``keywords`` / ``articleSection`` strings anywhere in a structured-data block."""
    out: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("keywords", "articleSection", "genre") and isinstance(value, str):
                out.append(value)
            elif key in ("keywords", "articleSection", "genre") and isinstance(value, list):
                out.extend(str(v) for v in value if isinstance(v, str))
            else:
                out.extend(_json_values(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_json_values(item))
    return out


def page_is_exclusive(html: str) -> bool:
    """True when the page itself says the report is an exclusive (see the module text)."""
    if not html or len(html) < 200:
        return False
    try:
        doc = lxml_html.fromstring(html)
    except (ValueError, lxml_html.etree.ParserError):
        return False
    for meta in doc.iter("meta"):
        name = (meta.get("name") or meta.get("property") or "").lower()
        content = meta.get("content") or ""
        if name in _KEYWORD_META and _keyword_hit(content):
            return True
        if name in ("og:title", "twitter:title") and is_exclusive(content):
            return True
        if name in ("description", "og:description", "twitter:description") and is_exclusive(None, content):
            return True  # The Guardian / The Independent open the page description with "Exclusive:"
    for script in doc.iter("script"):
        if (script.get("type") or "").lower() != "application/ld+json" or not script.text:
            continue
        try:
            data = json.loads(script.text)
        except ValueError:
            continue
        if any(_keyword_hit(v) for v in _json_values(data)):
            return True
    title = doc.findtext(".//title")
    if title and is_exclusive(title):
        return True
    scope = doc.find(".//article")
    if scope is None:
        scope = doc.find(".//main")
    if scope is None:
        return False
    for index, el in enumerate(scope.iter()):
        if index >= _ARTICLE_SCAN:
            break
        if not isinstance(el.tag, str) or el.tag in ("script", "style") or len(el) > 0:
            continue  # only elements without children: a label is a leaf
        if any(a.tag in _NOT_IN for a in el.iterancestors()):
            continue
        if _is_label(el.text_content()):
            return True
    return False
