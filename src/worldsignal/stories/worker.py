"""Background story builder: embeds new articles, clusters them into stories, scores stories.

Runs on the CPU (the embedding model is loaded with ``num_gpu: 0``) so it never
competes with the chat model for graphics memory.

Clustering is online and deterministic: articles are processed in time order
and compared with the already-clustered articles of the last ``WINDOW_HOURS``.
An article joins a story when (1) some member is at least ``threshold`` similar
(a close report of the same event) and (2) its *average* similarity to the
story's members reaches ``cohesion``. The second condition stops chaining: with
(1) alone, A joins because it resembles B, C because it resembles A, and
unrelated events end up in one story (measured in docs/BIRLESTIRME_KARSILASTIRMA.md).
Otherwise the article starts a new story. Because a story keeps absorbing new
reports while the event continues, a multi-day event stays one story (the "story chain").
Articles placed by the user (detach/merge) are never moved automatically.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from ..ai.ollama import OllamaClient, OllamaError
from ..db import utc_now_iso
from ..repo.settings import SettingsRepository
from ..repo.stories import StoryRepository
from .embedding import embed_text
from .score import Interest

log = logging.getLogger(__name__)

WINDOW_HOURS = 72
BATCH = 32
IDLE_SECONDS = 15
PAUSED_SECONDS = 30
RESCORE_EVERY = timedelta(minutes=5)


class StoryWorker:
    def __init__(
        self,
        stories: StoryRepository,
        settings: SettingsRepository,
        client_factory: Callable[[str], OllamaClient] = OllamaClient,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.stories = stories
        self.settings = settings
        self.client_factory = client_factory
        self.clock = clock
        self._wake: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._last_rescore: datetime | None = None
        self._state: dict[str, Any] = {"running": False, "state": "starting", "model": None, "last_error": None}

    def status(self) -> dict[str, Any]:
        return {**self._state, **self.stories.counts()}

    def request_rescore(self) -> None:
        """Settings changed: rescore every active story on the next step. Thread-safe."""
        self._last_rescore = None
        self.wake()

    def wake(self) -> None:
        if self._loop is not None and self._wake is not None:
            self._loop.call_soon_threadsafe(self._wake.set)

    async def run_forever(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._wake = asyncio.Event()
        self._state["running"] = True
        log.info("Story worker started")
        try:
            while True:
                # Cleared before the step, not after: a wake() that arrives during the step is kept.
                self._wake.clear()
                try:
                    delay = await self.step()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("Story worker step failed")
                    delay = PAUSED_SECONDS
                if delay:
                    try:
                        await asyncio.wait_for(self._wake.wait(), timeout=delay)
                    except TimeoutError:
                        pass
        finally:
            self._state["running"] = False

    # -- one step ---------------------------------------------------------------------------------
    async def step(self) -> float:
        prefs = await asyncio.to_thread(self.settings.get_preferences)
        model = (prefs.get("stories.embed_model") or "").strip()
        self._state["model"] = model or None
        if not model:
            self._state["state"] = "no_model"
            return PAUSED_SECONDS
        now = self.clock()
        since = utc_now_iso(now - timedelta(hours=WINDOW_HOURS))

        in_use = await asyncio.to_thread(self.stories.embedding_model_in_use)
        if in_use and in_use != model:
            dropped = await asyncio.to_thread(self.stories.drop_embeddings_of_other_models, model)
            log.info("Embedding model changed to %s; %d old vectors dropped", model, dropped)

        batch = await asyncio.to_thread(self.stories.articles_needing_embedding, since, BATCH)
        if batch:
            texts = [embed_text(model, a["title"], a["summary"], with_summary=bool(prefs.get("stories.embed_summary")))
                     for a in batch]
            try:
                vectors = await self.client_factory(prefs["ai.url"]).embed(model, texts, cpu_only=True)
            except OllamaError as exc:
                self._state.update(state=exc.code, last_error=exc.code)
                log.warning("Embedding paused: %s", exc)
                return PAUSED_SECONDS
            await asyncio.to_thread(self.stories.store_embeddings, [(a["id"], model, v) for a, v in zip(batch, vectors, strict=True)])

        touched = await asyncio.to_thread(
            self.cluster_pending, model, since, float(prefs["stories.threshold"]), float(prefs["stories.cohesion"])
        )
        rescore_all = self._last_rescore is None or now - self._last_rescore >= RESCORE_EVERY
        if rescore_all:
            touched |= set(await asyncio.to_thread(self.stories.active_story_ids, since))
            self._last_rescore = now
        if touched:
            await asyncio.to_thread(self.stories.recompute, sorted(touched), now, weights_from(prefs), interest_from(prefs))
        self._state.update(state="ok" if batch else "idle", last_error=None)
        return 0 if len(batch) == BATCH else IDLE_SECONDS

    def cluster_pending(self, model: str, since_iso: str, threshold: float, cohesion: float) -> set[int]:
        """Assign every embedded but unclustered article (time order). Returns touched story ids."""
        ids, story_ids, _, matrix = self.stories.recent_vectors(since_iso, model)
        if not ids:
            return set()
        touched: set[int] = set()
        story_arr = np.array([s if s is not None else -1 for s in story_ids], dtype=np.int64)
        for i in np.flatnonzero(story_arr < 0):  # already in time order
            clustered = story_arr >= 0  # this excludes i itself
            best_story, best_sim = choose_story(matrix[clustered] @ matrix[i], story_arr[clustered], threshold, cohesion)
            sid = self.stories.assign(ids[i], best_story, similarity=best_sim)
            story_arr[i] = sid
            touched.add(sid)
        return touched


def choose_story(sims: np.ndarray, stories: np.ndarray, threshold: float, cohesion: float) -> tuple[int | None, float | None]:
    """The story a new article joins, given its similarity to each clustered article and their stories.

    Eligible stories have a member at least ``threshold`` similar and an average similarity of at least
    ``cohesion``; among them the one with the closest member wins. Returns (story id, closest similarity)
    or (None, None) for "start a new story".
    """
    if len(sims) == 0:
        return None, None
    story_ids, inverse = np.unique(stories, return_inverse=True)
    closest = np.full(len(story_ids), -2.0)
    np.maximum.at(closest, inverse, sims)
    mean = np.bincount(inverse, weights=sims) / np.bincount(inverse)
    eligible = np.flatnonzero((closest >= threshold) & (mean >= cohesion))
    if len(eligible) == 0:
        return None, None
    best = eligible[int(closest[eligible].argmax())]
    return int(story_ids[best]), float(closest[best])


def weights_from(prefs: dict[str, Any]) -> dict[str, float]:
    return {k: float(prefs.get(f"score.w_{k}", 0)) for k in ("sources", "freshness", "turkey", "interest")}


def interest_from(prefs: dict[str, Any]) -> Interest:
    return Interest(
        keywords=list(prefs.get("interest.keywords") or []),
        categories=list(prefs.get("interest.categories") or []),
        regions=list(prefs.get("interest.regions") or []),
    )
