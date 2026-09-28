from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path

import httpx
import pytest

from worldsignal.country import HomeState
from worldsignal.db import Database
from worldsignal.paths import DataPaths
from worldsignal.repo.articles import ArticleRepository
from worldsignal.repo.settings import SettingsRepository
from worldsignal.repo.sources import SourceRepository

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(config, items):
    if config.getoption("-m"):
        return
    skips = {
        "network": pytest.mark.skip(reason="gerçek ağ testi; çalıştırmak için: pytest -m network"),
        "desktop": pytest.mark.skip(reason="ekranda bildirim gösterir; çalıştırmak için: pytest -m desktop"),
    }
    for item in items:
        for marker, skip in skips.items():
            if marker in item.keywords:
                item.add_marker(skip)


@pytest.fixture
def data_paths(tmp_path: Path) -> DataPaths:
    return DataPaths(tmp_path / "data").ensure()


@pytest.fixture
def db(data_paths: DataPaths) -> Iterator[Database]:
    database = Database(data_paths.database, backup_dir=data_paths.backups)
    database.migrate()
    yield database
    database.close_thread_connection()


@pytest.fixture
def settings(db: Database) -> SettingsRepository:
    return SettingsRepository(db)


@pytest.fixture
def sources(db: Database, settings: SettingsRepository) -> SourceRepository:
    return SourceRepository(db, settings)


@pytest.fixture
def home(settings: SettingsRepository) -> HomeState:
    """The user's country as the app sees it; Windows' region is Türkiye here unless a test says otherwise."""
    return HomeState(settings.get_preferences, "TR")


@pytest.fixture
def articles(db: Database) -> ArticleRepository:
    return ArticleRepository(db)


def fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def mock_client_factory(handler: Callable[[httpx.Request], httpx.Response]) -> Callable[[], httpx.AsyncClient]:
    def factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)

    return factory


MINI_CATALOG = {
    "version": 1,
    "sources": [
        {
            "slug": "alpha", "name": "Alpha News", "homepage": "https://alpha.example", "group": "western",
            "owner": "Alpha Group", "region": "europe", "language": "en", "paywalled": False, "verified": True,
            "feeds": [{"url": "https://alpha.example/rss", "label": "World", "verified": True}],
        },
        {
            "slug": "beta", "name": "Beta Haber", "homepage": "https://beta.example", "group": "turkey",
            "owner": "Beta", "region": "turkey", "language": "tr", "paywalled": False, "verified": True,
            "feeds": [{"url": "https://beta.example/rss", "label": "Dünya", "verified": True}],
        },
        {
            "slug": "gamma", "name": "Gamma Dead", "homepage": "https://gamma.example", "group": "asia",
            "owner": "Gamma", "region": "asia", "language": "en", "paywalled": True, "verified": False,
            "feeds": [{"url": "https://gamma.example/rss", "label": "All", "verified": False}],
        },
    ],
}
