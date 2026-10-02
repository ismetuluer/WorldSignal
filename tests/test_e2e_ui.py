"""End-to-end: compiled UI + real API server + real collector, driven in a real browser.

Feeds are served from fixture files through a mock HTTP transport, so the test
is deterministic and needs no internet. Requires ``frontend/dist`` (run
``npm run build`` in ``frontend``) and Microsoft Edge or Chrome.
"""

from __future__ import annotations

import hashlib
import json
import re
import socket
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import uvicorn

from conftest import MINI_CATALOG, fixture_bytes, mock_client_factory
from worldsignal.ai.ollama import OllamaClient
from worldsignal.api.app import AppContext, create_app
from worldsignal.ai.worker import AiWorker
from worldsignal.collector.service import Collector
from worldsignal.repo.ai import AiRepository
from worldsignal.fulltext.worker import FullTextWorker
from worldsignal.repo.fulltext import FullTextRepository
from worldsignal.repo.history import HistoryRepository
from worldsignal.backup import BackupManager
from worldsignal.maintenance import Maintenance
from worldsignal.notify import Notifier
from worldsignal.repo.notebook import NotebookRepository
from worldsignal.repo.stories import StoryRepository
from worldsignal.stories.worker import StoryWorker
from worldsignal.paths import ui_dist_dir
from worldsignal.updater import Updater
from worldsignal.home_sync import HomeSync

pytestmark = pytest.mark.e2e

playwright_api = pytest.importorskip("playwright.sync_api")

UI_DIR = ui_dist_dir()
TOKEN = "e2e-token"


FIXTURE_DAY = datetime(2026, 9, 27, tzinfo=UTC)


def dated(name: str) -> bytes:
    """Fixture feed with its dates moved to yesterday, so the test does not depend on the day it runs."""
    day = datetime.now(UTC) - timedelta(days=1)
    text = fixture_bytes(name).decode("utf-8")
    # The weekday is left out: the fixtures call 27 September a Saturday (it is a Sunday) and feedparser ignores it.
    text = re.sub(r"\w{3}, " + FIXTURE_DAY.strftime("%d %b %Y"), day.strftime("%a, %d %b %Y"), text)
    return text.replace(FIXTURE_DAY.strftime("%Y-%m-%dT"), day.strftime("%Y-%m-%dT")).encode("utf-8")


def feed_handler(request: httpx.Request) -> httpx.Response:
    if "alpha" in request.url.host:
        return httpx.Response(200, content=dated("atom_basic.xml"))
    if "beta" in request.url.host:
        return httpx.Response(200, content=dated("rss_turkish.xml"))
    return httpx.Response(404)


def embed_handler(request: httpx.Request) -> httpx.Response:
    """Stands in for Ollama's /api/embed: hashed bag of words, so titles sharing words are similar."""
    def vector(text: str) -> list[float]:
        v = [0.0] * 64
        for word in re.findall(r"\w+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1.0
        return v

    body = json.loads(request.content)
    return httpx.Response(200, json={"embeddings": [vector(t) for t in body["input"]]})


@pytest.fixture
def server(db, data_paths, settings, sources, articles, home) -> Iterator[str]:
    if not (UI_DIR / "index.html").exists():
        pytest.skip("frontend/dist yok; önce 'npm run build' çalıştırın")
    sources.seed_from_catalog(MINI_CATALOG)
    # Keep the test hermetic: point AI at a closed port instead of a real Ollama.
    settings.set("ai.url", "http://127.0.0.1:9")
    settings.set("feed.window_hours", 72)  # fixture reports are dated yesterday
    settings.set("fulltext.enabled", False)  # hermetic: no page downloads, no browser
    settings.set("update.auto_check", False)  # hermetic: never asks GitHub
    collector = Collector(db, sources, articles, client_factory=mock_client_factory(feed_handler))
    ctx = AppContext(
        db=db, paths=data_paths, token=TOKEN, settings=settings, sources=sources, articles=articles,
        collector=collector, ai=AiRepository(db), ai_worker=AiWorker(AiRepository(db), settings),
        stories=StoryRepository(db),
        story_worker=StoryWorker(
            StoryRepository(db), settings,
            client_factory=lambda url: OllamaClient(url, transport=httpx.MockTransport(embed_handler)),
        ),
        notebook=NotebookRepository(db, StoryRepository(db)),
        fulltext=FullTextRepository(db),
        fulltext_worker=FullTextWorker(FullTextRepository(db), settings, data_paths.browser_profile,
                                       find_browser=lambda path: None),
        history=HistoryRepository(db, StoryRepository(db)), maintenance=Maintenance(HistoryRepository(db, StoryRepository(db)), settings),
        backups=BackupManager(db, data_paths.backups, data_paths.root), notifier=Notifier(db, settings),
        updater=Updater(settings, data_paths.root), home=home,
        home_sync=HomeSync(home, articles, StoryRepository(db), settings),
        ui_dir=UI_DIR, run_collector=True,
    )
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(create_app(ctx), log_config=None, lifespan="on"))
    thread = threading.Thread(target=srv.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not srv.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.05)
    # Wait for the first collection cycle to store the fixture articles.
    while collector.status()["last_cycle_at"] is None:
        assert time.monotonic() < deadline, "collector did not run"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def page(server) -> Iterator:
    with playwright_api.sync_playwright() as p:
        browser = None
        for channel in ("msedge", "chrome"):
            try:
                browser = p.chromium.launch(channel=channel, headless=True)
                break
            except Exception:
                continue
        if browser is None:
            pytest.skip("Edge veya Chrome bulunamadı")
        context = browser.new_context(color_scheme="light", viewport={"width": 1280, "height": 860})
        pg = context.new_page()
        errors: list[str] = []
        pg.on("pageerror", lambda exc: errors.append(str(exc)))
        pg.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        yield pg
        browser.close()
        assert errors == [], f"browser errors: {errors}"


def test_full_user_journey(page, server):
    expect = playwright_api.expect
    page.goto(f"{server}/?t={TOKEN}")

    # Token is removed from the address bar.
    expect(page).to_have_url(f"{server}/")

    # The feed opens on stories (each fixture report is its own event here).
    expect(page.get_by_role("heading", name="Akış", exact=True)).to_be_visible()
    story = page.get_by_role("button", name="IRAK'ta seçim sonuçları açıklandı", exact=True)
    expect(story).to_be_visible()
    expect(page.get_by_text("Leaders meet in Brussels")).to_be_visible()
    story.click()
    dialog = page.get_by_role("dialog")
    expect(dialog.get_by_text("Bu hikâyedeki haberler")).to_be_visible()
    expect(dialog.get_by_role("link", name="IRAK'ta seçim sonuçları açıklandı")).to_have_attribute("href", re.compile("^https://"))
    page.keyboard.press("Escape")
    expect(dialog).to_have_count(0)

    # Meeting list: add the story from its card, give a reason, see the output.
    card = page.locator("li.story").filter(has=story)
    card.get_by_role("button", name="Toplantıya ekle").click()
    expect(card.get_by_role("button", name="Toplantıda")).to_be_visible()
    page.get_by_role("button", name="Toplantı", exact=True).click()
    expect(page.get_by_role("heading", name="Toplantı listesi")).to_be_visible()
    reason = page.get_by_role("textbox", name="Kısa not")
    reason.fill("Irak seçimi açılışta")
    with page.expect_response(lambda r: "/api/meeting/" in r.url and r.request.method == "PATCH"):
        reason.press("Enter")
    page.get_by_role("button", name="Çıktı al").click()
    preview = page.frame_locator("iframe.output-preview")
    expect(preview.get_by_text("1. IRAK'ta seçim sonuçları açıklandı")).to_be_visible()
    expect(preview.get_by_text("Irak seçimi açılışta")).to_be_visible()
    page.keyboard.press("Escape")

    # Notebook: today's page lists the proposal; a day note is saved and survives a reload.
    page.get_by_role("button", name="Not Defteri", exact=True).click()
    expect(page.get_by_text("IRAK'ta seçim sonuçları açıklandı")).to_be_visible()
    with page.expect_response(lambda r: "/note" in r.url and r.request.method == "PUT"):
        page.get_by_role("textbox", name="Günün notu").fill("Sabah toplantısı notu")
    page.reload()
    expect(page.get_by_role("textbox", name="Günün notu")).to_have_value("Sabah toplantısı notu")

    # History: a search over every day finds the story (Turkish-insensitive) and opens it with its milestones.
    page.get_by_role("button", name="Geçmiş", exact=True).click()
    expect(page.get_by_role("heading", name="Geçmiş", exact=True)).to_be_visible()
    expect(page.get_by_role("region", name="Geçmiş günler")).to_be_visible()
    page.get_by_role("searchbox").fill("ırak")
    expect(page.get_by_text("“ırak” için tüm günler")).to_be_visible()
    found = page.get_by_role("button", name="IRAK'ta seçim sonuçları açıklandı", exact=True)
    found.click()
    expect(page.get_by_role("dialog").get_by_text("Bu hikâyedeki haberler")).to_be_visible()
    page.keyboard.press("Escape")
    page.get_by_role("button", name="Akış", exact=True).click()

    # Articles view: individual reports from both fixture feeds.
    page.get_by_role("button", name="Haberler", exact=True).click()
    expect(page.get_by_text("IRAK'ta seçim sonuçları açıklandı")).to_be_visible()
    expect(page.get_by_text("Leaders meet in Brussels")).to_be_visible()

    # Turkish-insensitive search: "ırak" finds "IRAK", "istanbul" finds "İstanbul".
    search = page.get_by_role("searchbox")
    page.keyboard.press("/")
    expect(search).to_be_focused()
    search.fill("ırak")
    expect(page.get_by_text("IRAK'ta seçim sonuçları açıklandı")).to_be_visible()
    expect(page.get_by_text("Leaders meet in Brussels")).to_have_count(0)
    search.fill("ISTANBUL")
    expect(page.get_by_text("İstanbul'da şiddetli yağış")).to_be_visible()
    search.fill("bulunmayankelime")
    expect(page.get_by_text("“bulunmayankelime” için sonuç yok")).to_be_visible()
    search.fill("")

    # Region filter.
    page.get_by_role("button", name="Bölge").click()
    page.get_by_role("option", name="Türkiye").click()
    page.keyboard.press("Escape")
    expect(page.get_by_text("Leaders meet in Brussels")).to_have_count(0)
    expect(page.get_by_text("İstanbul'da şiddetli yağış")).to_be_visible()
    page.get_by_role("button", name="Filtreleri temizle").first.click()
    expect(page.get_by_text("Leaders meet in Brussels")).to_be_visible()

    # Sources: catalog groups, unverified section, disable a source -> its articles disappear.
    page.get_by_role("button", name="Kaynaklar", exact=True).click()
    expect(page.get_by_role("heading", name="Kaynaklar", exact=True)).to_be_visible()
    expect(page.get_by_text("Doğrulanmamış kaynaklar")).to_be_visible()
    toggle = page.get_by_role("switch", name="Alpha News kaynağını aç veya kapat")
    expect(toggle).to_have_attribute("aria-checked", "true")
    toggle.click()
    expect(toggle).to_have_attribute("aria-checked", "false")
    page.get_by_role("button", name="Akış", exact=True).click()
    expect(page.get_by_text("IRAK'ta seçim sonuçları açıklandı")).to_be_visible()
    expect(page.get_by_text("Leaders meet in Brussels")).to_have_count(0)

    # Source editor: change reliability and save.
    page.get_by_role("button", name="Kaynaklar", exact=True).click()
    page.get_by_role("button", name="Beta Haber ayarlarını aç").click()
    dialog = page.get_by_role("dialog")
    expect(dialog).to_be_visible()
    dialog.get_by_label("Ad", exact=True).fill("Beta Haber Ağı")
    dialog.get_by_role("button", name="Kaydet").click()
    expect(dialog).to_have_count(0)
    expect(page.get_by_text("Beta Haber Ağı")).to_be_visible()

    # Settings: switch to English and dark theme; both survive a reload.
    page.get_by_role("button", name="Ayarlar", exact=True).click()
    with page.expect_response(lambda r: "/api/settings" in r.url and r.request.method == "PATCH"):
        page.get_by_role("button", name="English").click()
    expect(page.get_by_role("heading", name="Settings", exact=True)).to_be_visible()
    with page.expect_response(lambda r: "/api/settings" in r.url and r.request.method == "PATCH"):
        page.get_by_role("button", name="Dark").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    page.reload()
    expect(page.get_by_role("heading", name="Settings", exact=True)).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")


def test_page_without_token_explains_itself(server):
    with playwright_api.sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        pg = browser.new_page()
        pg.goto(f"{server}/")
        playwright_api.expect(pg.get_by_text("Bu sayfa World Signal penceresinin içinden açılmalı.")).to_be_visible()
        browser.close()
