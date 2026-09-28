"""Wiring: build the database, repositories, collector and API context."""

from __future__ import annotations

import logging
from pathlib import Path

from .ai.worker import AiWorker
from .api.app import AppContext
from .catalog import load_catalog
from .collector.service import Collector
from .db import Database
from .paths import DataPaths
from .repo.ai import AiRepository
from .repo.articles import ArticleRepository
from .fulltext.worker import FullTextWorker
from .repo.fulltext import FullTextRepository
from .repo.history import HistoryRepository
from .backup import BackupManager
from .maintenance import Maintenance
from .notify import Notifier
from .repo.notebook import NotebookRepository
from .repo.settings import SettingsRepository
from .repo.sources import SourceRepository
from .repo.stories import StoryRepository
from .stories.worker import StoryWorker
from .updater import Updater

log = logging.getLogger(__name__)


def build_context(paths: DataPaths, token: str, ui_dir: Path | None, run_collector: bool = True) -> AppContext:
    db = Database(paths.database, backup_dir=paths.backups)
    version = db.migrate()
    log.info("Database ready at %s (schema v%d)", paths.database, version)
    settings = SettingsRepository(db)
    sources = SourceRepository(db, settings)
    sources.seed_from_catalog(load_catalog())
    articles = ArticleRepository(db)
    collector = Collector(db, sources, articles)
    ai = AiRepository(db)
    stories = StoryRepository(db)
    fulltext = FullTextRepository(db)
    history = HistoryRepository(db, stories)
    backups = BackupManager(db, paths.backups, paths.root)
    return AppContext(
        db=db, paths=paths, token=token, settings=settings, sources=sources, articles=articles,
        collector=collector, ai=ai, ai_worker=AiWorker(ai, settings, stories=stories, fulltext=fulltext),
        stories=stories, story_worker=StoryWorker(stories, settings), notebook=NotebookRepository(db, stories),
        fulltext=fulltext, fulltext_worker=FullTextWorker(fulltext, settings, paths.browser_profile),
        history=history, maintenance=Maintenance(history, settings, backups, fulltext), backups=backups,
        notifier=Notifier(db, settings),
        updater=Updater(settings, paths.root),
        ui_dir=ui_dir, run_collector=run_collector,
    )
