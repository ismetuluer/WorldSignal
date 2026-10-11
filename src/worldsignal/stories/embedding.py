"""What text is embedded, per model (shared by the app and tools/benchmark_embeddings.py)."""

from __future__ import annotations

import re

from ..flags import BREAKING_WORDS

# Some embedding models are trained with task prefixes; each gets its recommended one.
PREFIXES = {
    "embeddinggemma": "task: clustering | query: ",
    "qwen3-embedding": "Instruct: Identify the news event described in this article\nQuery: ",
}
SUMMARY_CHARS = 400

# Measured clustering settings per model family (titles only). Similarity scales differ a
# lot between models, so switching the model also switches to its measured values.
# threshold: best on the gold set (docs/GOMME_KARSILASTIRMA.md). cohesion: measured on the
# real article stream for bge-m3 only (docs/BIRLESTIRME_KARSILASTIRMA.md); 0 = not measured,
# nearest-neighbour rule alone.
RECOMMENDED = {
    "bge-m3": {"stories.threshold": 0.55, "stories.cohesion": 0.55},
    "qwen3-embedding": {"stories.threshold": 0.67, "stories.cohesion": 0.0},
    "embeddinggemma": {"stories.threshold": 0.84, "stories.cohesion": 0.0},
}


def prefix_for(model: str) -> str:
    base = model.split(":")[0]
    return PREFIXES.get(base, "")


def recommended_settings(model: str) -> dict[str, float]:
    return dict(RECOMMENDED.get(model.split(":")[0], {}))


# Headings that are not headlines. Matching is by headline only, so a heading that says nothing ("Flaş", "Kısa haberler",
# "Morning update") is near-identical to every other one and they pull each other, and whatever sits next to them, into
# one story that never ends (seen: 176 reports from 9 sources over two weeks). Two kinds:
#   "lead": the headline is only a label ("Flaş", "Son dakika //2//") and the report itself is in the summary, so the summary's
#           lead is embedded instead (DHA's flash reports);
#   "solo": a short heading repeated by the same source over a digest or an empty summary (a morning round-up, "Here's the latest"):
#           there is nothing to match it by, so it is never joined to a story.
HEADING_RULE = 1  # raise when the rule changes: the stored stories are then brought to it once (worker.step)
HEADING_REPEATS = 3  # the same short heading, same source, within HEADING_DAYS, this report included
HEADING_DAYS = 30
HEADING_WORDS = 3  # a repeated headline of more words is a real headline that was published again, not a heading
LEAD_MIN_CHARS = 30  # a summary shorter than this carries no report
DIGEST_CHARS = 600  # a repeated heading over a longer summary is a round-up of many items, not one report
LEAD_CHARS = 300
_NON_LETTERS = re.compile(r"[\W\d_]+")
# "ANKARA, (DHA)- ", "İSTANBUL (AA) -": the agency's place line, which says nothing about the event.
_DATELINE = re.compile(r"^\s*[^\W\d_][^\W\d_ .'’-]{1,30}(?: [^\W\d_]{2,20})?,?\s*\(?[A-Za-zÇĞİÖŞÜçğıöşü]{2,10}\)?\s*[-–—]\s*")
_LABELS = {w.lower() for w in BREAKING_WORDS}


def is_label_only(title: str) -> bool:
    """The headline is nothing but a breaking-news label ("Flaş", "FLAŞ", "flaş //3//")."""
    return _NON_LETTERS.sub(" ", title).strip().lower() in _LABELS


def lead_text(summary: str) -> str:
    """The start of a summary without the agency's place line."""
    return _DATELINE.sub("", summary.strip(), count=1).strip()[:LEAD_CHARS]


def heading_kind(title: str, summary: str | None, repeats: int) -> str | None:
    """None (an ordinary headline), "lead" or "solo": see the comment above. ``repeats``: how many times this source
    published this very headline within HEADING_DAYS (including this report)."""
    summary = (summary or "").strip()
    if is_label_only(title):
        return "lead" if len(summary) >= LEAD_MIN_CHARS else "solo"
    if repeats < HEADING_REPEATS or len(title.split()) > HEADING_WORDS:
        return None
    if LEAD_MIN_CHARS <= len(summary) <= DIGEST_CHARS and summary.lower() != title.strip().lower():
        return "lead"
    return "solo"


def embed_text(model: str, title: str, summary: str, *, with_summary: bool, kind: str | None = None) -> str:
    if kind == "lead" and lead_text(summary or ""):
        return prefix_for(model) + lead_text(summary)
    text = title.strip()
    summary = (summary or "").strip()
    if with_summary and summary and summary != text:
        text = f"{text}. {summary[:SUMMARY_CHARS]}"
    return prefix_for(model) + text
