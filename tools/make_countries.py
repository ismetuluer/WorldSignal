"""Build the country data used for "my country" relevance: names from Wikidata (CC0), land neighbours from
GeoNames (CC BY 4.0, https://www.geonames.org — credited in README and in the data file).

    .venv\\Scripts\\python tools\\make_countries.py

Output: src/worldsignal/catalog/countries.json
    {"countries": {"TR": {"label": {"tr": "Türkiye", "en": "Turkey", ...}, "neighbours": ["GR", ...]}, ...}}

The names (in the languages of LANGUAGES) fill the country list in the settings and count as "the country is
named in the text"; the neighbours are the "neighbour" rule of country.py.
"""

from __future__ import annotations

import json
import re
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "src" / "worldsignal" / "catalog" / "countries.json"
LANGUAGES = ["en", "tr", "de", "fr", "es", "it", "pt", "ru", "uk", "ar", "fa", "he", "el", "zh", "ja", "az", "nl", "pl"]
API = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
# Land borders only: Wikidata's "shares border with" also lists sea borders (Türkiye–Ukraine, USA–Japan), which would
# make every Ukraine story "related to Türkiye".
GEONAMES = "https://download.geonames.org/export/dump/countryInfo.txt"
HEADERS = {"User-Agent": "WorldSignal-build/1.0 (country data for a news reader; https://github.com/ismetuluer/WorldSignal)"}

# Every place with an ISO 3166-1 alpha-2 code that still exists (countries and dependent territories).
# Several items can carry the same code (e.g. a country and a historical state); the best known one wins.
QUERY = """SELECT ?c ?iso ?links WHERE { ?c wdt:P297 ?iso ; wikibase:sitelinks ?links .
             FILTER NOT EXISTS { ?c wdt:P576 ?end } }"""


def entities(client: httpx.Client, ids: list[str]) -> dict:
    """Fetch the items' names in batches. Large answers can come back with items silently left out, so what is
    missing is asked again in smaller batches; an item that never arrives stops the build."""
    found: dict = {}
    for size in (50, 10, 1):
        todo = [i for i in ids if i not in found]
        for i in range(0, len(todo), size):
            r = client.get(API, params={"action": "wbgetentities", "ids": "|".join(todo[i:i + size]), "props": "labels",
                                        "languages": "|".join(LANGUAGES), "format": "json"})
            r.raise_for_status()
            found.update({k: v for k, v in r.json().get("entities", {}).items() if "missing" not in v})
            time.sleep(0.3)  # be gentle with Wikidata
    lost = [i for i in ids if i not in found]
    if lost:
        raise SystemExit(f"Wikidata did not return {lost}")
    return found


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # names in every script
    with httpx.Client(headers=HEADERS, timeout=60, follow_redirects=True) as client:
        r = client.get(SPARQL, params={"query": QUERY, "format": "json"})
        r.raise_for_status()
        best: dict[str, tuple[int, str]] = {}
        for b in r.json()["results"]["bindings"]:
            qid = b["c"]["value"].rsplit("/", 1)[1]
            iso = b["iso"]["value"].upper()
            links = int(b["links"]["value"])
            if re.fullmatch(r"[A-Z]{2}", iso) and links > best.get(iso, (-1, ""))[0]:
                best[iso] = (links, qid)
        iso_of = {qid: iso for iso, (_, qid) in best.items()}
        print(f"{len(iso_of)} places with an ISO code", flush=True)
        places = entities(client, list(iso_of))
        land = {}
        for line in client.get(GEONAMES).raise_for_status().text.splitlines():
            cols = line.split("\t")
            if line.startswith("#") or len(cols) < 18:
                continue
            land[cols[0]] = [n for n in cols[17].split(",") if n]

    countries = {}
    for qid, e in places.items():
        iso = iso_of[qid]
        names = e.get("labels", {})
        if "en" not in names:
            print(f"without an English name (skipped): {iso}")
            continue
        countries[iso] = {
            "label": {lang: names[lang]["value"] for lang in LANGUAGES if lang in names},
            "neighbours": sorted(set(land.get(iso, [])) & set(iso_of.values()) - {iso}),
        }
    OUTPUT.write_text(json.dumps({
        "source": "Names: Wikidata (CC0). Land neighbours: GeoNames (CC BY 4.0, https://www.geonames.org).",
        "built": datetime.now(UTC).strftime("%Y-%m-%d"), "languages": LANGUAGES,
        "countries": dict(sorted(countries.items())),
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(countries)} countries -> {OUTPUT} ({OUTPUT.stat().st_size / 1000:.0f} kB)")
    for iso in ("TR", "ZA", "US", "DE"):
        c = countries.get(iso)
        if c:
            print(iso, c["label"].get("en"), "| neighbours:", c["neighbours"])


if __name__ == "__main__":
    sys.exit(main())
