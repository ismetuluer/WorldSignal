"""Compare story clustering rules on the real article stream (not only the gold set).

The gold set alone (tools/embedding_gold.json, 95 articles) cannot show *chaining*:
with single-link clustering an article joins a story because it resembles one
member, the next joins because it resembles *that* one, and unrelated events end
up in one story. Chaining only appears among thousands of articles. So this tool
replays every article of the real database from the gold period in time order
(the gold articles are part of that stream) and scores the rules on the gold
articles, plus stream statistics (story sizes).

Rules (all online, 72 h window, as in the app):
* nn        - join the story of the most similar clustered article if sim >= t (Faz 3 v1)
* avg       - story with mean similarity to its members >= t (closest member wins)
* hybrid    - story must have a member with sim >= t1 AND mean similarity >= t2
* centroid  - cosine to the story's mean vector >= t

Usage (Ollama running with bge-m3): .venv\\Scripts\\python tools\\benchmark_clustering.py
Reads the real database read-only. Vectors are cached in .devdata/benchmark/.
Writes docs/BIRLESTIRME_KARSILASTIRMA.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from worldsignal.ai.ollama import OllamaClient  # noqa: E402
from worldsignal.stories.embedding import embed_text  # noqa: E402
from worldsignal.repo.settings import DEFAULTS  # noqa: E402
from worldsignal.stories.worker import choose_story  # noqa: E402

MODEL = "bge-m3:latest"
WINDOW = timedelta(hours=72)
GOLD = ROOT / "tools" / "embedding_gold.json"
CACHE = ROOT / ".devdata" / "benchmark" / "stream_vectors.npz"
REPORT = ROOT / "docs" / "BIRLESTIRME_KARSILASTIRMA.md"


def parse(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")


def load_stream(gold_ids: set[int]) -> list[dict]:
    db = Path(os.environ["LOCALAPPDATA"]) / "WorldSignal" / "worldsignal.db"
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    first = conn.execute(
        f"SELECT MIN(sort_at) FROM articles WHERE id IN ({','.join('?' * len(gold_ids))})", list(gold_ids)
    ).fetchone()[0]
    since = (parse(first) - WINDOW).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = conn.execute(
        """SELECT a.id, a.title, a.sort_at, COALESCE(NULLIF(s.owner, ''), 'src:' || s.id) AS owner
           FROM articles a JOIN sources s ON s.id = a.source_id
           WHERE a.sort_at >= ? AND s.enabled = 1 ORDER BY a.sort_at, a.id""",
        (since,),
    ).fetchall()
    return [dict(r) for r in rows]


async def vectors_for(stream: list[dict]) -> np.ndarray:
    ids = np.array([a["id"] for a in stream])
    if CACHE.exists():
        cached = np.load(CACHE)
        if str(cached["model"]) == MODEL and np.array_equal(cached["ids"], ids):
            return cached["vectors"]
    client = OllamaClient()
    out: list[list[float]] = []
    t0 = time.perf_counter()
    for i in range(0, len(stream), 64):
        batch = stream[i : i + 64]
        out += await client.embed(MODEL, [embed_text(MODEL, a["title"], "", with_summary=False) for a in batch])
        print(f"\r{len(out)}/{len(stream)} ({len(out) / (time.perf_counter() - t0):.1f}/s)", end="", flush=True)
    print()
    vecs = np.array(out, dtype=np.float32)
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    np.savez(CACHE, ids=ids, vectors=vecs, model=MODEL)
    return vecs


def cluster(sim: np.ndarray, times: np.ndarray, vecs: np.ndarray, rule: str, t1: float, t2: float = 0.0) -> np.ndarray:
    """Replay the stream. nn and hybrid use the app's own rule (``choose_story``)."""
    n = len(times)
    story = np.full(n, -1, dtype=np.int64)
    sums = np.zeros_like(vecs)  # centroid rule: running sum of member vectors per story
    next_id = 0
    start = 0
    for i in range(n):
        while times[start] < times[i] - WINDOW.total_seconds():
            start += 1
        chosen: int | None = None
        if i > start:
            s = sim[i, start:i]
            st = story[start:i]
            if rule == "nn":
                chosen, _ = choose_story(s, st, t1, -1.0)
            elif rule == "hybrid":
                chosen, _ = choose_story(s, st, t1, t2)
            elif rule == "avg":
                chosen, _ = choose_story(s, st, -1.0, t1)
            else:  # centroid
                ids = np.unique(st)
                norms = np.sqrt((sums[ids] ** 2).sum(axis=1))
                cos = (sums[ids] @ vecs[i]) / np.where(norms > 0, norms, 1.0)
                j = int(cos.argmax())
                chosen = int(ids[j]) if cos[j] >= t1 else None
        if chosen is None:
            chosen = next_id
            next_id += 1
        story[i] = chosen
        sums[chosen] += vecs[i]
    return story


def bcubed(pred: list[int], truth: list[str]) -> tuple[float, float, float]:
    n = len(pred)
    p = r = 0.0
    for i in range(n):
        same_pred = {j for j in range(n) if pred[j] == pred[i]}
        same_true = {j for j in range(n) if truth[j] == truth[i]}
        inter = len(same_pred & same_true)
        p += inter / len(same_pred)
        r += inter / len(same_true)
    p, r = p / n, r / n
    return p, r, 2 * p * r / (p + r)


def evaluate(story: np.ndarray, gold_idx: list[int], gold_labels: list[str]) -> dict:
    p, r, f = bcubed([int(story[i]) for i in gold_idx], gold_labels)
    sizes = np.bincount(story)
    return {
        "precision": round(p, 3), "recall": round(r, 3), "f1": round(f, 3),
        "stories": int(len(sizes)), "largest": int(sizes.max()),
        "in_big": round(float(sizes[sizes >= 40].sum() / len(story)), 3),
    }


async def main() -> None:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    label_of = {aid: ev for ev, ids in gold["events"].items() for aid in ids}
    label_of.update({aid: f"single_{aid}" for aid in gold["singletons"]})
    stream = load_stream(set(label_of))
    vecs = await vectors_for(stream)
    times = np.array([parse(a["sort_at"]).timestamp() for a in stream])
    sim = vecs @ vecs.T
    pos = {a["id"]: i for i, a in enumerate(stream)}
    gold_idx = [pos[aid] for aid in label_of if aid in pos]
    gold_labels = [label_of[stream[i]["id"]] for i in gold_idx]
    print(f"{len(stream)} articles in the stream, {len(gold_idx)} gold")

    runs: list[tuple[str, str, dict]] = []

    def run(rule: str, name: str, t1: float, t2: float = 0.0) -> None:
        t0 = time.perf_counter()
        res = evaluate(cluster(sim, times, vecs, rule, t1, t2), gold_idx, gold_labels)
        runs.append((rule, name, res))
        print(f"{rule:<9}{name:<16}{res}  ({time.perf_counter() - t0:.0f}s)", flush=True)

    for t in (0.55, 0.6, 0.65, 0.7):
        run("nn", f"t={t}", t)
    for t in (0.45, 0.5, 0.55, 0.6):
        run("avg", f"t={t}", t)
    for t in (0.6, 0.65, 0.7, 0.75):
        run("centroid", f"t={t}", t)
    for t1 in (0.55, 0.6, 0.65):
        for t2 in (0.4, 0.45, 0.5, 0.55):
            run("hybrid", f"t1={t1} t2={t2}", t1, t2)

    lines = [
        "# Hikâye birleştirme kuralı karşılaştırması (Faz 3)",
        "",
        f"`tools/benchmark_clustering.py` ile üretilir. Gerçek veritabanındaki {len(stream)} haberin tamamı zaman sırasıyla "
        f"yeniden oynatıldı (model {MODEL}, yalnızca başlık, 72 saatlik pencere). Doğruluk, bu akışın içindeki "
        f"{len(gold_idx)} elle etiketlenmiş haber (`tools/embedding_gold.json`) üzerinde ölçüldü.",
        "",
        "- **Kesinlik**: bir hikâyedeki haberlerin gerçekten aynı olay olma oranı (düşükse alakasız olaylar karışıyor).",
        "- **Duyarlılık**: aynı olayın haberlerinin gerçekten aynı hikâyede toplanma oranı.",
        "- **En büyük**: akıştaki en kalabalık hikâyenin haber sayısı; **Büyük hikâyelerde**: 40+ haberli hikâyelere düşen haber "
        "oranı (zincirlenmenin işareti).",
        "",
        "| Kural | Eşik | Kesinlik | Duyarlılık | F1 | Hikâye sayısı | En büyük | Büyük hikâyelerde |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for rule, name, r in runs:
        lines.append(f"| {rule} | {name} | {r['precision']} | {r['recall']} | {r['f1']} | {r['stories']} | {r['largest']} | {r['in_big']} |")
    # What the biggest stories look like: chaining shows up as unrelated titles in one story.
    t1, t2 = float(DEFAULTS["stories.threshold"]), float(DEFAULTS["stories.cohesion"])
    for title, rule, a, c in (
        ("eski kural (yalnızca en yakın haber ≥ 0,55)", "nn", 0.55, 0.0),
        (f"uygulamanın varsayılanı (en yakın ≥ {t1}, ortalama ≥ {t2})", "hybrid", t1, t2),
    ):
        story = cluster(sim, times, vecs, rule, a, c)
        sizes = np.bincount(story)
        lines += ["", f"## En büyük 5 hikâyeden örnek başlıklar — {title}", ""]
        for k in np.argsort(sizes)[-5:][::-1]:
            idx = np.flatnonzero(story == k)
            step = max(1, len(idx) // 6)
            lines.append(f"- **{sizes[k]} haber**: " + " · ".join(stream[i]["title"][:70] for i in idx[::step][:6]))
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
