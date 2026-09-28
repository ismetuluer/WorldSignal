"""Verify every candidate feed and write the bundled source catalog.

Usage (from the project folder):
    .venv\\Scripts\\python tools\\verify_catalog.py

A feed is *verified* when it downloads, parses as RSS/Atom, contains at least
3 items and its newest dated item is at most 7 days old. Failing feeds are
kept only when their whole source has no working feed; such sources are
written with ``verified: false`` so the app can list them separately as
"not verified" instead of pretending they work.

Outputs:
    src/worldsignal/catalog/sources.json   (bundled with the app)
    docs/KAYNAK_DOGRULAMA.md                (human-readable report)
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from worldsignal.collector.rss import FetchError, fetch_feed, make_client  # noqa: E402

CANDIDATES = ROOT / "tools" / "catalog_candidates.json"
OUTPUT = ROOT / "src" / "worldsignal" / "catalog" / "sources.json"
REPORT = ROOT / "docs" / "KAYNAK_DOGRULAMA.md"
MIN_ITEMS = 3
MAX_AGE_HOURS = 7 * 24

GROUP_TITLES = {
    "western": "Batı gazeteleri ve yayıncıları",
    "agency": "Ajanslar",
    "middle_east": "Orta Doğu",
    "russia_ukraine": "Rusya / Ukrayna",
    "asia": "Asya",
    "europe": "Avrupa",
    "other": "Afrika / Latin Amerika",
    "turkey": "Türk kaynakları",
    "sports": "Spor",
}


async def check_feed(client, url: str, host_locks: dict[str, asyncio.Lock], sem: asyncio.Semaphore) -> dict:
    host = urlsplit(url).netloc
    async with sem, host_locks[host]:
        now = datetime.now(UTC)
        try:
            result = await fetch_feed(client, url)
        except FetchError as exc:
            return {"ok": False, "error": exc.code, "detail": exc.detail[:200]}
        feed = result.feed
        assert feed is not None
        dates = [e.published_at for e in feed.entries if e.published_at]
        newest_age_h = round((now - max(dates)).total_seconds() / 3600, 1) if dates else None
        info = {
            "items": len(feed.entries),
            "dated_items": len(dates),
            "newest_age_h": newest_age_h,
            "feed_language": feed.language,
            "final_url": result.final_url,
        }
        if len(feed.entries) < MIN_ITEMS:
            return {"ok": False, "error": "too_few_items", **info}
        if newest_age_h is not None and newest_age_h > MAX_AGE_HOURS:
            return {"ok": False, "error": "stale", **info}
        return {"ok": True, **info}


async def main() -> None:
    data = json.loads(CANDIDATES.read_text(encoding="utf-8"))
    sources = data["sources"]
    host_locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
    sem = asyncio.Semaphore(8)
    async with make_client() as client:
        tasks = {}
        for s in sources:
            for f in s["feeds"]:
                tasks[f["url"]] = asyncio.create_task(check_feed(client, f["url"], host_locks, sem))
        await asyncio.gather(*tasks.values())
        results = {url: t.result() for url, t in tasks.items()}

    checked_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    out_sources = []
    for s in sources:
        feeds_out = []
        for f in s["feeds"]:
            r = results[f["url"]]
            feeds_out.append({**f, "verified": r["ok"], "check": r})
        working = [f for f in feeds_out if f["verified"]]
        entry = {k: v for k, v in s.items() if k != "feeds"}
        entry["verified"] = bool(working)
        entry["feeds"] = working or feeds_out
        out_sources.append(entry)

    OUTPUT.write_text(
        json.dumps({"version": 1, "checked_at": checked_at, "sources": out_sources,
                    "retired_feeds": data.get("retired_feeds", [])}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    write_report(out_sources, sources, results, checked_at)

    ok_sources = sum(1 for s in out_sources if s["verified"])
    ok_feeds = sum(1 for r in results.values() if r["ok"])
    print(f"Sources verified: {ok_sources}/{len(out_sources)}   feeds OK: {ok_feeds}/{len(results)}")
    for s in sources:
        for f in s["feeds"]:
            r = results[f["url"]]
            mark = "OK  " if r["ok"] else "FAIL"
            extra = f"items={r.get('items')} newest={r.get('newest_age_h')}h" if "items" in r else ""
            print(f"{mark} {s['slug']:<18} {r.get('error', ''):<14} {extra}  {f['url']}")


def write_report(out_sources, candidates, results, checked_at) -> None:
    lines = [
        "# Kaynak doğrulama raporu",
        "",
        f"Son kontrol: {checked_at} (UTC). Bu dosya `tools/verify_catalog.py` tarafından üretilir; elle düzenlemeyin.",
        "",
        f"Doğrulama ölçütü: adres indirilebilmeli, RSS/Atom olarak çözümlenebilmeli, en az {MIN_ITEMS} haber içermeli "
        "ve en yeni haber en fazla 7 gün önce yayımlanmış olmalı.",
        "",
    ]
    by_group = defaultdict(list)
    for s, cand in zip(out_sources, candidates, strict=True):
        by_group[s["group"]].append((s, cand))
    for group, title in GROUP_TITLES.items():
        items = by_group.get(group, [])
        if not items:
            continue
        lines += [f"## {title}", "", "| Kaynak | Durum | Akış | Haber | En yeni |", "|---|---|---|---|---|"]
        for s, cand in items:
            for f in cand["feeds"]:
                r = results[f["url"]]
                status = "✅ doğrulandı" if r["ok"] else f"❌ {r.get('error')}"
                age = f"{r['newest_age_h']} sa" if r.get("newest_age_h") is not None else "-"
                lines.append(f"| {s['name']} | {status} | `{f['url']}` | {r.get('items', '-')} | {age} |")
        lines.append("")
    unverified = [s for s in out_sources if not s["verified"]]
    lines += ["## Doğrulanamayan kaynaklar", ""]
    if unverified:
        lines += [f"- **{s['name']}**: hiçbir akış çalışmadı; uygulamada \"doğrulanmadı\" olarak kapalı gelir." for s in unverified]
    else:
        lines.append("Yok.")
    notes = [s for s in out_sources if s.get("note")]
    if notes:
        lines += ["", "## Notlar", ""] + [f"- **{s['name']}**: {s['note']}" for s in notes]
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(main())
