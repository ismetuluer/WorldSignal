"""Compare embedding models for story clustering on hand-labelled real articles.

Usage (Ollama running, models pulled):
    .venv\\Scripts\\python tools\\benchmark_embeddings.py [model ...]

Gold data: tools/embedding_gold.json (same-event groups across languages plus
unrelated singletons and deliberately hard negatives). For each model and text
variant it reports:

* pair AUC            - how well same-event pairs score above different-event pairs
* best pair F1 / threshold
* clustering B-cubed F1 when articles arrive one by one in time order, using the
  nearest-neighbour rule (best threshold on a grid); the app's extra anti-chaining
  condition is measured on the full stream by tools/benchmark_clustering.py
* hard negatives      - highest similarity between designated look-alike events
* speed on CPU (articles per second)

Writes docs/GOMME_KARSILASTIRMA.md.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from worldsignal.ai.ollama import OllamaClient  # noqa: E402
from worldsignal.stories.embedding import embed_text  # noqa: E402

MODELS = ["bge-m3:latest", "qwen3-embedding:0.6b", "embeddinggemma:latest"]
GOLD = ROOT / "tools" / "embedding_gold.json"
SNAPSHOT = ROOT / ".devdata" / "benchmark" / "embed_gold_texts.json"
REPORT = ROOT / "docs" / "GOMME_KARSILASTIRMA.md"
HARD_NEGATIVES = [
    ("hormuz_drone", "hormuz_plan_rejected"),
    ("sayan_kaya", "ozata_resignation"),
    ("taiz_saudi_strike", "taiz_government_bombing"),
]


def load_articles() -> list[dict]:
    gold = json.loads(GOLD.read_text(encoding="utf-8"))
    if SNAPSHOT.exists():
        return json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    label_of = {aid: ev for ev, ids in gold["events"].items() for aid in ids}
    for aid in gold["singletons"]:
        label_of[aid] = f"single_{aid}"
    db = Path(os.environ["LOCALAPPDATA"]) / "WorldSignal" / "worldsignal.db"
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        f"""SELECT a.id, a.title, a.summary, a.sort_at, COALESCE(a.language, s.language) AS lang, s.name AS source
            FROM articles a JOIN sources s ON s.id = a.source_id
            WHERE a.id IN ({",".join("?" * len(label_of))}) ORDER BY a.sort_at""",
        list(label_of),
    ).fetchall()
    articles = [{**dict(r), "label": label_of[r["id"]]} for r in rows]
    missing = set(label_of) - {a["id"] for a in articles}
    if missing:
        raise SystemExit(f"Gold ids missing from database: {sorted(missing)}")
    SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
    SNAPSHOT.write_text(json.dumps(articles, ensure_ascii=False, indent=1), encoding="utf-8")
    return articles


def auc(pos: np.ndarray, neg: np.ndarray) -> float:
    scores = np.concatenate([pos, neg])
    ranks = scores.argsort().argsort() + 1
    return float((ranks[: len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def pair_f1(sim: np.ndarray, same: np.ndarray, t: float) -> float:
    iu = np.triu_indices(len(sim), 1)
    pred, truth = sim[iu] >= t, same[iu]
    tp = float((pred & truth).sum())
    if tp == 0:
        return 0.0
    p, r = tp / pred.sum(), tp / truth.sum()
    return 2 * p * r / (p + r)


def greedy_clusters(vectors: np.ndarray, t: float) -> list[int]:
    """Online nearest-neighbour rule: join the story whose closest member is most similar, if >= t."""
    assign: list[int] = []
    for i in range(len(vectors)):
        if i == 0:
            assign.append(0)
            continue
        sims = vectors[:i] @ vectors[i]
        best = int(sims.argmax())
        assign.append(assign[best] if sims[best] >= t else max(assign) + 1)
    return assign


def bcubed_f1(pred: list[int], truth: list[str]) -> float:
    n = len(pred)
    p = r = 0.0
    for i in range(n):
        same_pred = {j for j in range(n) if pred[j] == pred[i]}
        same_true = {j for j in range(n) if truth[j] == truth[i]}
        inter = len(same_pred & same_true)
        p += inter / len(same_pred)
        r += inter / len(same_true)
    p, r = p / n, r / n
    return 2 * p * r / (p + r)


async def evaluate(client: OllamaClient, model: str, articles: list[dict]) -> dict:
    labels = [a["label"] for a in articles]
    same = np.array([[x == y for y in labels] for x in labels])
    out: dict = {"model": model, "variants": {}}
    for variant in ("title", "title+summary"):
        texts = [embed_text(model, a["title"], a["summary"], with_summary=variant == "title+summary") for a in articles]
        await client.embed(model, texts[:1])  # load the model first so timing measures inference only
        t0 = time.perf_counter()
        vecs = np.array(await client.embed(model, texts), dtype=np.float32)
        seconds = time.perf_counter() - t0
        vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
        sim = vecs @ vecs.T
        iu = np.triu_indices(len(sim), 1)
        pos, neg = sim[iu][same[iu]], sim[iu][~same[iu]]
        grid = np.round(np.arange(0.40, 0.96, 0.01), 2)
        f1s = [pair_f1(sim, same, t) for t in grid]
        clus = [bcubed_f1(greedy_clusters(vecs, t), labels) for t in grid]
        hard = {}
        for a_ev, b_ev in HARD_NEGATIVES:
            ia = [i for i, lab in enumerate(labels) if lab == a_ev]
            ib = [i for i, lab in enumerate(labels) if lab == b_ev]
            hard[f"{a_ev}~{b_ev}"] = round(float(sim[np.ix_(ia, ib)].max()), 3)
        best = int(np.argmax(clus))
        out["variants"][variant] = {
            "auc": round(auc(pos, neg), 4),
            "pos_median": round(float(np.median(pos)), 3),
            "neg_p99": round(float(np.percentile(neg, 99)), 3),
            "best_pair_f1": round(max(f1s), 3),
            "best_pair_t": float(grid[int(np.argmax(f1s))]),
            "best_cluster_f1": round(clus[best], 3),
            "best_cluster_t": float(grid[best]),
            "cluster_f1_curve": {str(t): round(f, 3) for t, f in zip(grid, clus, strict=True) if round(t * 100) % 5 == 0},
            "hard_negative_max": hard,
            "per_second": round(len(texts) / seconds, 1),
            "dims": int(vecs.shape[1]),
        }
        v = out["variants"][variant]
        print(f"{model:<24}{variant:<15} AUC={v['auc']} clusterF1={v['best_cluster_f1']}@{v['best_cluster_t']} "
              f"pairF1={v['best_pair_f1']}@{v['best_pair_t']} hard={hard} {v['per_second']}/s")
    return out


def write_report(articles: list[dict], results: list[dict]) -> None:
    langs = sorted({a["lang"] for a in articles})
    events = sorted({a["label"] for a in articles if not a["label"].startswith("single_")})
    lines = [
        "# Gömme (embedding) modeli karşılaştırması (Faz 3)",
        "",
        "`tools/benchmark_embeddings.py` ile üretilir. Doğru cevap anahtarı: `tools/embedding_gold.json` — veritabanındaki gerçek "
        f"haberlerden elle doğrulanmış {len(events)} olay ({sum(1 for a in articles if not a['label'].startswith('single_'))} haber) "
        f"ve {sum(1 for a in articles if a['label'].startswith('single_'))} ilgisiz haber; diller: {', '.join(langs)}.",
        "Modeller işlemcide (CPU) çalıştırıldı; ekran kartı kullanılmadı.",
        "",
        "- **AUC**: aynı olaya ait haber çiftlerinin farklı olay çiftlerinden daha benzer bulunma oranı (1,0 = kusursuz).",
        "- **Kümeleme F1**: haberler zaman sırasıyla tek tek geldiğinde “en yakın habere katıl” kuralının doğruluğu (1,0 = kusursuz), "
        "en iyi eşikte. (Uygulama buna ek olarak zincirlenmeyi önleyen ikinci bir koşul kullanır; bkz. "
        "`docs/BIRLESTIRME_KARSILASTIRMA.md`.)",
        "- **Zor çiftler**: birbirine benzeyen ama farklı olayların en yüksek benzerliği; eşiğin altında kalmalı.",
        "",
        "| Model | Metin | AUC | Kümeleme F1 (eşik) | Zor çiftler (en yüksek) | Hız (haber/sn, CPU) |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        for variant, v in r["variants"].items():
            hard = max(v["hard_negative_max"].values())
            lines.append(
                f"| {r['model']} | {variant} | {v['auc']} | {v['best_cluster_f1']} ({v['best_cluster_t']}) | {hard} | {v['per_second']} |"
            )
    lines += ["", "## Eşiğe göre kümeleme F1", ""]
    for r in results:
        for variant, v in r["variants"].items():
            curve = ", ".join(f"{t}: {f}" for t, f in v["cluster_f1_curve"].items())
            lines.append(f"- **{r['model']} / {variant}**: {curve}")
    lines += ["", "## Zor çiftler ayrıntısı", ""]
    for r in results:
        for variant, v in r["variants"].items():
            lines.append(f"- **{r['model']} / {variant}**: " + ", ".join(f"{k} = {x}" for k, x in v["hard_negative_max"].items()))
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    models = sys.argv[1:] or MODELS
    articles = load_articles()
    print(f"{len(articles)} gold articles")
    client = OllamaClient()
    results = []
    for model in models:
        results.append(await evaluate(client, model, articles))
        await client.unload(model)
    (ROOT / ".devdata" / "benchmark" / "embed_results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    write_report(articles, results)


if __name__ == "__main__":
    asyncio.run(main())
