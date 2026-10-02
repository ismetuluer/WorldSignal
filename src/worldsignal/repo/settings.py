"""User settings stored as JSON values in the ``settings`` table."""

from __future__ import annotations

import json
from typing import Any

from ..db import Database, utc_now_iso

DEFAULTS: dict[str, Any] = {
    "ui.language": "tr",
    "ui.theme": "system",  # system | light | dark
    "ui.shortcuts": {},  # action -> keys the user chose; {} = the defaults (frontend/src/lib/shortcuts.ts)
    "ui.font": "",  # CSS font-family list; "" = the program's own
    "ui.font_scale": 100,  # percent
    "ui.text_color_light": "",  # "#rrggbb"; "" = the theme's own
    "ui.text_color_dark": "",
    "feed.window_hours": 24,
    "feed.view": "stories",
    # Program updates from GitHub releases (updater.py).
    "update.auto_check": True,
    "update.auto_download": True,
    # The feed's filters as the user last left them (remembered between sessions).
    "feed.filters": {"regions": [], "groups": [], "langs": [], "sources": [], "categories": [], "turkey": False},
    # "My country" (country.py): "" = Windows' region. related/topics None = the country's defaults
    # (for Türkiye: the Turkic states and the six topics; elsewhere none). keywords: extra words that name it.
    # Off: the country link is left out of the score and the feed hides its filter and badges. The AI still
    # extracts the countries, so switching it back on needs no new work.
    "home.enabled": True,
    # Rate the reports for "my country" and show the labels. Off: the ratings are not made again when the country
    # changes (the AI work is unaffected: that is what "home.enabled" is for).
    "home.labels": True,
    "home.country": "",
    "home.related": None,
    "home.topics": None,
    "home.keywords": [],
    "ai.enabled": True,
    # Where the AI runs: "ollama" (this or another computer) or a cloud service the user chose, with its model.
    # API keys are not settings: apikeys.py keeps them encrypted outside the database.
    "ai.provider": "ollama",
    "ai.gemini_model": "",
    "ai.openai_model": "",
    "ai.openai_url": "https://api.openai.com/v1",
    "ai.anthropic_model": "",
    "ai.cloud_rpm": 10,  # requests per minute to a cloud service (free plans allow few)
    # Languages the AI writes titles, summaries and translations in (ai/languages.py). None = the interface
    # language and English.
    "ai.languages": None,
    "ai.url": "http://localhost:11434",
    "ai.model": "gemma4-26b-a4b:latest",  # chosen by the project owner on 2026-09-27 after tools/benchmark_models.py
    "ai.max_age_hours": 24,  # newer articles are queued automatically; older ones on request
    "ai.yield_gpu": True,  # wait while another model is loaded in Ollama instead of evicting it
    # How much the AI writes (ai/worker.py): "full" every report on its own; "stories" the reports of a summarised
    # story are not read one by one; "fast" also single reports ten at a time, headline only (summary on request).
    "ai.depth": "fast",
    # Stories (phase 3). Embedding model and threshold come from tools/benchmark_embeddings.py.
    "stories.embed_model": "bge-m3:latest",
    # Measured in docs/GOMME_KARSILASTIRMA.md: titles alone separate distinct events better.
    "stories.embed_summary": False,
    "stories.threshold": 0.55,
    "ai.inputs": {},  # the user's layout of a report in the request (ai/prompts.py); {} = the default
    "ai.limits": {},  # the user's amounts sent (characters, reports per request); {} = the defaults
    "ai.prompts": {},  # the user's own wording of the AI instructions, per task (ai/prompts.py); {} = the defaults
    "stories.cohesion": 0.55,  # docs/BIRLESTIRME_KARSILASTIRMA.md: stops chaining (0.5 let stories drift, 0.55 halves the giants)
    "stories.min_sources_for_ai": 2,
    "score.w_sources": 0.45,
    "score.w_freshness": 0.25,
    "score.w_turkey": 0.20,
    "score.w_interest": 0.10,
    "interest.keywords": [],
    "interest.categories": [],
    "interest.regions": [],
    # Full text (phase 5). Browser mode uses patchright with a Chromium browser on this computer.
    "fulltext.enabled": True,
    # Also translate every full text that arrives into the user's languages (a lot of AI work). Off: the summary
    # only; a full text is translated when the user asks in the reader.
    "fulltext.translate": False,
    "fulltext.browser_path": "",  # empty: the first of Brave, Chrome, Edge that is installed
    "fulltext.profile": "own",  # own: World Signal's profile | main: the browser's everyday profile
    "fulltext.visible": False,  # show the browser window while it reads pages
    "fulltext.reader": "automation",  # automation: World Signal's own browser | extension: the user's browser (0.14)
    "fulltext.launch_browser": True,  # extension mode: start the user's browser (no window) when it is closed
    "fulltext.per_site_hour": 4,  # human pace: pages per site per hour
    # Subscription sites (read in the browser) at a person's pace (repo.fulltext.BrowserPace):
    "fulltext.browser_gap_min": 20,  # at least this many minutes between two pages of one site
    "fulltext.browser_per_day": 15,  # pages per site per day
    "fulltext.browser_night_rest": True,  # no automatic pages at night (NIGHT_HOURS, local time)
    "fulltext.auto_min_score": 60,  # stories at least this important get full texts automatically
    "fulltext.auto_per_story": 2,  # at most this many reports per story
    # History and retention (phase 6).
    "history.morning_hour": 9,  # the "morning" view of a past day shows the feed as it was at this hour
    "retention.fulltext_days": 30,  # full texts (and translations) are removed after this; 0 keeps them
    # Background and delivery (phase 7).
    "backup.keep_daily": 14,  # daily database copies kept
    "app.close_to_tray": True,  # closing the window keeps World Signal collecting in the system tray
    "notify.enabled": True,
    "notify.min_score": 60,  # only important stories ...
    "notify.min_sources": 5,  # ... reported by this many independent sources within three hours
    # Working hours (worktime.py): off = the background work runs all day and night.
    "work.limited": False,
    "work.start": 7,
    "work.end": 23,
    "notify.quiet": True,
    "notify.quiet_start": 23,  # quiet hours, local time
    "notify.quiet_end": 7,
}

# Internal bookkeeping keys that are not user preferences.
CATALOG_REMOVED = "catalog.removed_slugs"


class SettingsRepository:
    def __init__(self, db: Database) -> None:
        self.db = db

    def get(self, key: str, default: Any = None) -> Any:
        row = self.db.conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is None:
            return DEFAULTS.get(key, default)
        return json.loads(row["value"])

    def get_preferences(self) -> dict[str, Any]:
        values = dict(DEFAULTS)
        rows = self.db.conn.execute(
            "SELECT key, value FROM settings WHERE key IN (%s)" % ",".join("?" * len(DEFAULTS)),
            tuple(DEFAULTS),
        ).fetchall()
        for row in rows:
            values[row["key"]] = json.loads(row["value"])
        return values

    def set(self, key: str, value: Any) -> None:
        with self.db.transaction() as c:
            c.execute(
                "INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
                (key, json.dumps(value, ensure_ascii=False), utc_now_iso()),
            )

    def set_many(self, values: dict[str, Any]) -> None:
        with self.db.transaction():
            for key, value in values.items():
                self.set(key, value)
