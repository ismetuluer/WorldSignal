"""Local HTTP API and static UI server (bound to 127.0.0.1 only).

Every ``/api`` route except ``/api/health`` requires the per-session token in
the ``X-WorldSignal-Token`` header. The token is generated at start-up and
handed to the window in the URL fragment, so web pages open in other browsers
cannot talk to this server even though it listens on localhost.

Errors are returned as ``{"detail": {"code": "...", "message": "..."}}``; the
UI translates the code.
"""

from __future__ import annotations

import asyncio
import contextlib
import hmac
import logging
import os
import re
import subprocess
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl, field_validator

from .. import __version__
from ..ai.enrich import CATEGORIES
from ..ai.ollama import OllamaClient, OllamaError
from ..ai import prompts as ai_prompts
from ..ai.worker import AiWorker
from ..collector.rss import FetchError, download, fetch_feed, make_client
from ..collector.sitemap import discover
from ..collector.service import Collector
from ..db import Database, utc_now_iso
from ..paths import DataPaths, extension_dir
from ..repo.ai import AiRepository
from ..repo.articles import ArticleFilter, ArticleRepository
from ..fulltext.bridge import ExtensionBridge
from ..fulltext.fetch import browser_for, find_browsers, open_login_window, profile_in_use
from ..fulltext.worker import FullTextWorker
from ..repo.fulltext import FullTextRepository
from ..repo.history import HistoryRepository, day_view, local_datetime, next_day
from ..backup import BackupManager, InvalidBackup
from ..maintenance import Maintenance
from ..notify import Notifier
from ..repo.notebook import MAX_COMMENT, MAX_NOTE, NotebookRepository, valid_day
from ..repo.settings import DEFAULTS, SettingsRepository
from ..repo.sources import ABROAD, CATALOG_GROUPS, HOME_REGION, REGIONS, Conflict, NotFound, SourceRepository
from ..repo.stats import PERIODS, StatsRepository, period as stats_period
from ..repo.stories import StoryFilter, StoryRepository
from ..stories.embedding import recommended_settings
from ..stories.worker import WINDOW_HOURS as STORY_WINDOW_HOURS
from ..stories.worker import StoryWorker, interest_from, weights_from
from ..textnorm import MAX_ALTERNATIVES
from ..updater import UpdateError, Updater
from ..apikeys import SecretStore
from ..ai.cloud import OPENAI_URL, make_client as make_cloud_client
from ..flags import KINDS
from ..country import MAX_TOPIC, MAX_TOPICS, MIN_TOPIC, TOPICS, HomeState, countries as country_data
from ..country import profile as country_profile
from ..ai.languages import MAX_LANGUAGES, OUTPUT_LANGUAGES, effective as ai_languages
from ..home_sync import HomeSync
from .extension import extension_routers
from .. import mailer

log = logging.getLogger(__name__)

TOKEN_HEADER = "X-WorldSignal-Token"
SUPPORTED_LANGUAGES = ("tr", "en")


@dataclass
class AppContext:
    db: Database
    paths: DataPaths
    token: str
    settings: SettingsRepository
    sources: SourceRepository
    articles: ArticleRepository
    collector: Collector
    ai: AiRepository
    ai_worker: AiWorker
    stories: StoryRepository
    story_worker: StoryWorker
    notebook: NotebookRepository
    fulltext: FullTextRepository
    fulltext_worker: FullTextWorker
    history: HistoryRepository
    maintenance: Maintenance
    backups: BackupManager
    notifier: Notifier
    ui_dir: Path | None = None
    run_collector: bool = True
    show_window: Callable[[], None] | None = None
    # Set by the desktop window: close and start again (used after scheduling a restore).
    restart: Callable[[], None] | None = None
    # Set by the desktop window: close without starting again (an update starts the new program).
    quit: Callable[[], None] | None = None
    updater: Updater | None = None
    home: HomeState | None = None
    home_sync: HomeSync | None = None
    keys: SecretStore | None = None  # API keys of cloud AI services, and the extension's pairing key
    bridge: ExtensionBridge | None = None  # the browser extension's side of the full-text queue
    arm_watchdog: Callable[[], None] | None = None  # set by the entry point: start the crash watcher (watchdog.py)
    port: int = 0  # the port the server listens on (set once it is bound); the extension looks for it
    extra: dict[str, Any] = field(default_factory=dict)


def search_alternatives(qx: list[str] | None) -> tuple[str, ...]:
    """The translations of a search (``qx``, from /search/translations): trimmed, empty and overlong ones left out."""
    return tuple(t for t in (x.strip() for x in qx or ()) if 0 < len(t) <= 200)


def api_error(status: int, code: str, message: str = "") -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


# -- request models -------------------------------------------------------------
SHORTCUT_ACTIONS = ("search", "next", "prev", "open", "meeting")
# A key as KeyboardEvent.key names it, lower-case: one character, or one of the named keys below. Escape closes dialogs
# and Tab moves the focus, so neither can be given away.
SHORTCUT_KEY = re.compile(r"^(\S|space|enter|arrow(up|down|left|right)|home|end|page(up|down)|f([1-9]|1[0-2]))$")
SHORTCUT_RESERVED = {"escape", "tab"}
Region = Literal[REGIONS]  # type: ignore[valid-type]
Group = Literal[CATALOG_GROUPS]  # type: ignore[valid-type]
FeedGroup = Literal[CATALOG_GROUPS + KINDS]  # type: ignore[valid-type]
FeedRegion = Literal[REGIONS + (ABROAD,)]  # type: ignore[valid-type]


class FeedFilters(BaseModel):
    model_config = {"extra": "forbid"}

    regions: list[FeedRegion] = Field(default_factory=list)
    groups: list[FeedGroup] = Field(default_factory=list)
    langs: list[Annotated[str, Field(min_length=2, max_length=3)]] = Field(default_factory=list, max_length=50)
    sources: list[int] = Field(default_factory=list, max_length=500)
    categories: list[Literal[CATEGORIES]] = Field(default_factory=list)  # type: ignore[valid-type]
    turkey: bool = False


class SettingsPatch(BaseModel):
    model_config = {"extra": "forbid"}

    ui_language: Literal[SUPPORTED_LANGUAGES] | None = Field(None, alias="ui.language")  # type: ignore[valid-type]
    ui_theme: Literal["system", "light", "dark"] | None = Field(None, alias="ui.theme")
    # Type: a font-family list as written in CSS ("Georgia, serif"); "" = the program's own. Only names, no CSS syntax.
    ui_font: str | None = Field(None, alias="ui.font", max_length=120, pattern=r"^[\w \-,.'\"]*$")
    # Keyboard shortcuts: action -> keys (event.key, lower-case). Missing action = its default (frontend/src/lib/shortcuts.ts).
    ui_shortcuts: dict[str, list[str]] | None = Field(None, alias="ui.shortcuts")

    @field_validator("ui_shortcuts")
    @classmethod
    def _shortcuts(cls, value: dict[str, list[str]] | None) -> dict[str, list[str]] | None:
        """Known actions, plausible single keys, at most four per action, and no key on two actions."""
        if value is None:
            return None
        taken: dict[str, str] = {}
        for action, keys in value.items():
            if action not in SHORTCUT_ACTIONS:
                raise ValueError(f"unknown_action:{action}")
            if not 1 <= len(keys) <= 4:
                raise ValueError(f"bad_count:{action}")
            for key in keys:
                if not SHORTCUT_KEY.fullmatch(key) or key in SHORTCUT_RESERVED:
                    raise ValueError(f"bad_key:{key}")
                if taken.setdefault(key, action) != action or keys.count(key) > 1:
                    raise ValueError(f"duplicate_key:{key}")
        return value

    ui_font_scale: int | None = Field(None, alias="ui.font_scale", ge=70, le=160)  # percent of the normal size
    # Colour of the text per theme, "#rrggbb"; "" = the theme's own.
    ui_text_color_light: str | None = Field(None, alias="ui.text_color_light", pattern=r"^(#[0-9a-fA-F]{6})?$")
    ui_text_color_dark: str | None = Field(None, alias="ui.text_color_dark", pattern=r"^(#[0-9a-fA-F]{6})?$")
    feed_window_hours: int | None = Field(None, alias="feed.window_hours", ge=1, le=168)
    feed_view: Literal["stories", "articles"] | None = Field(None, alias="feed.view")
    feed_filters: FeedFilters | None = Field(None, alias="feed.filters")
    update_auto_check: bool | None = Field(None, alias="update.auto_check")
    home_enabled: bool | None = Field(None, alias="home.enabled")
    home_labels: bool | None = Field(None, alias="home.labels")
    home_country: Annotated[str, Field(pattern=r"^([A-Z]{2})?$")] | None = Field(None, alias="home.country")
    home_related: list[Annotated[str, Field(pattern=r"^[A-Z]{2}$")]] | None = Field(None, alias="home.related", max_length=50)
    home_topics: list[Annotated[str, Field(min_length=MIN_TOPIC, max_length=MAX_TOPIC)]] | None = Field(
        None, alias="home.topics", max_length=MAX_TOPICS
    )
    ai_languages: list[Annotated[str, Field(pattern=r"^[a-z]{2}$")]] | None = Field(
        None, alias="ai.languages", min_length=1, max_length=MAX_LANGUAGES
    )
    home_keywords: list[Annotated[str, Field(min_length=2, max_length=60)]] | None = Field(
        None, alias="home.keywords", max_length=50
    )
    update_auto_download: bool | None = Field(None, alias="update.auto_download")
    ai_enabled: bool | None = Field(None, alias="ai.enabled")
    ai_url: HttpUrl | None = Field(None, alias="ai.url")
    ai_model: str | None = Field(None, alias="ai.model", max_length=200)
    ai_provider: Literal["ollama", "gemini", "openai", "anthropic"] | None = Field(None, alias="ai.provider")
    ai_gemini_model: str | None = Field(None, alias="ai.gemini_model", max_length=200)
    ai_openai_model: str | None = Field(None, alias="ai.openai_model", max_length=200)
    ai_anthropic_model: str | None = Field(None, alias="ai.anthropic_model", max_length=200)
    ai_openai_url: HttpUrl | None = Field(None, alias="ai.openai_url")
    ai_cloud_rpm: int | None = Field(None, alias="ai.cloud_rpm", ge=1, le=600)
    ai_max_age_hours: int | None = Field(None, alias="ai.max_age_hours", ge=1, le=168)
    ai_yield_gpu: bool | None = Field(None, alias="ai.yield_gpu")
    ai_depth: Literal["full", "stories", "fast"] | None = Field(None, alias="ai.depth")
    ai_prompts: dict[str, str] | None = Field(None, alias="ai.prompts")  # the instructions the user rewrote (ai/prompts.py)

    ai_inputs: dict[str, str] | None = Field(None, alias="ai.inputs")  # how a report is laid out in the request
    ai_limits: dict[str, int] | None = Field(None, alias="ai.limits")  # how much of it is sent (ai/prompts.py LIMITS)

    @field_validator("ai_inputs")
    @classmethod
    def _inputs(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        clean: dict[str, str] = {}
        for kind, text in value.items():
            if kind not in ai_prompts.INPUT_TASKS:
                raise ValueError(f"unknown_input:{kind}")
            if not text.strip():
                continue
            wrong = ai_prompts.input_problems(kind, text)
            if wrong:
                raise ValueError(wrong[0])
            clean[kind] = text
        return clean

    @field_validator("ai_limits")
    @classmethod
    def _limits(cls, value: dict[str, int] | None) -> dict[str, int] | None:
        if value is None:
            return None
        for name, amount in value.items():
            if name not in ai_prompts.LIMITS:
                raise ValueError(f"unknown_limit:{name}")
            _, low, high = ai_prompts.LIMITS[name]
            if isinstance(amount, bool) or not low <= amount <= high:
                raise ValueError(f"out_of_range:{name}")
        return value

    @field_validator("ai_prompts")
    @classmethod
    def _prompts(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        """Only known tasks, a blank text means "the default", and a text the model could not work with is refused."""
        if value is None:
            return None
        clean: dict[str, str] = {}
        for task, text in value.items():
            if task not in ai_prompts.TASKS:
                raise ValueError(f"unknown_task:{task}")
            if not text.strip():
                continue
            wrong = [p for p in ai_prompts.problems(task, text) if p != "no_fields"]  # {fields} is added when missing
            if wrong:
                raise ValueError(wrong[0])
            clean[task] = text
        return clean
    stories_embed_model: str | None = Field(None, alias="stories.embed_model", min_length=1, max_length=200)
    stories_embed_summary: bool | None = Field(None, alias="stories.embed_summary")
    stories_threshold: float | None = Field(None, alias="stories.threshold", ge=0.5, le=0.95)
    stories_cohesion: float | None = Field(None, alias="stories.cohesion", ge=0, le=0.9)
    fulltext_enabled: bool | None = Field(None, alias="fulltext.enabled")
    fulltext_translate: bool | None = Field(None, alias="fulltext.translate")
    fulltext_browser_path: str | None = Field(None, alias="fulltext.browser_path", max_length=400)
    extension_profile: Literal["daily", "own"] | None = Field(None, alias="extension.profile")
    debug_save_pages: bool | None = Field(None, alias="debug.save_pages")
    fulltext_launch_browser: bool | None = Field(None, alias="fulltext.launch_browser")
    fulltext_per_site_hour: int | None = Field(None, alias="fulltext.per_site_hour", ge=1, le=20)
    fulltext_browser_gap_min: int | None = Field(None, alias="fulltext.browser_gap_min", ge=5, le=240)
    fulltext_browser_per_day: int | None = Field(None, alias="fulltext.browser_per_day", ge=1, le=100)
    fulltext_browser_night_rest: bool | None = Field(None, alias="fulltext.browser_night_rest")
    fulltext_auto_min_score: float | None = Field(None, alias="fulltext.auto_min_score", ge=0, le=100)
    fulltext_auto_per_story: int | None = Field(None, alias="fulltext.auto_per_story", ge=0, le=5)
    history_morning_hour: int | None = Field(None, alias="history.morning_hour", ge=0, le=23)
    retention_fulltext_days: int | None = Field(None, alias="retention.fulltext_days", ge=0, le=3650)
    backup_keep_daily: int | None = Field(None, alias="backup.keep_daily", ge=1, le=90)
    app_close_to_tray: bool | None = Field(None, alias="app.close_to_tray")
    system_restart_on_crash: bool | None = Field(None, alias="system.restart_on_crash")
    notify_enabled: bool | None = Field(None, alias="notify.enabled")
    notify_min_score: float | None = Field(None, alias="notify.min_score", ge=0, le=100)
    notify_min_sources: int | None = Field(None, alias="notify.min_sources", ge=2, le=30)
    notify_breaking: bool | None = Field(None, alias="notify.breaking")
    notify_breaking_min_sources: int | None = Field(None, alias="notify.breaking_min_sources", ge=1, le=10)
    work_limited: bool | None = Field(None, alias="work.limited")
    work_start: int | None = Field(None, alias="work.start", ge=0, le=23)
    work_end: int | None = Field(None, alias="work.end", ge=0, le=23)
    notify_quiet: bool | None = Field(None, alias="notify.quiet")
    notify_quiet_start: int | None = Field(None, alias="notify.quiet_start", ge=0, le=23)
    notify_quiet_end: int | None = Field(None, alias="notify.quiet_end", ge=0, le=23)
    stories_min_sources_for_ai: int | None = Field(None, alias="stories.min_sources_for_ai", ge=1, le=10)
    score_w_sources: float | None = Field(None, alias="score.w_sources", ge=0, le=1)
    score_w_freshness: float | None = Field(None, alias="score.w_freshness", ge=0, le=1)
    score_w_turkey: float | None = Field(None, alias="score.w_turkey", ge=0, le=1)
    score_w_interest: float | None = Field(None, alias="score.w_interest", ge=0, le=1)
    interest_keywords: list[Annotated[str, Field(min_length=1, max_length=60)]] | None = Field(
        None, alias="interest.keywords", max_length=100
    )
    interest_categories: list[Literal[CATEGORIES]] | None = Field(None, alias="interest.categories")  # type: ignore[valid-type]
    interest_regions: list[Region] | None = Field(None, alias="interest.regions")


class RestoreRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class MergeRequest(BaseModel):
    into: int


class RegroupRequest(BaseModel):
    dry_run: bool = True


class LoginRequest(BaseModel):
    url: HttpUrl | None = None
    source_id: int | None = None  # open this subscription site's home page


class NoteBody(BaseModel):
    body: str = Field(max_length=MAX_NOTE)


class MailDraft(BaseModel):
    subject: str = Field(min_length=1, max_length=300)
    html: str = Field(max_length=2_000_000)
    text: str = Field(max_length=500_000)
    cut_note: str = Field(max_length=300)


class MeetingAdd(BaseModel):
    story_id: int | None = None
    article_id: int | None = None  # exactly one of the two


class MeetingPatch(BaseModel):
    comment: str = Field(max_length=MAX_COMMENT)


class MeetingOrder(BaseModel):
    day: str
    ids: list[int] = Field(max_length=500)


class ApiKeyBody(BaseModel):
    key: str = Field(min_length=8, max_length=400)


class CloudTestRequest(BaseModel):
    provider: Literal["gemini", "openai", "anthropic"]
    url: HttpUrl | None = None  # OpenAI-compatible services only


class OllamaTestRequest(BaseModel):
    url: HttpUrl


class FeedTestRequest(BaseModel):
    url: HttpUrl


class SourceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    feed_url: HttpUrl
    homepage: HttpUrl | None = None
    catalog_group: Group = "other"
    owner: str | None = Field(None, max_length=120)
    region: Region = "global"
    language: str = Field("en", pattern=r"^[a-z]{2}$")
    reliability: float = Field(1.0, ge=0, le=2)
    paywalled: bool = False

    @field_validator("name")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("empty")
        return v


class SourcePatch(BaseModel):
    model_config = {"extra": "forbid"}

    name: str | None = Field(None, min_length=1, max_length=120)
    homepage: HttpUrl | None = None
    catalog_group: Group | None = None
    owner: str | None = Field(None, max_length=120)
    region: Region | None = None
    language: str | None = Field(None, pattern=r"^[a-z]{2}$")
    reliability: float | None = Field(None, ge=0, le=2)
    enabled: bool | None = None
    paywalled: bool | None = None
    fulltext_mode: Literal["off", "http", "browser"] | None = None


class FeedCreate(BaseModel):
    url: HttpUrl
    label: str | None = Field(None, max_length=80)


class FeedPatch(BaseModel):
    model_config = {"extra": "forbid"}

    label: str | None = Field(None, max_length=80)
    enabled: bool | None = None
    fetch_interval_min: int | None = Field(None, ge=5, le=1440)


# -- app factory ----------------------------------------------------------------
def create_app(ctx: AppContext) -> FastAPI:
    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        tasks = []
        if ctx.bridge is not None:
            ctx.bridge.on_translation_queued = ctx.ai_worker.wake
        if ctx.run_collector:
            # New reports go into stories (and the AI queue) right away instead of at the next poll.
            ctx.collector.on_new_articles[:] = [ctx.story_worker.wake, ctx.ai_worker.wake]
            ctx.fulltext_worker.on_translation_queued = ctx.ai_worker.wake
            tasks.append(asyncio.create_task(ctx.collector.run_forever(), name="collector"))
            tasks.append(asyncio.create_task(ctx.ai_worker.run_forever(), name="ai-worker"))
            tasks.append(asyncio.create_task(ctx.story_worker.run_forever(), name="story-worker"))
            tasks.append(asyncio.create_task(ctx.fulltext_worker.run_forever(), name="fulltext-worker"))
            tasks.append(asyncio.create_task(ctx.maintenance.run_forever(), name="maintenance"))
            tasks.append(asyncio.create_task(ctx.notifier.run_forever(), name="notifier"))
            if ctx.bridge is not None:
                tasks.append(asyncio.create_task(ctx.bridge.watch_forever(), name="extension-watch"))
            if ctx.updater is not None:
                tasks.append(asyncio.create_task(ctx.updater.run_forever(), name="updater"))
            if ctx.home_sync is not None:
                tasks.append(asyncio.create_task(ctx.home_sync.run_forever(), name="home-sync"))
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            for task in tasks:
                with contextlib.suppress(asyncio.CancelledError):
                    await task

    app = FastAPI(title="World Signal", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)

    def require_token(x_worldsignal_token: Annotated[str | None, Header()] = None) -> None:
        if not x_worldsignal_token or not hmac.compare_digest(x_worldsignal_token, ctx.token):
            raise api_error(401, "unauthorized")

    public = APIRouter(prefix="/api")
    api = APIRouter(prefix="/api", dependencies=[Depends(require_token)])

    @public.get("/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__}

    # -- status / meta ---------------------------------------------------------
    @api.get("/status")
    def status() -> dict[str, Any]:
        since = utc_now_iso(datetime.now(UTC) - timedelta(hours=24))
        return {
            "version": __version__,
            "collector": ctx.collector.status(),
            "ai": ctx.ai_worker.status(),
            "stories": ctx.story_worker.status(),
            "fulltext": ctx.fulltext_worker.status(),
            "maintenance": ctx.maintenance.status(),
            "notify": ctx.notifier.status(),
            "articles": ctx.articles.counts(since),
            "breaking": ctx.stories.breaking_count(utc_now_iso(datetime.now(UTC) - timedelta(hours=3))),
            "extension": None if ctx.bridge is None else {
                **ctx.bridge.status(), "active": bool(ctx.settings.get_preferences()["fulltext.enabled"]),
            },
        }

    @api.get("/meta")
    def meta() -> dict[str, Any]:
        return {
            "regions": list(REGIONS),
            # "Abroad" (every source outside the local region) is offered only where a local region exists.
            "home_region": HOME_REGION if ctx.home is None or ctx.home.profile().code == "TR" else None,
            "groups": list(CATALOG_GROUPS),
            # Virtual groups of the feed's filter: exclusives and opinion pieces from any source (flags.py).
            "kinds": list(KINDS),
            "languages": ctx.articles.languages(),
            "categories": list(CATEGORIES),
            "ui_languages": list(SUPPORTED_LANGUAGES),
            "data_dir": str(ctx.paths.root),
            # The user's country: settings "home.country", or this when it is "" (Windows' region).
            "home_country": ctx.home.profile().code if ctx.home is not None else "TR",
            "ai_output_languages": list(OUTPUT_LANGUAGES),
            "ai_prompt_defaults": dict(ai_prompts.DEFAULTS),
            "ai_input_defaults": dict(ai_prompts.INPUT_DEFAULTS),
            "ai_limit_ranges": {k: list(v) for k, v in ai_prompts.LIMITS.items()},  # [default, lowest, highest]
            "system_country": country_profile({}, ctx.home.system_country).code if ctx.home is not None else "TR",
            "version": __version__,
        }

    # -- my country ------------------------------------------------------------------
    @api.get("/home")
    def home_country() -> dict[str, Any]:
        """The user's country as the rules see it now (settings may say "" = Windows' region)."""
        if ctx.home is None:
            raise api_error(409, "home_unavailable")
        p = ctx.home.profile()
        return {
            "code": p.code,
            "system_country": ctx.home.system_country,
            "neighbours": list(p.neighbours),
            "related": list(p.related),
            "topics": list(p.topics),
            "keywords": list(p.keywords),
            "countries": sorted(country_data()),
            "all_topics": list(TOPICS),
            "syncing": bool(ctx.home_sync and ctx.home_sync.status()["running"]),
        }

    # -- settings ----------------------------------------------------------------
    @api.get("/settings")
    def get_settings() -> dict[str, Any]:
        return ctx.settings.get_preferences()

    @api.patch("/settings")
    def patch_settings(patch: SettingsPatch) -> dict[str, Any]:
        values = patch.model_dump(by_alias=True, exclude_none=True)
        unknown = set(values) - set(DEFAULTS)
        if unknown:
            raise api_error(400, "unknown_setting", ", ".join(sorted(unknown)))
        if "ai.url" in values:
            values["ai.url"] = str(values["ai.url"]).rstrip("/")
        if "ai.openai_url" in values:
            values["ai.openai_url"] = str(values["ai.openai_url"]).rstrip("/")
        for key in ("ai.gemini_model", "ai.openai_model", "ai.anthropic_model"):
            if key in values:
                values[key] = str(values[key]).strip()
        if "ai.model" in values:
            values["ai.model"] = values["ai.model"].strip()
        if "stories.embed_model" in values:
            values["stories.embed_model"] = values["stories.embed_model"].strip()
            for key, value in recommended_settings(values["stories.embed_model"]).items():
                values.setdefault(key, value)  # a value sent in the same change wins
        if "interest.keywords" in values:
            values["interest.keywords"] = list(dict.fromkeys(k.strip() for k in values["interest.keywords"] if k.strip()))
        if "home.country" in values:
            unknown_codes = {c for c in [values["home.country"], *values.get("home.related", [])] if c} - set(country_data())
            if unknown_codes:
                raise api_error(422, "unknown_country", ", ".join(sorted(unknown_codes)))
            # A new country starts with its own defaults for related countries and topics.
            values.setdefault("home.related", None)
            values.setdefault("home.topics", None)
        if values.get("ai.languages") is not None:
            unknown_langs = [x for x in values["ai.languages"] if x not in OUTPUT_LANGUAGES]
            if unknown_langs:
                raise api_error(422, "unknown_language", ", ".join(unknown_langs))
            values["ai.languages"] = list(dict.fromkeys(values["ai.languages"]))
        if values.get("home.topics") is not None:
            values["home.topics"] = list(dict.fromkeys(t.strip() for t in values["home.topics"] if t.strip()))
        if "home.keywords" in values:
            values["home.keywords"] = list(dict.fromkeys(k.strip() for k in values["home.keywords"] if k.strip()))
        ctx.settings.set_many(values)
        if values.get("system.restart_on_crash") and ctx.arm_watchdog:
            ctx.arm_watchdog()
        if any(k.startswith("home.") for k in values) and ctx.home_sync is not None:
            ctx.home_sync.wake()
        if any(k.startswith("ai.") for k in values):
            ctx.ai_worker.wake()
        if any(k.split(".")[0] in ("stories", "score", "interest") or k in ("home.enabled", "home.labels") for k in values):
            ctx.story_worker.request_rescore()
        if any(k.startswith("fulltext.") for k in values):
            ctx.fulltext_worker.wake()
        if "retention.fulltext_days" in values:
            ctx.maintenance.wake()
        return ctx.settings.get_preferences()

    # -- articles ------------------------------------------------------------------
    @api.get("/articles")
    def list_articles(
        hours: Annotated[int | None, Query(ge=1, le=24 * 365)] = None,
        source: Annotated[list[int] | None, Query()] = None,
        region: Annotated[list[str] | None, Query()] = None,
        group: Annotated[list[str] | None, Query()] = None,
        lang: Annotated[list[str] | None, Query()] = None,
        category: Annotated[list[str] | None, Query()] = None,
        turkey: bool = False,
        q: Annotated[str | None, Query(max_length=200)] = None,
        qx: Annotated[list[str] | None, Query(max_length=MAX_ALTERNATIVES, description="translations of q")] = None,
        before: Annotated[str | None, Query(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\|\d+$")] = None,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
        day: Annotated[str | None, Query(description="one local calendar day (YYYY-MM-DD) instead of hours")] = None,
    ) -> dict[str, Any]:
        since = utc_now_iso(datetime.now(UTC) - timedelta(hours=hours)) if hours else None
        until = None
        if day is not None:
            start = local_datetime(check_day(day), 0)
            since, until = utc_now_iso(start), utc_now_iso(local_datetime(check_day(next_day(day)), 0))
        cursor = None
        if before:
            ts, _, ident = before.partition("|")
            cursor = (ts, int(ident))
        filt = ArticleFilter(
            since=since, until=until, source_ids=source or (), regions=region or (), groups=group or (),
            languages=lang or (), categories=category or (), turkey_only=turkey,
            query=(q or "").strip() or None, alternatives=search_alternatives(qx), before=cursor, limit=limit,
        )
        items = ctx.articles.list(filt)
        next_cursor = f"{items[-1]['sort_at']}|{items[-1]['id']}" if len(items) == limit else None
        # The total is only needed for the first page (shown in the header).
        total = ctx.articles.count(filt) if cursor is None else None
        return {"items": items, "next": next_cursor, "total": total}

    # -- statistics -------------------------------------------------------------------------------
    stats = StatsRepository(ctx.db, ctx.stories)

    def check_period(hours: int) -> int:
        if hours not in PERIODS:
            raise api_error(422, "bad_period")
        return hours

    @api.get("/stats")
    def get_stats(hours: int = 24) -> dict[str, Any]:
        """Reports, stories and sources of the period; shares by category and region; countries; rising stories."""
        return stats.overview(stats_period(check_period(hours), datetime.now().astimezone()))

    @api.get("/stats/topic")
    def get_topic_stats(
        q: Annotated[str, Query(min_length=1, max_length=200)],
        qx: Annotated[list[str] | None, Query(max_length=MAX_ALTERNATIVES)] = None,
        hours: int = 24,
    ) -> dict[str, Any]:
        """One topic (the search, with its translations ``qx``) per hour or day, and its share of all reports."""
        found = stats.topic(stats_period(check_period(hours), datetime.now().astimezone()), q.strip(),
                            search_alternatives(qx))
        return found if found is not None else {"articles": 0, "sources": 0, "previous": 0, "buckets": []}

    @api.get("/search/translations")
    async def search_translations(q: Annotated[str, Query(min_length=1, max_length=200)]) -> dict[str, Any]:
        """The search words in the languages the sources publish in (ai/query.py), for ``qx`` of the lists.

        ``state`` is ``ok``, or why there are no translations (``disabled``, ``no_model``, ``gpu_busy``,
        ``unreachable`` …); the search then runs on the typed words alone."""
        languages = await asyncio.to_thread(ctx.articles.source_languages)
        try:
            queries = await ctx.ai_worker.expand_query(q.strip(), languages)
        except OllamaError as exc:
            log.info("Search words not translated: %s", exc.code)
            return {"state": exc.code, "queries": {}}
        return {"state": "ok", "queries": queries}

    @api.post("/articles/{article_id}/ai")
    def request_ai(article_id: int) -> dict[str, Any]:
        """Ask for the AI title and summary of one article now (jumps the queue)."""
        try:
            status = ctx.ai.request(article_id, ai_languages(ctx.settings.get_preferences()))
        except KeyError:
            raise api_error(404, "not_found") from None
        ctx.ai_worker.wake()
        return {"status": status}

    # -- stories ------------------------------------------------------------------------------
    def rescore(story_ids: list[int]) -> None:
        prefs = ctx.settings.get_preferences()
        ctx.stories.recompute(story_ids, datetime.now(UTC), weights_from(prefs), interest_from(prefs))

    @api.get("/stories")
    def list_stories(
        hours: Annotated[int | None, Query(ge=1, le=24 * 365)] = None,
        source: Annotated[list[int] | None, Query()] = None,
        region: Annotated[list[str] | None, Query()] = None,
        group: Annotated[list[str] | None, Query()] = None,
        lang: Annotated[list[str] | None, Query()] = None,
        category: Annotated[list[str] | None, Query()] = None,
        turkey: bool = False,
        min_sources: Annotated[int, Query(ge=1, le=50)] = 1,
        breaking: bool = False,
        q: Annotated[str | None, Query(max_length=200)] = None,
        qx: Annotated[list[str] | None, Query(max_length=MAX_ALTERNATIVES, description="translations of q")] = None,
        sort: Literal["score", "recent"] = "score",
        limit: Annotated[int, Query(ge=1, le=200)] = 40,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        since = utc_now_iso(datetime.now(UTC) - timedelta(hours=hours)) if hours else None
        items, total = ctx.stories.list(StoryFilter(
            since=since, source_ids=source or (), regions=region or (), groups=group or (), languages=lang or (),
            categories=category or (), turkey_only=turkey, breaking=breaking, min_sources=min_sources, query=(q or "").strip() or None,
            alternatives=search_alternatives(qx), sort=sort, limit=limit, offset=offset,
        ))
        return {"items": items, "total": total}

    @api.post("/stories/regroup")
    def regroup_stories(body: RegroupRequest) -> dict[str, int]:
        """Hold the stories of the last days to the current threshold (stories formed under a lower one are split).
        With ``dry_run`` only says how many would change."""
        prefs = ctx.settings.get_preferences()
        model = (prefs.get("stories.embed_model") or "").strip()
        if not model:
            return {"changed": 0, "created": 0}
        since = utc_now_iso(datetime.now(UTC) - timedelta(hours=STORY_WINDOW_HOURS))
        touched, created = ctx.stories.split_loose(since, model, float(prefs["stories.threshold"]), dry_run=body.dry_run)
        if touched and not body.dry_run:
            rescore(sorted(touched))
        return {"changed": len(touched) - created if not body.dry_run else len(touched), "created": created}

    @api.get("/stories/{story_id}")
    def get_story(story_id: int) -> dict[str, Any]:
        story = ctx.stories.get(story_id)
        if story is None:
            raise api_error(404, "not_found")
        story["milestones"] = ctx.history.milestones(story_id, ctx.settings.get_preferences()["ui.language"])
        return story

    @api.post("/articles/{article_id}/detach")
    def detach_article(article_id: int) -> dict[str, Any]:
        """The user says this article is not about its story's event."""
        old = ctx.stories.story_of(article_id)
        try:
            new = ctx.stories.detach(article_id)
        except KeyError:
            raise api_error(404, "not_found") from None
        rescore([s for s in (old, new) if s is not None])
        still_exists = old is not None and ctx.stories.get(old) is not None
        return {"story_id": new, "previous_story_id": old if still_exists else None}

    @api.post("/stories/{story_id}/merge")
    def merge_stories(story_id: int, body: MergeRequest) -> dict[str, Any]:
        """The user says two stories are the same event; story_id is merged into body.into."""
        try:
            target = ctx.stories.merge(story_id, body.into)
        except KeyError:
            raise api_error(404, "not_found") from None
        rescore([target])
        story = ctx.stories.get(target)
        assert story is not None
        return story

    @api.post("/stories/{story_id}/summarize")
    def summarize_story(story_id: int) -> dict[str, str]:
        try:
            ctx.stories.request_summary(story_id)
        except KeyError:
            raise api_error(404, "not_found") from None
        ctx.ai_worker.wake()
        return {"status": "pending"}

    # -- notebook --------------------------------------------------------------------------
    def check_day(day: str) -> str:
        if not valid_day(day):
            raise api_error(422, "invalid_day")
        return day

    @api.get("/stories/{story_id}/note")
    def get_story_note(story_id: int) -> dict[str, Any]:
        return {"note": ctx.notebook.story_note(story_id)}

    @api.put("/stories/{story_id}/note")
    def put_story_note(story_id: int, body: NoteBody) -> dict[str, Any]:
        try:
            return {"note": ctx.notebook.save_story_note(story_id, body.body)}
        except KeyError:
            raise api_error(404, "not_found") from None

    @api.get("/meeting")
    def get_meeting(day: str | None = None) -> dict[str, Any]:
        day = check_day(day) if day else ctx.notebook.today()
        return {"day": day, "today": ctx.notebook.today(), "items": ctx.notebook.meeting(day)}

    @api.post("/meeting", status_code=201)
    def add_meeting(body: MeetingAdd) -> dict[str, Any]:
        if (body.story_id is None) == (body.article_id is None):
            raise api_error(422, "invalid_request")
        try:
            if body.article_id is not None:
                return ctx.notebook.add_article_to_meeting(body.article_id)
            assert body.story_id is not None
            return ctx.notebook.add_to_meeting(body.story_id)
        except KeyError:
            raise api_error(404, "not_found") from None

    @api.patch("/meeting/{item_id}")
    def patch_meeting(item_id: int, body: MeetingPatch) -> dict[str, Any]:
        try:
            return ctx.notebook.update_item(item_id, body.comment)
        except KeyError:
            raise api_error(404, "not_found") from None

    @api.delete("/meeting/{item_id}", status_code=204)
    def delete_meeting(item_id: int) -> None:
        try:
            ctx.notebook.remove_item(item_id)
        except KeyError:
            raise api_error(404, "not_found") from None

    @api.put("/meeting/order")
    def order_meeting(body: MeetingOrder) -> dict[str, Any]:
        day = check_day(body.day)
        try:
            items = ctx.notebook.reorder(day, body.ids)
        except ValueError:
            raise api_error(409, "order_mismatch") from None
        return {"day": day, "today": ctx.notebook.today(), "items": items}

    @api.get("/notebook")
    def notebook_days(month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")]) -> dict[str, Any]:
        return {"month": month, "today": ctx.notebook.today(), "days": ctx.notebook.days(month)}

    @api.get("/notebook/{day}")
    def notebook_day(day: str) -> dict[str, Any]:
        return ctx.notebook.day(check_day(day))

    @api.put("/notebook/{day}/note")
    def put_day_note(day: str, body: NoteBody) -> dict[str, Any]:
        return {"day_note": ctx.notebook.save_day_note(check_day(day), body.body)}

    # -- history -----------------------------------------------------------------------------
    @api.get("/history")
    def history_month(month: Annotated[str, Query(pattern=r"^\d{4}-\d{2}$")]) -> dict[str, Any]:
        return {"month": month, "today": ctx.notebook.today(), "days": ctx.history.month(month)}

    @api.get("/history/{day}")
    def history_day(
        day: str,
        moment: Literal["morning", "day"] = "morning",
        min_sources: Annotated[int, Query(ge=1, le=50)] = 1,
        limit: Annotated[int, Query(ge=1, le=200)] = 40,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        """A past day's stories ranked as they were at that moment (reconstructed, see repo/history.py)."""
        prefs = ctx.settings.get_preferences()
        view = day_view(check_day(day), moment, int(prefs["history.morning_hour"]), datetime.now(UTC))
        if view.as_of <= view.window_start:
            return {"day": day, "moment": moment, "as_of": utc_now_iso(view.as_of), "window_start": utc_now_iso(view.window_start),
                    "items": [], "total": 0, "unclustered": 0, "future": True}
        page = ctx.history.ranking(view, weights_from(prefs), interest_from(prefs), min_sources=min_sources,
                                   limit=limit, offset=offset)
        return {**page, "future": False}

    # -- full text ---------------------------------------------------------------------------
    @api.get("/articles/{article_id}/fulltext")
    def get_fulltext(article_id: int) -> dict[str, Any]:
        """The article's full text (local reading only; outputs never include it)."""
        return {"fulltext": ctx.fulltext.get(article_id)}

    @api.post("/articles/{article_id}/fulltext")
    def request_fulltext(article_id: int) -> dict[str, str]:
        try:
            status = ctx.fulltext.request(article_id)
        except KeyError:
            raise api_error(404, "not_found") from None
        ctx.fulltext_worker.wake()
        return {"status": status}

    @api.post("/articles/{article_id}/fulltext/translate")
    def translate_fulltext(article_id: int) -> dict[str, str]:
        try:
            status = ctx.fulltext.request_translation(article_id, ai_languages(ctx.settings.get_preferences()))
        except LookupError:
            raise api_error(409, "no_fulltext") from None
        ctx.ai_worker.wake()
        return {"status": status}

    @api.get("/fulltext/browsers")
    def list_browsers() -> dict[str, Any]:
        prefs = ctx.settings.get_preferences()
        chosen = browser_for(str(prefs.get("fulltext.browser_path") or ""))
        return {
            "browsers": [{"name": b.name, "path": str(b.executable)} for b in find_browsers()],
            "chosen": str(chosen.executable) if chosen else None,
            "own_profile": str(ctx.paths.browser_profile),
            "main_profile_in_use": bool(chosen and profile_in_use(chosen.main_profile)),
        }

    @api.get("/fulltext/sites")
    def fulltext_sites() -> dict[str, Any]:
        """Subscription sites and whether their full text works (the latest attempt)."""
        return {"sites": ctx.fulltext.sites(), "login_window_open": profile_in_use(ctx.paths.browser_profile)}

    @api.post("/fulltext/login")
    def open_login(body: LoginRequest) -> dict[str, str]:
        """Opens a site's page so the user can sign in: in the everyday browser, or (extension.profile = own) in a
        normal window on World Signal's own profile, where the extension and the sign-ins live. No automation."""
        prefs = ctx.settings.get_preferences()
        browser = browser_for(str(prefs.get("fulltext.browser_path") or ""))
        if browser is None:
            raise api_error(409, "no_browser")
        url = str(body.url) if body.url else "about:blank"
        if body.source_id is not None:
            source = next((s for s in ctx.sources.list_sources() if s["id"] == body.source_id), None)
            if source is None:
                raise api_error(404, "not_found")
            if not source.get("homepage"):
                raise api_error(409, "no_homepage")
            url = str(source["homepage"])
        # The program is handed to the browser as it is: a stored homepage is not re-validated at use, so only
        # a web page (or the blank page) may reach the command line (not a file:, a script or a browser switch).
        if url != "about:blank" and not url.lower().startswith(("http://", "https://")):
            raise api_error(409, "bad_url")
        if prefs.get("extension.profile") == "own":
            open_login_window(browser, ctx.paths.browser_profile, url)
        else:
            subprocess.Popen([str(browser.executable), url])  # noqa: S603 - the browser found on this PC, the site's page
        return {"status": "opened"}

    @api.post("/extension/profile/open")
    def open_extension_profile() -> dict[str, str]:
        """Opens World Signal's own browser profile on the browser's extensions page, where the user loads the
        extension (once) and signs in to the subscriptions."""
        browser = browser_for(str(ctx.settings.get_preferences().get("fulltext.browser_path") or ""))
        if browser is None:
            raise api_error(409, "no_browser")
        open_login_window(browser, ctx.paths.browser_profile, "chrome://extensions")  # a fixed page, never user input
        return {"status": "opened"}

    def end_site_rest(source_id: int) -> None:
        """The user wants the site tried again: its pause ends, and so does the extension's rest after trouble."""
        ctx.fulltext.resume_source(source_id)
        if ctx.bridge is not None:
            ctx.bridge.clear_cooldown(source_id)

    @api.post("/fulltext/sites/{source_id}/test")
    def test_site(source_id: int) -> dict[str, Any]:
        """Fetch the full text of the site's newest article now (to check a fresh sign-in)."""
        article_id = ctx.fulltext.latest_article(source_id)
        if article_id is None:
            raise api_error(409, "no_articles")
        end_site_rest(source_id)
        status = ctx.fulltext.request(article_id)
        ctx.fulltext_worker.wake()
        return {"article_id": article_id, "status": status}

    @api.post("/fulltext/sources/{source_id}/resume")
    def resume_fulltext_source(source_id: int) -> dict[str, str]:
        end_site_rest(source_id)
        ctx.fulltext_worker.wake()
        return {"status": "resumed"}

    # -- AI ------------------------------------------------------------------------------
    @api.get("/ai/status")
    def ai_status() -> dict[str, Any]:
        return ctx.ai_worker.status()

    # -- cloud AI: keys (write-only) and a connection test -----------------------------------------------
    def key_store() -> SecretStore:
        if ctx.keys is None:
            raise api_error(409, "keys_unavailable")
        return ctx.keys

    @api.get("/ai/keys")
    def ai_keys() -> dict[str, bool]:
        """Which services have a key; the keys themselves never leave the backend."""
        return key_store().status()

    @api.put("/ai/keys/{provider}")
    def set_ai_key(provider: Literal["gemini", "openai", "anthropic"], body: ApiKeyBody) -> dict[str, bool]:
        store = key_store()
        store.set(provider, body.key.strip())
        ctx.ai_worker.wake()
        return store.status()

    @api.delete("/ai/keys/{provider}")
    def delete_ai_key(provider: Literal["gemini", "openai", "anthropic"]) -> dict[str, bool]:
        store = key_store()
        store.delete(provider)
        return store.status()

    @api.post("/ai/cloud/test")
    async def cloud_test(body: CloudTestRequest) -> dict[str, Any]:
        """Check the saved key of a service and list its models (the OpenAI-compatible address from the request)."""
        key = key_store().get(body.provider) or ""
        url = str(body.url).rstrip("/") if body.url else ""
        if not key and not (body.provider == "openai" and url and url != OPENAI_URL):
            return {"ok": False, "error_code": "no_key", "models": []}
        try:
            models = await make_cloud_client(body.provider, key, url).list_models()
        except OllamaError as exc:
            return {"ok": False, "error_code": exc.code, "models": []}
        return {"ok": True, "error_code": None, "models": models}

    @api.post("/ai/test")
    async def ai_test(body: OllamaTestRequest) -> dict[str, Any]:
        """Check an Ollama address and list its models (does not save anything)."""
        client = OllamaClient(str(body.url))
        try:
            version = await client.version()
            models = await client.list_models()
            caps = await asyncio.gather(*(client.capabilities(m.name) for m in models), return_exceptions=True)
        except OllamaError as exc:
            return {"ok": False, "error_code": exc.code, "version": None, "models": []}
        return {
            "ok": True,
            "error_code": None,
            "version": version,
            "models": [
                {
                    "name": m.name,
                    "size_gb": round(m.size_bytes / 1e9, 1),
                    "parameters": m.parameter_size,
                    # None: unknown (older Ollama or the lookup failed); the UI then offers the model everywhere.
                    "capabilities": c if isinstance(c, list) else None,
                }
                for m, c in zip(models, caps, strict=True)
            ],
        }

    @api.post("/ai/retry")
    def ai_retry() -> dict[str, Any]:
        """Retry failed items and re-check the Ollama connection now."""
        count = ctx.ai.retry_failed()
        ctx.ai_worker.wake()
        return {"requeued": count}

    # -- sources ---------------------------------------------------------------------
    @api.get("/sources")
    def list_sources() -> list[dict[str, Any]]:
        return ctx.sources.list_sources()

    @api.post("/sources", status_code=201)
    def create_source(body: SourceCreate) -> dict[str, Any]:
        data = body.model_dump(exclude={"feed_url"})
        if data.get("homepage"):
            data["homepage"] = str(data["homepage"])
        try:
            source_id = ctx.sources.create_source(data, str(body.feed_url))
        except Conflict:
            raise api_error(409, "feed_exists") from None
        ctx.collector.request_run(source_id)
        return ctx.sources.get_source(source_id)

    @api.patch("/sources/{source_id}")
    def patch_source(source_id: int, body: SourcePatch) -> dict[str, Any]:
        changes = body.model_dump(exclude_unset=True)
        if "homepage" in changes and changes["homepage"] is not None:
            changes["homepage"] = str(changes["homepage"])
        if changes.get("name") is not None:
            changes["name"] = changes["name"].strip()
        try:
            ctx.sources.update_source(source_id, changes)
            if changes.get("enabled"):
                ctx.collector.request_run(source_id)
            return ctx.sources.get_source(source_id)
        except NotFound:
            raise api_error(404, "not_found") from None

    @api.delete("/sources/{source_id}", status_code=204)
    def delete_source(source_id: int) -> None:
        try:
            ctx.sources.delete_source(source_id)
        except NotFound:
            raise api_error(404, "not_found") from None

    @api.post("/sources/{source_id}/refresh")
    def refresh_source(source_id: int) -> dict[str, Any]:
        return {"scheduled": ctx.collector.request_run(source_id)}

    @api.post("/sources/{source_id}/feeds", status_code=201)
    def add_feed(source_id: int, body: FeedCreate) -> dict[str, Any]:
        try:
            ctx.sources.add_feed(source_id, str(body.url), body.label)
        except NotFound:
            raise api_error(404, "not_found") from None
        except Conflict:
            raise api_error(409, "feed_exists") from None
        ctx.collector.request_run(source_id)
        return ctx.sources.get_source(source_id)

    @api.patch("/feeds/{feed_id}")
    def patch_feed(feed_id: int, body: FeedPatch) -> dict[str, Any]:
        try:
            ctx.sources.update_feed(feed_id, body.model_dump(exclude_unset=True))
            feed = ctx.sources.get_feed(feed_id)
        except NotFound:
            raise api_error(404, "not_found") from None
        ctx.collector.request_run(feed["source_id"])
        return ctx.sources.get_source(feed["source_id"])

    @api.delete("/feeds/{feed_id}", status_code=204)
    def delete_feed(feed_id: int) -> None:
        try:
            ctx.sources.delete_feed(feed_id)
        except NotFound:
            raise api_error(404, "not_found") from None

    async def suggest_feeds(client: httpx.AsyncClient, url: str, page_loaded: bool) -> list[dict[str, str]]:
        html = None
        if page_loaded:
            try:
                _, page, url, _, _ = await download(client, url)
                html = page.decode("utf-8", errors="replace")
            except FetchError:
                html = None
        return await discover(client, url, html)

    SUGGEST_ON = {"not_a_feed", "http_401", "http_403", "http_404"}

    @api.post("/feeds/test")
    async def test_feed(body: FeedTestRequest) -> dict[str, Any]:
        """Fetch a feed without saving it, so the user sees whether it works."""
        async with make_client() as client:
            try:
                result = await fetch_feed(client, str(body.url))
            except FetchError as exc:
                failed: dict[str, Any] = {"ok": False, "error_code": exc.code, "error_detail": exc.detail[:300]}
                if exc.code in SUGGEST_ON:
                    # A web page (or one closed to programs): offer the feeds it declares and the news sitemaps
                    # its robots.txt allows.
                    failed["suggestions"] = await suggest_feeds(client, str(body.url), exc.code == "not_a_feed")
                return failed
        feed = result.feed
        assert feed is not None
        dated = [e.published_at for e in feed.entries if e.published_at]
        return {
            "ok": len(feed.entries) > 0,
            "error_code": None if feed.entries else "empty_feed",
            "title": feed.title,
            "language": feed.language,
            "item_count": len(feed.entries),
            "newest_at": utc_now_iso(max(dated)) if dated else None,
            "sample_titles": [e.title for e in feed.entries[:5]],
            "final_url": result.final_url,
        }

    @api.post("/collector/run")
    def run_collector() -> dict[str, Any]:
        return {"scheduled": ctx.collector.request_run()}

    # -- desktop helpers ------------------------------------------------------------
    @api.post("/app/show")
    def show_window() -> dict[str, bool]:
        if ctx.show_window is not None:
            ctx.show_window()
        return {"ok": ctx.show_window is not None}

    @api.post("/app/restart")
    def restart_app() -> dict[str, bool]:
        if ctx.restart is None:
            raise api_error(409, "restart_unavailable")
        ctx.restart()
        return {"ok": True}

    # -- e-mail -----------------------------------------------------------------------------------
    @api.post("/mail/draft")
    async def mail_draft(body: MailDraft) -> dict[str, Any]:
        """Opens a draft in the user's mail program; World Signal itself never sends mail."""
        try:
            return await asyncio.to_thread(mailer.open_draft, body.subject, body.html, body.text, body.cut_note)
        except mailer.MailError as exc:
            raise api_error(409, exc.code) from None

    # -- program updates -------------------------------------------------------------------
    def updater() -> Updater:
        if ctx.updater is None:
            raise api_error(409, "update_unavailable")
        return ctx.updater

    @api.get("/update")
    def update_status() -> dict[str, Any]:
        return {**updater().status(), "can_quit": ctx.quit is not None}

    @api.post("/update/check")
    async def update_check() -> dict[str, Any]:
        await asyncio.to_thread(updater().check)
        return update_status()

    @api.post("/update/download")
    async def update_download() -> dict[str, Any]:
        try:
            await asyncio.to_thread(updater().download)
        except UpdateError as exc:
            raise api_error(409 if exc.code in ("nothing_to_download", "no_checksum") else 502,
                            f"update_{exc.code}") from None
        return update_status()

    @api.post("/update/apply")
    def update_apply() -> dict[str, bool]:
        if ctx.quit is None:
            raise api_error(409, "update_needs_window")
        try:
            updater().apply(ctx.quit)
        except UpdateError as exc:
            raise api_error(409, f"update_{exc.code}") from None
        return {"ok": True}

    @api.delete("/update/result", status_code=204)
    def update_dismiss() -> None:
        updater().dismiss_result()

    # -- backups -------------------------------------------------------------------------
    @api.get("/backups")
    def list_backups() -> dict[str, Any]:
        return {
            "backups": [b.public() for b in ctx.backups.list()],
            "pending_restore": ctx.backups.pending_restore(),
            "last_restore": ctx.backups.last_restore(),
            "can_restart": ctx.restart is not None,
        }

    @api.post("/backups")
    def make_backup() -> dict[str, Any]:
        return ctx.backups.make("manual").public()

    @api.post("/backups/restore")
    def schedule_restore(body: RestoreRequest) -> dict[str, Any]:
        try:
            info = ctx.backups.schedule_restore(body.name)
        except InvalidBackup as exc:
            raise api_error(404 if exc.code == "not_found" else 422, f"backup_{exc.code}") from None
        return {"scheduled": info.public(), "can_restart": ctx.restart is not None}

    @api.delete("/backups/restore", status_code=204)
    def cancel_restore() -> None:
        ctx.backups.cancel_restore()

    # -- notifications -------------------------------------------------------------------
    @api.post("/notify/test")
    def test_notification() -> dict[str, bool]:
        if not ctx.notifier.test():
            raise api_error(409, "notify_unavailable")
        return {"ok": True}

    @api.post("/app/open-data-dir")
    def open_data_dir() -> dict[str, bool]:
        if os.name != "nt":
            raise api_error(501, "unsupported")
        subprocess.Popen(["explorer", str(ctx.paths.root)])  # noqa: S603,S607 - fixed program, our own path
        return {"ok": True}

    @api.post("/app/open-extension-dir")
    def open_extension_dir() -> dict[str, bool]:
        if os.name != "nt":
            raise api_error(501, "unsupported")
        folder = extension_dir()
        if folder is None:
            raise api_error(404, "no_extension_dir")
        subprocess.Popen(["explorer", str(folder)])  # noqa: S603,S607 - fixed program, our own folder
        return {"ok": True}

    for router in extension_routers(ctx, require_token):
        app.include_router(router)
    app.include_router(public)
    app.include_router(api)

    @app.api_route("/api/{rest:path}", methods=["GET", "POST", "PATCH", "DELETE", "PUT"], include_in_schema=False)
    def api_not_found(rest: str) -> None:
        raise api_error(404, "not_found")

    _mount_ui(app, ctx.ui_dir)
    return app


def _mount_ui(app: FastAPI, ui_dir: Path | None) -> None:
    if ui_dir is None or not (ui_dir / "index.html").is_file():
        log.warning("UI files not found (%s); only the API is served", ui_dir)
        return
    index = ui_dir / "index.html"
    app.mount("/assets", StaticFiles(directory=ui_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        candidate = (ui_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(ui_dir.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
