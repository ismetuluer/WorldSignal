"""Story importance score: explainable, no black box.

score = 100 x weighted average of four components, each 0..1:

* sources   - independent sources (one per media group, weighted by the
              source's reliability), at most ``REGION_CAP`` per region, so a
              region with many outlets (the user's own press) cannot fill it
              alone. log-scaled: 1 source is little, ``SOURCES_FOR_MAX`` is max.
* freshness - how recent the latest report is (half-life 8 h), blended with
              how fast it is spreading (independent sources in the last 3 h).
* turkey    - 1.0 if any member is directly about Türkiye, 0.5 if indirectly.
* interest  - the user's interest profile (keywords, categories, regions).

Every component also yields a short tag ("9 kaynak", "3 saatte 5 kaynak",
"Türkiye bağlantısı", "İlgi alanı: enerji") that the UI shows on the card.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from ..textnorm import fold_for_search

DEFAULT_WEIGHTS = {"sources": 0.45, "freshness": 0.25, "turkey": 0.20, "interest": 0.10}
SOURCES_FOR_MAX = 40
REGION_CAP = 6
FRESHNESS_HALF_LIFE_H = 8.0
SPREAD_WINDOW = timedelta(hours=3)
SPREAD_FOR_MAX = 4
SPREADING_TAG_MIN = 3


@dataclass
class Member:
    article_id: int
    owner_key: str  # media group, or the source itself when it has none
    reliability: float
    sort_at: datetime
    region: str
    text: str  # title + Turkish AI title, used for keyword matching
    category: str | None = None
    turkey_relevance: str | None = None


@dataclass
class Interest:
    keywords: Sequence[str] = ()
    categories: Sequence[str] = ()
    regions: Sequence[str] = ()


@dataclass
class ScoreResult:
    score: float
    components: dict[str, float]
    tags: list[dict[str, Any]] = field(default_factory=list)
    source_count: int = 0
    turkey_relevance: str = "none"

    def parts(self) -> dict[str, Any]:
        return {"components": self.components, "tags": self.tags}


def independent_sources(members: Sequence[Member]) -> dict[str, float]:
    """media group -> highest reliability among its outlets in the story."""
    owners: dict[str, float] = {}
    for m in members:
        owners[m.owner_key] = max(owners.get(m.owner_key, 0.0), m.reliability)
    return owners


def counted_sources(members: Sequence[Member], region_cap: int | None = None) -> float:
    """The reliability-weighted independent sources the score counts: in each region only the ``region_cap`` most
    reliable media groups."""
    cap = REGION_CAP if region_cap is None else region_cap
    best: dict[str, tuple[float, str]] = {}
    for m in members:
        if m.owner_key not in best or m.reliability > best[m.owner_key][0]:
            best[m.owner_key] = (m.reliability, m.region)
    by_region: dict[str, list[float]] = {}
    for reliability, region in best.values():
        by_region.setdefault(region, []).append(reliability)
    return sum(sum(sorted(values, reverse=True)[:cap]) for values in by_region.values())


def score_story(
    members: Sequence[Member],
    now: datetime,
    *,
    weights: dict[str, float] | None = None,
    interest: Interest | None = None,
    category: str | None = None,
    story_relevance: str | None = None,
) -> ScoreResult:
    """``story_relevance``: the rating of the story's own AI facts (its summary), next to its members' ratings."""
    if not members:
        return ScoreResult(0.0, {k: 0.0 for k in DEFAULT_WEIGHTS})
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    interest = interest or Interest()
    tags: list[dict[str, Any]] = []

    owners = independent_sources(members)
    weighted = counted_sources(members)
    sources_c = min(1.0, math.log1p(weighted) / math.log1p(SOURCES_FOR_MAX))
    tags.append({"kind": "sources", "count": len(owners)})

    latest = max(m.sort_at for m in members)
    age_h = max(0.0, (now - latest).total_seconds() / 3600)
    decay = 0.5 ** (age_h / FRESHNESS_HALF_LIFE_H)
    recent_owners = {m.owner_key for m in members if now - m.sort_at <= SPREAD_WINDOW}
    spread = min(1.0, len(recent_owners) / SPREAD_FOR_MAX)
    freshness_c = 0.7 * decay + 0.3 * spread
    tags.append({"kind": "age", "hours": round(age_h, 1)})
    if len(recent_owners) >= SPREADING_TAG_MIN:
        tags.append({"kind": "spreading", "count": len(recent_owners), "hours": 3})

    levels = {m.turkey_relevance for m in members} | {story_relevance}
    turkey = "direct" if "direct" in levels else "indirect" if "indirect" in levels else "none"
    turkey_c = {"direct": 1.0, "indirect": 0.5, "none": 0.0}[turkey]
    if turkey != "none":
        tags.append({"kind": "turkey", "level": turkey})

    matches: list[str] = []
    folded = fold_for_search(" ".join(m.text for m in members))
    for kw in interest.keywords:
        k = fold_for_search(kw).strip()
        if k and k in folded and kw not in matches:
            matches.append(kw)
    if category and category in interest.categories:
        matches.append(f"category:{category}")
    regions = {m.region for m in members}
    matches += [f"region:{r}" for r in interest.regions if r in regions]
    interest_c = min(1.0, 0.5 * len(matches))
    if matches:
        tags.append({"kind": "interest", "matches": matches[:3]})

    components = {
        "sources": round(sources_c, 3),
        "freshness": round(freshness_c, 3),
        "turkey": turkey_c,
        "interest": round(interest_c, 3),
    }
    total_w = sum(max(0.0, w) for w in weights.values()) or 1.0
    score = 100 * sum(max(0.0, weights[k]) * components[k] for k in components) / total_w
    return ScoreResult(round(score, 1), components, tags, len(owners), turkey)
