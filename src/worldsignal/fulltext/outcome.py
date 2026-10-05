"""What becomes of a fetched article page: its text, or the reason it has none (one path for the background worker
and the browser extension)."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from ..ai.languages import effective as ai_languages
from ..repo.fulltext import FullTextJob, FullTextRepository
from .extract import extract
from .fetch import Page
from .labels import page_is_exclusive


@dataclass
class Outcome:
    ok: bool
    code: str | None
    status: str  # done | pending | failed | blocked


KEEP_DEBUG_PAGES = 40
MAX_DEBUG_BYTES = 900_000


def save_debug_page(folder: Path, job: FullTextJob, page: Page) -> None:
    """Keep the page as it arrived (local, last ``KEEP_DEBUG_PAGES``): the way to see where a publisher puts a label."""
    folder.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^A-Za-z0-9]+", "-", job.source_name).strip("-") or "source"
    (folder / f"{job.article_id}-{name}.html").write_text(page.html[:MAX_DEBUG_BYTES], encoding="utf-8")
    old = sorted(folder.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)[KEEP_DEBUG_PAGES:]
    for path in old:
        path.unlink(missing_ok=True)


def record_page(repo: FullTextRepository, job: FullTextJob, page: Page, prefs: dict[str, Any], now: datetime,
                on_translation_queued: Callable[[], None], method: str | None = None,
                debug_dir: Path | None = None) -> Outcome:
    """Extract the article text and store it, or store the failure (pausing the site where that is wise)."""
    if debug_dir is not None and prefs.get("debug.save_pages") and page.html:
        try:
            save_debug_page(debug_dir, job, page)
        except OSError:
            pass  # a diagnostic aid must never cost the article its text
    if page.html and page_is_exclusive(page.html):
        repo.mark_exclusive(job.article_id)  # the label is on the page even when only the teaser can be read
    result = extract(page.html, page.final_url, page.status)
    if result.ok and result.text:
        repo.store_text(job.article_id, result.text, method or job.mode, now)
        if prefs.get("fulltext.translate") and prefs.get("ai.enabled", True):
            repo.request_translation(job.article_id, ai_languages(prefs))
            on_translation_queued()
        return Outcome(True, None, "done")
    code = result.error_code or "not_article"
    return Outcome(False, code, repo.store_failure(job, code, now, method))
