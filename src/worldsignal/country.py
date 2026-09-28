""""My country" relevance: which reports concern the user's home country (default: Windows' region).

The rules are the ones World Signal always had for Türkiye, with the country as a setting. They are applied when
the AI has read a report (language models proved unreliable at geography, so the AI only lists facts):

* **direct**: the AI lists the country among the report's countries, or the country's name is in the text
  (for Türkiye also the AI's "Türkiye is mentioned" answer);
* **indirect**: the AI lists a neighbour or a country the user chose as related, or found a topic the user chose.

For Türkiye the defaults are the pre-0.9 rules exactly: its word list, its neighbours (with Cyprus), the Turkic
states as related countries and all six topics. Country names and land neighbours come from
catalog/countries.json (tools/make_countries.py: Wikidata names, GeoNames neighbours).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import cache
from typing import Any

from .paths import resource_dir

log = logging.getLogger(__name__)

# The topics the AI can recognise in a report (ai/enrich.py asks for them).
TOPICS = ("black_sea", "eastern_mediterranean", "nato", "eu_enlargement", "migration", "turkic_states")
TURKIC_STATES = ("AZ", "KZ", "UZ", "KG", "TM")
DEFAULT_COUNTRY = "TR"
# Raise when the rules below change: every stored rating is then made again (home_sync.py).
RULES_VERSION = 1

# Türkiye's word list from before 0.9 (the data's plain names would miss "Türk", "Erdoğan", "Турецк"…).
NAME_WORDS: dict[str, str] = {
    "TR": r"Türkiye|Turkiye|\bTurkey\b|\bTurkish|\bTürk|\bAnkara\b|Erdoğan|Erdogan|İstanbul|\bIstanbul|"
          r"Türkei|Turquie|Turquía|Turchia|Турци|Турецк|تركيا|التركي",
}

# Neighbours the land-border data leaves out but that the Türkiye rules had (sea neighbour Cyprus).
EXTRA_NEIGHBOURS: dict[str, tuple[str, ...]] = {"TR": ("CY",)}

_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")
_ARABIC = re.compile(r"[؀-ۿ]")


@cache
def countries() -> dict[str, dict[str, Any]]:
    path = resource_dir() / "catalog" / "countries.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["countries"]
    except (OSError, ValueError, KeyError):
        log.exception("Country data missing or broken: %s", path)
        return {}


def label(code: str, lang: str) -> str:
    c = countries().get(code, {})
    names = c.get("label", {})
    return names.get(lang) or names.get("en") or code


def _term_pattern(term: str) -> str:
    """A name matches at a word start. Long names also match with suffixes ("Güney Afrika'nın"); short ones only
    as whole words ("Niger" must not hit "Nigeria")."""
    escaped = re.escape(term)
    if _CJK.search(term):
        return escaped  # no spaces between words
    if _ARABIC.search(term):
        return rf"(?<!\w)(?:ال)?{escaped}"  # the article is written together with the word
    if len(term) >= 6:
        return rf"(?<!\w){escaped}"
    return rf"(?<!\w){escaped}(?!\w)"


def name_pattern(code: str, keywords: tuple[str, ...] = ()) -> re.Pattern[str] | None:
    """The words that mean "the country is named in the text": Türkiye's list, or the country's name in the
    data's languages; plus the user's own extra words."""
    parts = [NAME_WORDS[code]] if code in NAME_WORDS else [
        _term_pattern(n) for n in sorted(set(countries().get(code, {}).get("label", {}).values()), key=len, reverse=True)
    ]
    parts += [_term_pattern(k) for k in keywords]
    return re.compile("|".join(parts)) if parts else None


@dataclass(frozen=True)
class HomeProfile:
    """The user's country and what counts as related to it."""

    code: str
    related: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    keywords: tuple[str, ...] = ()
    neighbours: tuple[str, ...] = ()
    names: re.Pattern[str] | None = field(default=None, compare=False, repr=False)

    @property
    def key(self) -> str:
        """Changes whenever the rules change: stored relevance is recomputed then."""
        return json.dumps([RULES_VERSION, self.code, sorted(self.related), sorted(self.topics), sorted(self.keywords)])

    def relevance(self, text: str, countries_in_text: list[str], topics: list[str],
                  mentions_home: bool = False) -> tuple[str, list[str]]:
        """(level, links explaining why) for a report the AI has read. ``countries_in_text`` and ``topics`` are
        the AI's findings. Links: "home_mentioned", "neighbour:GR", "related:KZ", "topic:nato"."""
        if mentions_home or self.code in countries_in_text or (self.names is not None and self.names.search(text)):
            return "direct", ["home_mentioned"]
        links = [f"neighbour:{c}" for c in countries_in_text if c in self.neighbours]
        links += [f"related:{c}" for c in countries_in_text if c in self.related and c not in self.neighbours]
        links += [f"topic:{t}" for t in topics if t in self.topics]
        return ("indirect", links) if links else ("none", [])


def profile(prefs: dict[str, Any], system_country: str | None = None) -> HomeProfile:
    """Build the profile from the settings ("home.*"); the country "" means Windows' region."""
    code = str(prefs.get("home.country") or "").upper() or (system_country or "") or DEFAULT_COUNTRY
    data = countries().get(code)
    if data is None:
        code, data = DEFAULT_COUNTRY, countries().get(DEFAULT_COUNTRY, {})
    related = prefs.get("home.related")
    topics = prefs.get("home.topics")
    if related is None:
        related = list(TURKIC_STATES) if code == "TR" else []
    if topics is None:
        topics = list(TOPICS) if code == "TR" else []
    keywords = tuple(dict.fromkeys(k.strip() for k in prefs.get("home.keywords") or [] if k.strip()))
    return HomeProfile(
        code=code,
        related=tuple(r for r in dict.fromkeys(related) if r != code and r in countries()),
        topics=tuple(t for t in dict.fromkeys(topics) if t in TOPICS),
        keywords=keywords,
        neighbours=tuple(dict.fromkeys([*data.get("neighbours", []), *EXTRA_NEIGHBOURS.get(code, ())])),
        names=name_pattern(code, keywords),
    )


HOME_KEYS = ("home.country", "home.related", "home.topics", "home.keywords")


class HomeState:
    """The current profile, rebuilt only when a "home.*" setting changes (compiling the name pattern)."""

    def __init__(self, get_preferences: Any, system_country: str | None = None) -> None:
        self._get = get_preferences
        self.system_country = system_country
        self._cache: tuple[str, HomeProfile] | None = None

    def profile(self) -> HomeProfile:
        prefs = self._get()
        key = json.dumps([prefs.get(k) for k in HOME_KEYS])
        if self._cache is None or self._cache[0] != key:
            self._cache = (key, profile(prefs, self.system_country))
        return self._cache[1]


def windows_country() -> str | None:
    """The country set in Windows (Settings → Time & language → Region), as an ISO code."""
    try:
        import ctypes

        buf = ctypes.create_unicode_buffer(16)
        if ctypes.windll.kernel32.GetUserDefaultGeoName(buf, len(buf)) > 0:
            value = buf.value.upper()
            return value if re.fullmatch(r"[A-Z]{2}", value) else None
    except (AttributeError, OSError):
        return None
    return None
