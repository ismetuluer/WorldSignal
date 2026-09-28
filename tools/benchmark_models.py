"""Compare Ollama models on real articles from the user's database.

Usage (from the project folder, Ollama running; delete .devdata/benchmark/sample.json to draw a new sample):
    .venv\\Scripts\\python tools\\benchmark_models.py [model ...]

Picks a fixed, multilingual sample of recent articles (read-only access to the
live database), runs the enrichment task on every model one after another
(each model is unloaded afterwards so they do not compete for VRAM) and writes:

    .devdata/benchmark/results.json      raw results (not committed)
    docs/MODEL_KARSILASTIRMA.md          side-by-side report for the user
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import sqlite3
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from worldsignal.ai.enrich import EnrichInput, EnrichTask, validate  # noqa: E402
from worldsignal.ai.ollama import OllamaClient, OllamaError  # noqa: E402
from worldsignal.country import profile  # noqa: E402

HOME = profile({"home.country": "TR"})  # the report rates relevance to Türkiye, as the benchmark did
TASK = EnrichTask(("tr", "en"), HOME.topics)  # Turkish and English, the benchmark's languages

DEFAULT_MODELS = [
    "qwen3:14b",
    "gemma4:12b",
    "gemma4:latest",
    "qwen3.5:9b",
    "gemma4-26b-a4b:latest",
    "Qwen3.8-27b:latest",
]
# language -> how many articles
SAMPLE_PLAN = {"en": 4, "tr": 2, "ar": 1, "ru": 1, "de": 1, "fr": 1, "az": 1, "es": 1}
OUT_DIR = ROOT / ".devdata" / "benchmark"
REPORT = ROOT / "docs" / "MODEL_KARSILASTIRMA.md"


def pick_sample(db_path: Path) -> list[dict]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rng = random.Random(20260927)
    sample: list[dict] = []
    used_sources: set[int] = set()
    for lang, count in SAMPLE_PLAN.items():
        rows = conn.execute(
            """SELECT a.id, a.title, a.summary, a.url, s.name AS source, s.id AS sid,
                      COALESCE(a.language, s.language) AS lang
               FROM articles a JOIN sources s ON s.id = a.source_id
               WHERE COALESCE(a.language, s.language) = ? AND length(a.summary) BETWEEN 60 AND 1500
                 AND a.summary != a.title
               ORDER BY a.sort_at DESC LIMIT 300""",
            (lang,),
        ).fetchall()
        rows = list(rows)
        rng.shuffle(rows)
        # Make sure at least one English item mentions Türkiye, to test relevance detection.
        if lang == "en":
            turkish = [r for r in rows if any(k in (r["title"] + r["summary"]) for k in ("Turk", "Erdogan", "Ankara", "Istanbul"))]
            rows = turkish[:1] + [r for r in rows if r not in turkish[:1]]
        taken = 0
        for r in rows:
            if taken == count:
                break
            if r["sid"] in used_sources and len(rows) > count * 3:
                continue
            used_sources.add(r["sid"])
            sample.append(dict(r))
            taken += 1
    conn.close()
    return sample


async def wait_for_idle_gpu(client: OllamaClient, model: str) -> None:
    """Fair timings need an idle GPU; never interrupt other programs' models, just wait for them."""
    while True:
        others = [m["name"] for m in await client.loaded_models() if m["name"] != model]
        if not others:
            return
        print(f"  waiting: GPU in use by {', '.join(others)}", flush=True)
        await asyncio.sleep(30)


async def run_model(client: OllamaClient, model: str, sample: list[dict]) -> dict:
    print(f"\n=== {model}")
    result: dict = {"model": model, "items": [], "error": None}
    await wait_for_idle_gpu(client, model)
    try:
        t0 = time.perf_counter()
        warm = await client.chat_json(model, "Reply with JSON.", 'Return {"ok": true}.',
                                      {"type": "object", "properties": {"ok": {"type": "boolean"}}, "required": ["ok"]})
        result["load_s"] = round(time.perf_counter() - t0, 1)
        result["warm_load_ms"] = warm.load_ms
        ps = await client.loaded_models()
        info = next((m for m in ps if m["name"] == model), None)
        if info:
            result["size_gb"] = round(info["size"] / 1e9, 1)
            result["vram_gb"] = round(info.get("size_vram", 0) / 1e9, 1)
        for art in sample:
            inp = EnrichInput(art["source"], art["lang"], art["title"], art["summary"])
            item = {"article_id": art["id"]}
            try:
                r = await client.chat_json(model, TASK.system_prompt, inp.render(), TASK.schema)
                v = validate(r.data, inp, TASK)
                item.update(
                    ok=True, seconds=round(r.total_ms / 1000, 2), tps=round(r.tokens_per_second, 1),
                    out_tokens=r.output_tokens, **v.__dict__, title_tr=v.texts["tr"]["title"],
                    summary_tr=v.texts["tr"]["summary"],
                )
            except (OllamaError, ValueError) as exc:
                item.update(ok=False, error=str(exc)[:300])
            result["items"].append(item)
            print(f"  {art['lang']} {item.get('seconds', '-')}s ok={item['ok']} {item.get('title_tr', item.get('error', ''))[:90]}")
    except OllamaError as exc:
        result["error"] = str(exc)
        print("  FAILED:", exc)
    finally:
        try:
            await client.unload(model)
        except OllamaError:
            pass
    return result


def summarize(res: dict) -> dict:
    ok = [i for i in res["items"] if i.get("ok")]
    secs = [i["seconds"] for i in ok]
    return {
        "ok": len(ok),
        "n": len(res["items"]),
        "median_s": round(statistics.median(secs), 1) if secs else None,
        "max_s": round(max(secs), 1) if secs else None,
        "tps": round(statistics.median([i["tps"] for i in ok]), 1) if ok else None,
        "issues": sum(len(i["issues"]) for i in ok),
        "per_day_hours_3000": round(statistics.mean(secs) * 3000 / 3600, 1) if secs else None,
    }


def write_report(sample: list[dict], results: list[dict]) -> None:
    lines = [
        "# Model karşılaştırması (Faz 2)",
        "",
        "Bu dosya `tools/benchmark_models.py` ile üretilir. Görev: tek bir haberden Türkçe başlık, Türkçe özet, kategori ve "
        "Türkiye bağlantısı üretmek. Girdi yalnızca RSS başlığı + özetidir (tam metin Faz 5'te gelecek).",
        "",
        "## Özet tablo",
        "",
        "| Model | Başarılı | Ortalama süre (medyan) | En uzun | Hız (token/sn) | GPU'ya sığan | Uydurma uyarısı | 3.000 haber/gün için GPU süresi |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['model']} | hata: {r['error'][:60]} | | | | | | |")
            continue
        s = summarize(r)
        vram = f"{r.get('vram_gb', '?')} / {r.get('size_gb', '?')} GB"
        lines.append(
            f"| {r['model']} | {s['ok']}/{s['n']} | {s['median_s']} sn | {s['max_s']} sn | {s['tps']} | {vram} | "
            f"{s['issues']} | {s['per_day_hours_3000']} saat |"
        )
    lines += ["", "## Haber haber çıktılar", ""]
    for idx, art in enumerate(sample, 1):
        summary = art["summary"] if len(art["summary"]) <= 600 else art["summary"][:600] + "…"
        lines += [
            f"### {idx}. [{art['lang']}] {art['source']}",
            "",
            f"**Orijinal başlık:** {art['title']}",
            "",
            f"**Orijinal özet:** {summary}",
            "",
            "| Model | Türkçe başlık | Türkçe özet | Kategori | Türkiye | Uyarı |",
            "|---|---|---|---|---|---|",
        ]
        for r in results:
            item = next((i for i in r["items"] if i["article_id"] == art["id"]), None)
            if item is None:
                continue
            if not item.get("ok"):
                lines.append(f"| {r['model']} | ❌ {item.get('error', '')[:80]} | | | | |")
                continue
            cell = lambda s: s.replace("|", "／").replace("\n", " ")  # noqa: E731
            level, links = HOME.relevance(f"{art['title']}\n{art.get('summary', '')}", item["countries"],
                                          item["topics"], item["mentions_turkey"])
            tr = level + (f" ({', '.join(links)})" if links else "")
            if item["countries"]:
                tr += f" · ülkeler: {', '.join(item['countries'])}"
            lines.append(
                f"| {r['model']} | {cell(item['title_tr'])} | {cell(item['summary_tr'])} | {item['category']} | {cell(tr)} | "
                f"{', '.join(item['issues']) or '—'} |"
            )
        lines.append("")
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> None:
    models = sys.argv[1:] or DEFAULT_MODELS
    db_path = Path(os.environ.get("LOCALAPPDATA", "")) / "WorldSignal" / "worldsignal.db"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # The sample is frozen on first use so that every run compares the same articles.
    sample_file = OUT_DIR / "sample.json"
    if sample_file.exists():
        sample = json.loads(sample_file.read_text(encoding="utf-8"))
    else:
        sample = pick_sample(db_path)
        sample_file.write_text(json.dumps(sample, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Sample: {len(sample)} articles: " + ", ".join(a["lang"] for a in sample))
    client = OllamaClient()
    results = []
    for model in models:
        results.append(await run_model(client, model, sample))
        (OUT_DIR / "results.json").write_text(
            json.dumps({"sample": sample, "results": results}, ensure_ascii=False, indent=1), encoding="utf-8"
        )
    write_report(sample, results)
    print("\nSummary:")
    for r in results:
        print(r["model"], r.get("error") or summarize(r), r.get("vram_gb"), r.get("size_gb"), r.get("load_s"))


if __name__ == "__main__":
    asyncio.run(main())
