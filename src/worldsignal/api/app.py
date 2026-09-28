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
import subprocess
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, HttpUrl, field_validator

from .. import __version__
from ..ai.enrich import CATEGORIES
from ..ai.ollama import OllamaClient, OllamaError
from ..ai.worker import AiWorker
from ..collector.rss import FetchError, fetch_feed, make_client
from ..collector.service import Collector
from ..db import Database, utc_now_iso
from ..paths import DataPaths
from ..repo.ai import AiRepository
from ..repo.articles import ArticleFilter, ArticleRepository
from ..fulltext.fetch import browser_for, find_browsers, open_login_window, profile_in_use
from ..fulltext.worker import FullTextWorker
from ..repo.fulltext import FullTextRepository
from ..repo.history import HistoryRepository, day_view, local_datetime, next_day
from ..backup import BackupManager, InvalidBackup
from ..maintenance import Maintenance
from ..notify import Notifier
from ..repo.notebook import MAX_COMMENT, MAX_NOTE, NotebookRepository, valid_day
from ..repo.settings import DEFAULTS, SettingsRepository
from ..repo.sources import CATALOG_GROUPS, REGIONS, Conflict, NotFound, SourceRepository
from ..repo.stories import StoryFilter, StoryRepository
from ..stories.embedding import recommended_settings
from ..stories.worker import StoryWorker, interest_from, weights_from
from ..updater import UpdateError, Updater
from ..country import TOPICS, HomeState, countries as country_data, profile as country_profile
from ..home_sync import HomeSync
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
    extra: dict[str, Any] = field(default_factory=dict)


def api_error(status: int, code: str, message: str = "") -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


# -- request models -------------------------------------------------------------
Region = Literal[REGIONS]  # type: ignore[valid-type]
Group = Literal[CATALOG_GROUPS]  # type: ignore[valid-type]


class FeedFilters(BaseModel):
    model_config = {"extra": "forbid"}

    regions: list[Region] = Field(default_factory=list)
    groups: list[Group] = Field(default_factory=list)
    langs: list[Annotated[str, Field(min_length=2, max_length=3)]] = Field(default_factory=list, max_length=50)
    sources: list[int] = Field(default_factory=list, max_length=500)
    categories: list[Literal[CATEGORIES]] = Field(default_factory=list)  # type: ignore[valid-type]
    turkey: bool = False


class SettingsPatch(BaseModel):
    model_config = {"extra": "forbid"}

    ui_language: Literal[SUPPORTED_LANGUAGES] | None = Field(None, alias="ui.language")  # type: ignore[valid-type]
    ui_theme: Literal["system", "light", "dark"] | None = Field(None, alias="ui.theme")
    feed_window_hours: int | None = Field(None, alias="feed.window_hours", ge=1, le=168)
    feed_view: Literal["stories", "articles"] | None = Field(None, alias="feed.view")
    feed_filters: FeedFilters | None = Field(None, alias="feed.filters")
    update_auto_check: bool | None = Field(None, alias="update.auto_check")
    home_country: Annotated[str, Field(pattern=r"^([A-Z]{2})?$")] | None = Field(None, alias="home.country")
    home_related: list[Annotated[str, Field(pattern=r"^[A-Z]{2}$")]] | None = Field(None, alias="home.related", max_length=50)
    home_topics: list[Literal[TOPICS]] | None = Field(None, alias="home.topics")  # type: ignore[valid-type]
    home_keywords: list[Annotated[str, Field(min_length=2, max_length=60)]] | None = Field(
        None, alias="home.keywords", max_length=50
    )
    update_auto_download: bool | None = Field(None, alias="update.auto_download")
    ai_enabled: bool | None = Field(None, alias="ai.enabled")
    ai_url: HttpUrl | None = Field(None, alias="ai.url")
    ai_model: str | None = Field(None, alias="ai.model", max_length=200)
    ai_max_age_hours: int | None = Field(None, alias="ai.max_age_hours", ge=1, le=168)
    ai_yield_gpu: bool | None = Field(None, alias="ai.yield_gpu")
    stories_embed_model: str | None = Field(None, alias="stories.embed_model", min_length=1, max_length=200)
    stories_embed_summary: bool | None = Field(None, alias="stories.embed_summary")
    stories_threshold: float | None = Field(None, alias="stories.threshold", ge=0.5, le=0.95)
    stories_cohesion: float | None = Field(None, alias="stories.cohesion", ge=0, le=0.9)
    fulltext_enabled: bool | None = Field(None, alias="fulltext.enabled")
    fulltext_browser_path: str | None = Field(None, alias="fulltext.browser_path", max_length=400)
    fulltext_profile: Literal["own", "main"] | None = Field(None, alias="fulltext.profile")
    fulltext_visible: bool | None = Field(None, alias="fulltext.visible")
    fulltext_per_site_hour: int | None = Field(None, alias="fulltext.per_site_hour", ge=1, le=20)
    fulltext_auto_min_score: float | None = Field(None, alias="fulltext.auto_min_score", ge=0, le=100)
    fulltext_auto_per_story: int | None = Field(None, alias="fulltext.auto_per_story", ge=0, le=5)
    history_morning_hour: int | None = Field(None, alias="history.morning_hour", ge=0, le=23)
    retention_fulltext_days: int | None = Field(None, alias="retention.fulltext_days", ge=0, le=3650)
    backup_keep_daily: int | None = Field(None, alias="backup.keep_daily", ge=1, le=90)
    app_close_to_tray: bool | None = Field(None, alias="app.close_to_tray")
    notify_enabled: bool | None = Field(None, alias="notify.enabled")
    notify_min_score: float | None = Field(None, alias="notify.min_score", ge=0, le=100)
    notify_min_sources: int | None = Field(None, alias="notify.min_sources", ge=2, le=30)
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
    story_id: int


class MeetingPatch(BaseModel):
    comment: str = Field(max_length=MAX_COMMENT)


class MeetingOrder(BaseModel):
    day: str
    ids: list[int] = Field(max_length=500)


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
        if ctx.run_collector:
            # New reports go into stories (and the AI queue) right away instead of at the next poll.
            ctx.collector.on_new_articles[:] = [ctx.story_worker.wake, ctx.ai_worker.wake]
            tasks.append(asyncio.create_task(ctx.collector.run_forever(), name="collector"))
            tasks.append(asyncio.create_task(ctx.ai_worker.run_forever(), name="ai-worker"))
            tasks.append(asyncio.create_task(ctx.story_worker.run_forever(), name="story-worker"))
            tasks.append(asyncio.create_task(ctx.fulltext_worker.run_forever(), name="fulltext-worker"))
            tasks.append(asyncio.create_task(ctx.maintenance.run_forever(), name="maintenance"))
            tasks.append(asyncio.create_task(ctx.notifier.run_forever(), name="notifier"))
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
        }

    @api.get("/meta")
    def meta() -> dict[str, Any]:
        return {
            "regions": list(REGIONS),
            "groups": list(CATALOG_GROUPS),
            "languages": ctx.articles.languages(),
            "categories": list(CATEGORIES),
            "ui_languages": list(SUPPORTED_LANGUAGES),
            "data_dir": str(ctx.paths.root),
            # The user's country: settings "home.country", or this when it is "" (Windows' region).
            "home_country": ctx.home.profile().code if ctx.home is not None else "TR",
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
        if "home.keywords" in values:
            values["home.keywords"] = list(dict.fromkeys(k.strip() for k in values["home.keywords"] if k.strip()))
        ctx.settings.set_many(values)
        if any(k.startswith("home.") for k in values) and ctx.home_sync is not None:
            ctx.home_sync.wake()
        if any(k.startswith("ai.") for k in values):
            ctx.ai_worker.wake()
        if any(k.split(".")[0] in ("stories", "score", "interest") for k in values):
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
            query=(q or "").strip() or None, before=cursor, limit=limit,
        )
        items = ctx.articles.list(filt)
        next_cursor = f"{items[-1]['sort_at']}|{items[-1]['id']}" if len(items) == limit else None
        # The total is only needed for the first page (shown in the header).
        total = ctx.articles.count(filt) if cursor is None else None
        return {"items": items, "next": next_cursor, "total": total}

    @api.post("/articles/{article_id}/ai")
    def request_ai(article_id: int) -> dict[str, Any]:
        """Ask for Turkish title/summary of one article now (jumps the queue)."""
        try:
            status = ctx.ai.request(article_id)
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
        q: Annotated[str | None, Query(max_length=200)] = None,
        sort: Literal["score", "recent"] = "score",
        limit: Annotated[int, Query(ge=1, le=200)] = 40,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, Any]:
        since = utc_now_iso(datetime.now(UTC) - timedelta(hours=hours)) if hours else None
        items, total = ctx.stories.list(StoryFilter(
            since=since, source_ids=source or (), regions=region or (), groups=group or (), languages=lang or (),
            categories=category or (), turkey_only=turkey, min_sources=min_sources, query=(q or "").strip() or None,
            sort=sort, limit=limit, offset=offset,
        ))
        return {"items": items, "total": total}

    @api.get("/stories/{story_id}")
    def get_story(story_id: int) -> dict[str, Any]:
        story = ctx.stories.get(story_id)
        if story is None:
            raise api_error(404, "not_found")
        story["milestones"] = ctx.history.milestones(story_id)
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
        try:
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
            status = ctx.fulltext.request_translation(article_id)
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
        return {"sites": ctx.fulltext.sites(), "login_window_open": profile_in_use(ctx.paths.browser_profile)
                and not ctx.fulltext_worker.browser_open}

    @api.post("/fulltext/login")
    def open_login(body: LoginRequest) -> dict[str, str]:
        """Opens a normal browser window (no automation) on World Signal's profile so the user can sign in
        once. If that window is already open, the page opens in it as a new tab."""
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
        # The hidden full-text browser uses the same profile: it must not receive the page.
        ctx.fulltext_worker.make_room_for_login()
        open_login_window(browser, ctx.paths.browser_profile, url)
        return {"status": "opened"}

    @api.post("/fulltext/sites/{source_id}/test")
    def test_site(source_id: int) -> dict[str, Any]:
        """Fetch the full text of the site's newest article now (to check a fresh sign-in)."""
        article_id = ctx.fulltext.latest_article(source_id)
        if article_id is None:
            raise api_error(409, "no_articles")
        ctx.fulltext.resume_source(source_id)
        status = ctx.fulltext.request(article_id)
        ctx.fulltext_worker.wake()
        return {"article_id": article_id, "status": status}

    @api.post("/fulltext/sources/{source_id}/resume")
    def resume_fulltext_source(source_id: int) -> dict[str, str]:
        ctx.fulltext.resume_source(source_id)
        ctx.fulltext_worker.wake()
        return {"status": "resumed"}

    # -- AI ------------------------------------------------------------------------------
    @api.get("/ai/status")
    def ai_status() -> dict[str, Any]:
        return ctx.ai_worker.status()

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

    @api.post("/feeds/test")
    async def test_feed(body: FeedTestRequest) -> dict[str, Any]:
        """Fetch a feed without saving it, so the user sees whether it works."""
        async with make_client() as client:
            try:
                result = await fetch_feed(client, str(body.url))
            except FetchError as exc:
                return {"ok": False, "error_code": exc.code, "error_detail": exc.detail[:300]}
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
