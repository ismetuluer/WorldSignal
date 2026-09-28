"""Badges read from the reports themselves: "exclusive" and "breaking".

* **Exclusive**: the publisher marks the headline itself ("Exclusive:", "ÖZEL HABER", "Exclusif :", "Эксклюзив",
  "حصري" …). Only a marker at the start of the headline counts, so everyday words such as "özel sektör" or
  "exclusive rights" in the middle of a headline do not.
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
    "exclusive", "özel haber", "özel", "exclusif", "exklusiv", "exclusiva", "exclusivo", "esclusiva", "esclusivo",
    "эксклюзив", "ексклюзив", "حصري", "حصريا", "خاص", "اختصاصی", "αποκλειστικό", "独家", "独家报道", "בלעדי",
)
BREAKING_WORDS = (
    "breaking", "breaking news", "son dakika", "son dakika haberi", "flaş", "flash", "urgent", "alert",
    "eilmeldung", "dernière minute", "última hora", "ultima hora", "ultim'ora", "ultimora", "срочно", "молния",
    "терміново", "عاجل", "فوری", "突发", "速報", "속보", "דחוף",
)


def _marker(words: Iterable[str], separator: str) -> re.Pattern[str]:
    """A marker word at the very start: "[Word] …", "(Word) …", or "Word" followed by ``separator``."""
    alternatives = "|".join(re.escape(w) for w in sorted(set(words), key=len, reverse=True))
    return re.compile(rf"^\s*(?:[\[(]\s*(?:{alternatives})\s*[\])]|(?:{alternatives}){separator})", re.IGNORECASE)


# "Exclusive-Tesla …" is Reuters' own style, so a hyphen counts for "exclusive" …
_EXCLUSIVE = _marker(EXCLUSIVE_WORDS, r"\s*(?:[:|\-–—]|$)")
# … but "Flash-flood warning" is not a flash: breaking needs a colon, a bar, a spaced dash or nothing after it.
_BREAKING = _marker(BREAKING_WORDS, r"\s*(?:[:|–—]|\s-\s|$)")
# Upper-case "EXCLUSIVE" / "ÖZEL HABER" among the first words is also the publisher's marker.
_EXCLUSIVE_CAPS = re.compile(r"(?:^|\s)(?:EXCLUSIVE|ÖZEL HABER|EXCLUSIF|EXKLUSIV)(?:\s|:|$)")


def is_exclusive(title: str | None) -> bool:
    if not title:
        return False
    return bool(_EXCLUSIVE.search(title) or _EXCLUSIVE_CAPS.search(title[:40]))


def has_breaking_marker(title: str | None) -> bool:
    return bool(title and _BREAKING.search(title))


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
