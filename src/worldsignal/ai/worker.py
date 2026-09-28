"""Background AI worker: story summaries and article enrichment, one job at a time.

Story summaries (several sources about one event) come first, highest score
first; then single articles, newest first.

The AI runs in Ollama on this (or another) computer, or at a cloud service the user chose (``ai.provider``,
cloud.py). With Ollama the GPU is a single shared resource, so there is exactly one job in flight; with a cloud
service jobs are spaced to stay under the requests per minute the user set (``ai.cloud_rpm``).
If the service is unavailable, the model is missing or the key is wrong, the worker pauses (the
articles simply stay in their original language), reports the reason in its
status and retries periodically or when the user presses "retry".
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any

from ..apikeys import SecretStore
from ..country import HomeProfile
from .cloud import OPENAI_URL
from .cloud import make_client as make_cloud_client
from ..db import utc_now_iso
from ..repo.ai import AiRepository, Job
from ..repo.fulltext import FullTextRepository
from . import translate
from ..repo.settings import SettingsRepository
from ..repo.stories import StoryRepository
from .enrich import PROMPT_VERSION, EnrichInput, EnrichTask, validate
from .languages import effective
from .story import pick_reports, render_reports, story_prompt, story_schema, validate_story
from .ollama import OllamaClient, OllamaError

log = logging.getLogger(__name__)

IDLE_SECONDS = 20
PAUSED_SECONDS = 30
# Errors that mean "the service is unavailable or busy", not "this article failed".
# A timeout usually means another program is using the GPU; the article is not penalised.
SERVICE_ERRORS = {"unreachable", "model_missing", "timeout", "bad_key", "rate_limited"}
# Output room per language: a headline and a few sentences (Arabic and CJK scripts take more tokens).
TOKENS_PER_LANGUAGE = 400
STORY_WINDOW_HOURS = 48
# While this many recent reports still wait to be matched into stories (first start, or after a long
# pause), stories keep growing by the minute: summarising them now would be redone again and again.
STORY_BACKLOG_LIMIT = 100


class AiWorker:
    def __init__(
        self,
        ai: AiRepository,
        settings: SettingsRepository,
        client_factory: Callable[[str], OllamaClient] = OllamaClient,
        stories: StoryRepository | None = None,
        fulltext: FullTextRepository | None = None,
        home: Callable[[], HomeProfile] | None = None,
        keys: SecretStore | None = None,
        cloud_factory: Callable[[str, str, str], Any] = make_cloud_client,
    ) -> None:
        self.keys = keys  # API keys of cloud services (apikeys.py)
        self.cloud_factory = cloud_factory
        self.ai = ai
        self.home = home  # the user's country: its topics go into the prompt
        self.settings = settings
        self.stories = stories
        self.fulltext = fulltext
        self.client_factory = client_factory
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._state: dict[str, Any] = {
            "running": False,
            # starting | ok | idle | disabled | no_model | unreachable | model_missing | timeout | gpu_busy
            "state": "starting",
            "busy_with": None,  # other model(s) occupying the GPU when state == gpu_busy
            "model": None,
            "url": None,
            "current_article_id": None,
            "current_story_id": None,
            "current_translation_id": None,
            "last_error": None,
            "last_done_at": None,
            "avg_seconds": None,
        }
        self._durations: list[float] = []

    # -- public ------------------------------------------------------------------
    def status(self) -> dict[str, Any]:
        return {**self._state, **self.ai.counts()}

    def wake(self) -> None:
        """Re-check immediately (settings changed, retry pressed, user request). Thread-safe."""
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    async def run_forever(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._state["running"] = True
        log.info("AI worker started")
        try:
            while True:
                # Cleared before the step, not after: a wake() that arrives during the step is kept.
                self._wake.clear()
                try:
                    delay = await self.step()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("AI worker step failed")
                    delay = PAUSED_SECONDS
                if delay:
                    await self._sleep(delay)
        finally:
            self._state["running"] = False
            log.info("AI worker stopped")

    # -- internals ---------------------------------------------------------------------
    async def _sleep(self, seconds: float) -> None:
        assert self._wake is not None
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=seconds)
        except TimeoutError:
            pass

    async def step(self) -> float:
        """Do at most one unit of work. Returns how long to wait before the next step."""
        prefs = await asyncio.to_thread(self.settings.get_preferences)
        provider = str(prefs.get("ai.provider") or "ollama")
        cloud = provider != "ollama"
        model = str(prefs.get(f"ai.{provider}_model" if cloud else "ai.model") or "").strip()
        url = prefs.get("ai.openai_url") if provider == "openai" else (provider if cloud else prefs.get("ai.url"))
        self._state.update(model=model or None, url=url, provider=provider)
        if not prefs.get("ai.enabled"):
            self._state.update(state="disabled", current_article_id=None)
            return PAUSED_SECONDS
        key = ""
        if cloud:
            key = (await asyncio.to_thread(self.keys.get, provider) if self.keys is not None else None) or ""
            # An OpenAI-compatible service on the local network (LM Studio …) may need no key.
            if not key and not (provider == "openai" and prefs.get("ai.openai_url") != OPENAI_URL):
                self._state.update(state="no_key", current_article_id=None)
                return PAUSED_SECONDS
        if not model:
            self._state.update(state="no_model", current_article_id=None)
            return PAUSED_SECONDS
        make = (lambda: self.cloud_factory(provider, key, str(prefs.get("ai.openai_url") or ""))) if cloud else (
            lambda: self.client_factory(url))
        pace = 60.0 / max(1, int(prefs.get("ai.cloud_rpm") or 10)) if cloud else 0.0

        languages = tuple(effective(prefs))
        since = utc_now_iso(datetime.now(UTC) - timedelta(hours=int(prefs.get("ai.max_age_hours", 24))))
        await asyncio.to_thread(self.ai.enqueue_recent, since)
        job = await asyncio.to_thread(self.ai.next_job, since, languages)
        story_job = None
        if self.stories is not None:
            story_since = utc_now_iso(datetime.now(UTC) - timedelta(hours=STORY_WINDOW_HOURS))
            settled = await asyncio.to_thread(self.stories.embedding_backlog, story_since) <= STORY_BACKLOG_LIMIT
            story_job = await asyncio.to_thread(
                partial(self.stories.next_story_job, story_since, int(prefs.get("stories.min_sources_for_ai", 2)),
                        automatic=settled, languages=languages)
            )
        translation = await asyncio.to_thread(self.fulltext.next_translation) if self.fulltext is not None else None
        if job is None and story_job is None and translation is None:
            # Still verify the service so the UI can warn before work arrives.
            try:
                await make().version()
                self._state.update(state="idle", current_article_id=None, last_error=None)
            except OllamaError as exc:
                self._state.update(state="unreachable", last_error=exc.code)
            return IDLE_SECONDS

        client = make()
        if not cloud and prefs.get("ai.yield_gpu", True):
            # Be polite: if the user (or another program) has a different model loaded,
            # wait instead of pushing it out of the graphics card's memory.
            try:
                # Models running on the CPU (size_vram 0, e.g. our own embedding model) leave the GPU free.
                others = [
                    m["name"] for m in await client.loaded_models()
                    if m.get("name") != model and m.get("size_vram", 1) != 0
                ]
            except OllamaError as exc:
                self._state.update(state="unreachable", last_error=exc.code, current_article_id=None, busy_with=None)
                return PAUSED_SECONDS
            if others:
                self._state.update(state="gpu_busy", busy_with=", ".join(others), current_article_id=None)
                return PAUSED_SECONDS
        self._state["busy_with"] = None

        if translation is not None:  # the user is waiting for it
            delay = await self._run_translation(client, model, translation, languages)
        elif story_job is not None:
            delay = await self._run_story(client, model, story_job, languages)
        else:
            assert job is not None
            delay = await self._run_article(client, model, job, prefs, languages)
        return max(delay, pace)

    async def _run_article(self, client: Any, model: str, job: Job, prefs: dict[str, Any],
                           languages: tuple[str, ...]) -> float:
        self._state["current_article_id"] = job.article_id
        inp = EnrichInput(job.source_name, job.language, job.title, job.summary)
        task = self.task(prefs, languages)
        started = time.perf_counter()
        try:
            result = await client.chat_json(model, task.system_prompt, inp.render(), task.schema, keep_alive="30m",
                                            num_predict=300 + TOKENS_PER_LANGUAGE * len(languages))
            enriched = validate(result.data, inp, task)
        except OllamaError as exc:
            self._state["current_article_id"] = None
            if exc.code in SERVICE_ERRORS:
                log.warning("AI paused: %s", exc)
                self._state.update(state=exc.code, last_error=exc.code)
                return PAUSED_SECONDS
            log.warning("AI failed for article %s: %s", job.article_id, exc)
            await asyncio.to_thread(self._fail, job, exc.code)
            self._state.update(state="ok", last_error=exc.code)
            return 0
        except ValueError as exc:
            await asyncio.to_thread(self._fail, job, "bad_response")
            self._state.update(state="ok", last_error="bad_response", current_article_id=None)
            log.warning("AI output rejected for article %s: %s", job.article_id, exc)
            return 0

        elapsed = time.perf_counter() - started
        await asyncio.to_thread(
            self.ai.store_result, job.article_id, enriched,
            model=model, prompt_version=PROMPT_VERSION, duration_ms=int(elapsed * 1000),
        )
        self._durations = (self._durations + [elapsed])[-50:]
        self._state.update(
            state="ok", current_article_id=None, last_error=None, last_done_at=utc_now_iso(),
            avg_seconds=round(sum(self._durations) / len(self._durations), 1),
        )
        return 0

    def task(self, prefs: dict[str, Any], languages: tuple[str, ...]) -> EnrichTask:
        """What an article job asks for: the user's languages and topics (``home.topics``, the country's default
        when unset), and the Türkiye question only for users in Türkiye."""
        home = self.home() if self.home is not None else None
        topics = tuple(home.topics) if home is not None else ()
        return EnrichTask(languages, topics, ask_turkey=home is None or home.code == "TR")

    async def _run_translation(self, client: OllamaClient, model: str, item: dict[str, Any],
                               languages: tuple[str, ...]) -> float:
        """Full text into the user's languages, chunk by chunk; the article's own language is not translated."""
        assert self.fulltext is not None
        self._state["current_translation_id"] = item["article_id"]
        text = item["text"] or ""
        result: dict[str, str] = dict(item.get("translations") or {})
        try:
            for lang in translate.targets(list(languages), item["language"]):
                if result.get(lang):
                    continue  # done earlier; only a newly added language is missing
                parts = []
                for chunk in translate.chunks(text):
                    answer = await client.chat_json(
                        model, translate.system_prompt(lang), chunk, translate.SCHEMA,
                        num_predict=translate.NUM_PREDICT, keep_alive="30m",
                    )
                    translated = str(answer.data.get("translation", "")).strip()
                    if not translated:
                        raise ValueError("empty_translation")
                    parts.append(translated)
                result[lang] = "\n\n".join(parts)
        except OllamaError as exc:
            self._state["current_translation_id"] = None
            if exc.code in SERVICE_ERRORS:
                self._state.update(state=exc.code, last_error=exc.code)
                return PAUSED_SECONDS
            await asyncio.to_thread(self.fulltext.store_translation_failure, item["article_id"])
            self._state.update(state="ok", last_error=exc.code)
            return 0
        except ValueError:
            await asyncio.to_thread(self.fulltext.store_translation_failure, item["article_id"])
            self._state.update(state="ok", last_error="bad_response", current_translation_id=None)
            return 0
        await asyncio.to_thread(self.fulltext.store_translation, item["article_id"], result)
        self._state.update(state="ok", current_translation_id=None, last_error=None, last_done_at=utc_now_iso())
        return 0

    def _fail(self, job: Job, code: str) -> None:
        if job.upgrade:
            self.ai.store_upgrade_failure(job.article_id, code)  # keep the finished text
        else:
            self.ai.store_failure(job.article_id, code)

    async def _run_story(self, client: OllamaClient, model: str, story: dict[str, Any],
                         languages: tuple[str, ...]) -> float:
        assert self.stories is not None
        self._state["current_story_id"] = story["id"]
        reports = pick_reports(story["members"])
        started = time.perf_counter()
        try:
            result = await client.chat_json(
                model, story_prompt(languages), render_reports(reports, story["source_count"]), story_schema(languages),
                keep_alive="30m", num_predict=300 + 2 * TOKENS_PER_LANGUAGE * len(languages),
            )
            written = validate_story(result.data, reports, story["source_count"], languages)
        except OllamaError as exc:
            self._state["current_story_id"] = None
            if exc.code in SERVICE_ERRORS:
                self._state.update(state=exc.code, last_error=exc.code)
                return PAUSED_SECONDS
            await asyncio.to_thread(self.stories.store_story_ai_failure, story["id"], exc.code)
            self._state.update(state="ok", last_error=exc.code)
            return 0
        except ValueError:
            await asyncio.to_thread(self.stories.store_story_ai_failure, story["id"], "bad_response")
            self._state.update(state="ok", last_error="bad_response", current_story_id=None)
            return 0
        await asyncio.to_thread(
            self.stories.store_story_ai, story["id"], texts=written.texts, category=written.category,
            issues=written.issues, model=model, article_count=story["article_count"],
        )
        elapsed = time.perf_counter() - started
        log.info("Story %s summarised in %.1fs", story["id"], elapsed)
        self._state.update(state="ok", current_story_id=None, last_error=None, last_done_at=utc_now_iso())
        return 0
