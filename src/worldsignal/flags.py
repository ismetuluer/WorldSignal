"""Badges read from the reports themselves: "exclusive" and "breaking".

* **Exclusive**: the publisher marks the headline itself ("Exclusive:", "ÖZEL HABER", "Exclusif :", "Эксклюзив",
  "حصري" …). Only a marker at the start of the headline counts, so everyday words such as "özel sektör" or
  "exclusive rights" in the middle of a headline do not. A bracketed marker closing the headline ("… (Exclusive)")
  counts too.
* **Breaking**: a story is spreading right now — at least ``BREAKING_SOURCES`` independent sources (media groups
  counted once, as in the score) reported it within the last ``BREAKING_WINDOW`` — or a report of the last
  ``MARKER_WINDOW`` is marked "BREAKING" / "Son dakika" / "عاجل" … by its publisher.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime, timedelta

BREAKING_SOURCES = 3
BREAKING_WINDOW = timedelta(minutes=60)
MARKER_WINDOW = timedelta(hours=2)

# Words that mean "exclusive" when a headline starts with them, in the catalog's languages.
EXCLUSIVE_WORDS = (
    "scoop", "exclusive", "özel haber", "özel", "exclusif", "exklusiv", "exclusiva", "exclusivo", "esclusiva", "esclusivo",
    "эксклюзив", "ексклюзив", "حصري", "حصريا", "خاص", "اختصاصی", "αποκλειστικό", "独家", "独家报道", "בלעדי",
)
BREAKING_WORDS = (
    "breaking", "breaking news", "son dakika", "son dakika haberi", "flaş", "flash", "urgent", "alert",
    "eilmeldung", "dernière minute", "última hora", "ultima hora", "ultim'ora", "ultimora", "срочно", "молния",
    "терміново", "عاجل", "فوری", "突发", "速報", "속보", "דחוף",
)


def _alternatives(words: Iterable[str]) -> str:
    return "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))


def _marker(words: Iterable[str], separator: str) -> re.Pattern[str]:
    """A marker word at the very start: "[Word] …", "(Word) …", or "Word" followed by ``separator``."""
    alternatives = _alternatives(words)
    return re.compile(rf"^\s*(?:[\[(]\s*(?:{alternatives})\s*[\])]|(?:{alternatives}){separator})", re.IGNORECASE)


# "Reuters exclusive: …" / "CNN Exclusive - …": a known outlet's name in front of the marker (not any word: "Why exclusive:").
_OUTLETS = ("Reuters", "Bloomberg", "CNN", "AP", "Axios", "Politico", "Semafor", "Sky News", "Fox News", "NBC News",
            "CBS News", "ABC News", "BBC", "Guardian", "Telegraph", "Daily Mail", "Newsweek", "Forbes", "Al Jazeera",
            "Haaretz", "Times of Israel", "Anadolu", "AA", "Yonhap", "Kyodo", "Xinhua")
_EXCLUSIVE_OWNED = re.compile(
    rf"^\s*(?:{'|'.join(re.escape(o) for o in _OUTLETS)})\s+(?:{_alternatives(EXCLUSIVE_WORDS)})\s*[:|\-–—]", re.IGNORECASE
)
# "Exclusive-Tesla …" is Reuters' own style, so a hyphen counts for "exclusive" …
_EXCLUSIVE = _marker(EXCLUSIVE_WORDS, r"\s*(?:[:|\-–—]|$)")
# … but "Flash-flood warning" is not a flash: breaking needs a colon, a bar, a spaced dash or nothing after it.
_BREAKING = _marker(BREAKING_WORDS, r"\s*(?:[:|–—]|\s-\s|$)")
# Upper-case "EXCLUSIVE" / "ÖZEL HABER" among the first words is also the publisher's marker.
_EXCLUSIVE_CAPS = re.compile(r"(?:^|\s)(?:EXCLUSIVE|ÖZEL HABER|EXCLUSIF|EXKLUSIV)(?:\s|:|$)")
# … and so is "(Exclusive)" / "[Exclusive]" closing the headline (Trend News Agency's style).
_EXCLUSIVE_END = re.compile(rf"[\[(]\s*(?:{_alternatives(EXCLUSIVE_WORDS)})\s*[\])]\s*$", re.IGNORECASE)


# An interview or report the publisher calls exclusive, or says it reported exclusively (summary / standfirst): "in an
# exclusive interview with ...", "exclusively reported by ...". "an exclusive look" (a magazine's own wording) is not one.
_EXCLUSIVE_PHRASE = re.compile(
    r"\bexclusive (?:interview|report|story|investigation|footage|photos|video|access)\b"
    r"|\bexclusively (?:reported|revealed|obtained|reveals)\b|\breported exclusively\b|\bözel röportaj\b|\bözel haber\b",
    re.IGNORECASE,
)


_REUTERS_EXCLUSIVE = re.compile(r"^\s*exclusive\s*[-–—]\s*\S|^\s*reuters\s+exclusive\s*[:|\-–—]", re.IGNORECASE)


def is_reuters_exclusive(title: str | None) -> bool:
    """Reuters' own exclusive headline as syndicated copies keep it ("Exclusive-…", "Exclusive - …", "Reuters exclusive: …")."""
    return bool(title and _REUTERS_EXCLUSIVE.search(title))


def is_exclusive(title: str | None, summary: str | None = None) -> bool:
    """The publisher itself says so: the marker in the headline, or opening the standfirst/summary ("Exclusive: …": The
    Guardian's and The Independent's style), or a phrase such as "exclusive interview" in the summary. Never a guess from the
    wording of a story ("sources say" is ordinary sourcing)."""
    if summary and (_EXCLUSIVE.search(summary[:80]) or _EXCLUSIVE_PHRASE.search(summary)):
        return True
    if not title:
        return False
    return bool(_EXCLUSIVE.search(title) or _EXCLUSIVE_CAPS.search(title[:40]) or _EXCLUSIVE_END.search(title)
                or _EXCLUSIVE_OWNED.search(title))


# Opinion pieces: the publisher's own section in the address ("/opinion/", "/commentisfree/", "/yazarlar/" …) or a
# label opening or closing the headline ("Opinion:", "Analysis |", "Görüş -", "… - opinion"). Measured on two days of the real feed: the
# address finds ~140, the headline ~12 more.
_OPINION_PATH = re.compile(
    r"/(?:opinions?|op-ed|oped|commentisfree|comment|columnists?|column|yazarlar|yazar|kose-yazilari|kose-yazisi"
    r"|analysis|analiz|editorials?|blogs?|ideas|perspectives?|meinung|kommentar|tribune|opinione)/",
    re.IGNORECASE,
)
_OPINION_TITLE = re.compile(
    r"^\s*(?:opinion|analysis|comment|column|editorial|op-ed|görüş|yorum|analiz|köşe yazısı|мнение|колонка"
    r"|analyse|meinung|kommentar|tribune|opinión)\s*[:|\-–—]",
    re.IGNORECASE,
)
# … or closing it ("… - opinion", "… | Analysis": The Jerusalem Post's style).
_OPINION_END = re.compile(r"\s[\-–—|]\s*(?:opinion|analysis|commentary|op-ed)\s*$", re.IGNORECASE)
# The feed's two virtual source groups: they cut across the catalog groups.
KINDS = ("exclusive", "opinion")


def is_opinion(title: str | None, url: str | None) -> bool:
    if url and _OPINION_PATH.search(url):
        return True
    return bool(title and (_OPINION_TITLE.search(title) or _OPINION_END.search(title)))


def article_kind(title: str | None, url: str | None, summary: str | None = None, page_exclusive: int | None = 0) -> str | None:
    """"exclusive", "opinion" or None; registered in SQLite as ``ws_kind(title, url, summary, page_exclusive)``."""
    if page_exclusive or is_exclusive(title, summary):
        return "exclusive"
    if is_opinion(title, url):
        return "opinion"
    return None


def group_condition(groups: Iterable[str]) -> tuple[str, list[str]] | None:
    """SQL for the feed's "source group" filter over ``s`` (sources) and ``a`` (articles): a report matches when its
    source is in one of the chosen catalog groups or it is one of the chosen kinds."""
    groups = list(dict.fromkeys(groups))
    catalog = [g for g in groups if g not in KINDS]
    kinds = [g for g in groups if g in KINDS]
    parts: list[str] = []
    if catalog:
        parts.append(f"s.catalog_group IN ({','.join('?' * len(catalog))})")
    if kinds:
        parts.append(f"ws_kind(a.title, a.url, a.summary, a.page_exclusive) IN ({','.join('?' * len(kinds))})")
    return (f"({' OR '.join(parts)})", catalog + kinds) if parts else None


def has_breaking_marker(title: str | None) -> bool:
    return bool(title and _BREAKING.search(title))


_BREAKING_PREFIX = re.compile(
    rf"^\s*(?:[\[(]\s*(?:{_alternatives(BREAKING_WORDS)})\s*[\])]|(?:{_alternatives(BREAKING_WORDS)})\s*(?:[:|–—]|\s-\s))\s*",
    re.IGNORECASE,
)


def strip_breaking_marker(title: str) -> str:
    """The headline without the publisher's "SON DAKİKA |" / "(URGENT)" label (as shown in a notification)."""
    stripped = _BREAKING_PREFIX.sub("", title, count=1).strip()
    return stripped or title.strip()


def is_breaking(reports: Iterable[tuple[str, datetime, str | None]], now: datetime) -> bool:
    """``reports``: (independent owner key, time, headline) of a story's reports."""
    recent_owners = set()
    for owner, at, title in reports:
        age = max(now - at, timedelta(0))
        if age <= BREAKING_WINDOW:
            recent_owners.add(owner)
        if age <= MARKER_WINDOW and has_breaking_marker(title):
            return True
    return len(recent_owners) >= BREAKING_SOURCES
