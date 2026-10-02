"""What becomes of a fetched article page: its text, or the reason it has none (one path for the background worker
and the browser extension)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..ai.languages import effective as ai_languages
from ..repo.fulltext import FullTextJob, FullTextRepository
from .extract import extract
from .fetch import Page


@dataclass
class Outcome:
    ok: bool
    code: str | None
    status: str  # done | pending | failed | blocked


def record_page(repo: FullTextRepository, job: FullTextJob, page: Page, prefs: dict[str, Any], now: datetime,
                on_translation_queued: Callable[[], None], method: str | None = None) -> Outcome:
    """Extract the article text and store it, or store the failure (pausing the site where that is wise)."""
    result = extract(page.html, page.final_url, page.status)
    if result.ok and result.text:
        repo.store_text(job.article_id, result.text, method or job.mode, now)
        if prefs.get("fulltext.translate") and prefs.get("ai.enabled", True):
            repo.request_translation(job.article_id, ai_languages(prefs))
            on_translation_queued()
        return Outcome(True, None, "done")
    code = result.error_code or "not_article"
    return Outcome(False, code, repo.store_failure(job, code, now, method))
