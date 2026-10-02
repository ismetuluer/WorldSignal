"""What text is embedded, per model (shared by the app and tools/benchmark_embeddings.py)."""

from __future__ import annotations

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


def embed_text(model: str, title: str, summary: str, *, with_summary: bool) -> str:
    text = title.strip()
    summary = (summary or "").strip()
    if with_summary and summary and summary != text:
        text = f"{text}. {summary[:SUMMARY_CHARS]}"
    return prefix_for(model) + text
