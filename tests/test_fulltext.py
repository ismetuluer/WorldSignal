"""Full text: extraction, queue and pacing, the worker (with fake fetchers), translations."""

import asyncio
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from test_stories import SPECS, FakeEmbedOllama, make_worker, seed_articles
from worldsignal.ai import translate
from worldsignal.fulltext.extract import SHORT_TEXT, declared_word_count, extract, judge, tidy
from worldsignal.fulltext.fetch import FetchFailed, Page, profile_in_use
from worldsignal.fulltext.worker import FullTextWorker
from worldsignal.repo.fulltext import MAX_PAUSE, PAUSE_AFTER, BrowserPace, FullTextRepository
from worldsignal.repo.stories import StoryRepository

NOW = datetime.now(UTC).replace(microsecond=0)
ARTICLE_TEXT = " ".join(f"Paragraf {i}: İran'ın Hürmüz Boğazı'nda ele geçirdiği araçla ilgili ayrıntılar açıklandı." for i in range(12))


def html(body: str, title: str = "Haber") -> str:
    return f"<html><head><title>{title}</title></head><body><article><h1>{title}</h1>{body}</article></body></html>"


def article_page() -> str:
    return html("".join(f"<p>{s}.</p>" for s in ARTICLE_TEXT.split(". ")))


def run(coro):
    return asyncio.run(coro)


# -- extraction -------------------------------------------------------------------------------------
def test_extract_article_text():
    r = extract(article_page(), "https://x.example/a")
    assert r.ok and "Hürmüz" in r.text and len(r.text) > 400


def test_extract_rejects_the_free_part_of_a_longer_article():
    words = len(extract(article_page(), "https://x.example/a").text.split())
    meta = '<script type="application/ld+json">{{"@type":"NewsArticle","wordCount":{n}}}</script>'
    # The page declares the article three times longer than what it showed: only the free part.
    cut = article_page().replace("<head>", "<head>" + meta.format(n=words * 3))
    assert extract(cut, "https://x.example/a").error_code == "paywall"
    # Declared length matches (or is short and therefore ignored): the text is accepted.
    whole = article_page().replace("<head>", "<head>" + meta.format(n=words + 10))
    assert extract(whole, "https://x.example/a").ok
    assert declared_word_count(meta.format(n=80)) is None


def test_tidy_keeps_one_paragraph_per_line():
    messy = "Başlık\n            \n    \n   İlk   paragraf burada.\t\n\nİkinci paragraf.  "
    assert tidy(messy) == "Başlık\nİlk paragraf burada.\nİkinci paragraf."


@pytest.mark.parametrize(("page", "status", "code"), [
    (html("<p>Just a moment...</p><p>Checking your browser before accessing.</p>"), 403, "bot_check"),
    (html("<p>Please verify you are a human. Press &amp; Hold.</p>"), 200, "bot_check"),
    (html("<p>Kısa giriş.</p><p>Subscribe to continue reading. Already a subscriber? Log in.</p>"), 200, "paywall"),
    (html("<p>Video</p>"), 200, "not_article"),
    ("<html><body>Not found</body></html>", 404, "http_404"),
    ("<html><body>Forbidden</body></html>", 403, "http_403"),
])
def test_extract_explains_why_there_is_no_text(page, status, code):
    r = extract(page, "https://x.example/a", status)
    assert not r.ok and r.error_code == code


def test_teaser_ending_in_a_subscription_prompt_is_a_paywall():
    teaser = html("".join(f"<p>{s}.</p>" for s in ARTICLE_TEXT.split(". ")[:8]) + "<p>Subscribe to continue reading this article.</p>")
    assert extract(teaser, "https://x.example/a").error_code == "paywall"


def test_profile_in_use(tmp_path):
    assert not profile_in_use(tmp_path)
    (tmp_path / "lockfile").write_text("")
    assert not profile_in_use(tmp_path)  # a leftover lock file that nobody holds


# -- queue ------------------------------------------------------------------------------------------
@pytest.fixture
def world(db, sources, articles, settings):
    ids = seed_articles(db, sources, articles, SPECS)
    run(make_worker(db, settings, FakeEmbedOllama()).step())
    return {"ids": ids, "repo": FullTextRepository(db), "stories": StoryRepository(db), "db": db, "settings": settings,
            "sources": sources}


def source_of(world, key):
    return world["db"].conn.execute("SELECT source_id FROM articles WHERE id = ?", (world["ids"][key],)).fetchone()[0]


def test_paid_sources_start_off_and_free_ones_download(world):
    modes = {s["slug"]: s["fulltext_mode"] for s in world["sources"].list_sources()}
    assert modes["alpha"] == "http"
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    assert {s["slug"]: s["fulltext_mode"] for s in world["sources"].list_sources()}["alpha"] == "browser"


def test_priority_user_over_notebook_over_auto(world):
    repo, ids = world["repo"], world["ids"]
    repo.enqueue([ids["a1"], ids["b1"]], "auto")
    repo.enqueue([ids["g1"]], "notebook")
    assert repo.next_job(NOW, 10).article_id == ids["g1"]
    assert repo.request(ids["a2"]) == "pending"
    job = repo.next_job(NOW, 10)
    assert job.article_id == ids["a2"] and job.reason == "user"
    repo.enqueue([ids["a1"]], "notebook")  # a higher reason upgrades a pending row
    assert repo.get(ids["a1"])["reason"] == "notebook"
    repo.enqueue([ids["a1"]], "auto")  # ... a lower one does not downgrade it
    assert repo.get(ids["a1"])["reason"] == "notebook"
    with pytest.raises(KeyError):
        repo.request(999999)


def test_hourly_limit_per_site_and_pauses(world):
    repo, ids = world["repo"], world["ids"]
    alpha = [ids["a1"], ids["a2"], ids["a3"]]
    repo.enqueue(alpha, "auto")
    for aid in alpha[:2]:
        repo.mark_attempt(aid, NOW)
    job = repo.next_job(NOW, 2)
    assert job is None  # alpha already had 2 pages this hour
    assert repo.next_job(NOW + timedelta(minutes=61), 2) is not None

    job = repo.next_job(NOW, 5)
    assert repo.store_failure(job, "bot_check", NOW) == "blocked"
    assert repo.next_job(NOW, 5) is None  # the whole site is paused
    assert [p["name"] for p in repo.paused_sources(NOW)] == [job.source_name]
    assert repo.next_job(NOW + timedelta(hours=13), 5) is not None
    repo.resume_source(job.source_id)
    assert repo.paused_sources(NOW) == []


def test_repeated_refusals_lengthen_the_pause(world):
    repo, ids = world["repo"], world["ids"]
    alpha = [ids["a1"], ids["a2"], ids["a3"]]
    repo.enqueue(alpha, "auto")
    # Every refusal pauses the site; the same refusal again within three days doubles the pause.
    job = repo.next_job(NOW, 10)
    repo.mark_attempt(job.article_id, NOW)  # the worker marks every attempt before it reads the page
    assert repo.store_failure(job, "http_403", NOW) == "failed"
    assert repo.paused_sources(NOW + timedelta(hours=5))
    assert not repo.paused_sources(NOW + timedelta(hours=7))  # 6 hours the first time
    later = NOW + timedelta(days=1)
    job = repo.next_job(later, 10)
    repo.mark_attempt(job.article_id, later)
    repo.store_failure(job, "http_403", later)
    assert repo.paused_sources(later + timedelta(hours=11))
    assert not repo.paused_sources(later + timedelta(hours=13))  # 12 hours the second time
    # A login request (401) pauses the site too, and the pause never exceeds three days.
    assert PAUSE_AFTER["http_401"] > timedelta(0) and MAX_PAUSE == timedelta(hours=72)


def pace(**kw):
    values = {"gap": timedelta(minutes=20), "user_gap": timedelta(minutes=3), "per_day": 15,
              "day_start": NOW - timedelta(hours=10), "resting": False}
    return BrowserPace(**{**values, **kw})


def test_subscription_sites_are_read_at_a_persons_pace(world):
    repo, ids = world["repo"], world["ids"]
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    alpha = [ids["a1"], ids["a2"], ids["a3"]]
    repo.enqueue(alpha, "auto")
    assert repo.next_job(NOW, 10, pace()) is not None
    repo.mark_attempt(ids["a1"], NOW)
    # Not twice within the gap, even though the hourly limit would allow it …
    assert repo.next_job(NOW + timedelta(minutes=19), 10, pace()) is None
    assert repo.next_job(NOW + timedelta(minutes=19), 10) is not None  # (the old rule alone)
    assert repo.next_job(NOW + timedelta(minutes=21), 10, pace()) is not None
    # … a page the user asked for only waits the short gap …
    repo.request(ids["a2"])
    assert repo.next_job(NOW + timedelta(minutes=2), 10, pace()) is None
    assert repo.next_job(NOW + timedelta(minutes=4), 10, pace()).article_id == ids["a2"]
    # … and the user's requests ignore the night and the daily limit; automatic ones wait.
    later = NOW + timedelta(minutes=30)
    assert repo.next_job(later, 10, pace(resting=True)).reason == "user"
    repo.mark_attempt(ids["a2"], NOW)
    repo.store_text(ids["a2"], "text", "browser", NOW)
    assert repo.next_job(later, 10, pace(resting=True)) is None
    assert repo.next_job(later, 10, pace(per_day=3)).article_id == ids["a3"]
    repo.mark_attempt(ids["a3"], NOW - timedelta(minutes=40))
    assert repo.next_job(later, 10, pace(per_day=3)) is None  # three pages of alpha today already
    assert repo.next_job(later, 10, pace(per_day=3, day_start=NOW - timedelta(minutes=5))) is not None


def test_the_persons_pace_is_only_for_sites_read_in_the_browser(world):
    repo, ids = world["repo"], world["ids"]
    repo.enqueue([ids["a1"], ids["a2"]], "auto")  # alpha downloads over plain HTTP
    repo.mark_attempt(ids["a1"], NOW)
    assert repo.next_job(NOW + timedelta(minutes=1), 10, pace(resting=True)) is not None


def test_temporary_errors_retry_then_fail(world):
    repo, ids = world["repo"], world["ids"]
    repo.enqueue([ids["b2"]], "auto")
    for expected in ("pending", "pending", "failed"):
        job = repo.next_job(NOW, 10)
        assert repo.store_failure(job, "timeout", NOW) == expected


def test_switched_off_sources_are_skipped_unless_the_user_asks(world):
    repo, ids = world["repo"], world["ids"]
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "off", "paywalled": True})
    repo.enqueue([ids["a1"]], "auto")
    assert repo.next_job(NOW, 10) is None
    repo.request(ids["a1"])
    job = repo.next_job(NOW, 10)
    assert job.article_id == ids["a1"] and job.mode == "browser"  # paid source: the browser


def test_auto_candidates_respect_score_and_per_story_limit(world):
    repo, stories = world["repo"], world["stories"]
    hormuz = stories.story_of(world["ids"]["a1"])
    with world["db"].transaction() as c:
        c.execute("UPDATE stories SET score = 80 WHERE id = ?", (hormuz,))
    picks = repo.auto_candidates("2000-01-01T00:00:00Z", 60, 2, "2026-09-27")
    assert len(picks["auto"]) == 2 and picks["notebook"] == []
    repo.enqueue(picks["auto"], "auto")
    assert repo.auto_candidates("2000-01-01T00:00:00Z", 60, 2, "2026-09-27")["auto"] == []  # limit reached
    assert repo.auto_candidates("2000-01-01T00:00:00Z", 90, 2, "2026-09-27")["auto"] == []


# -- worker ------------------------------------------------------------------------------------------
def make_ft_worker(world, tmp_path, *, http=None):
    async def default_http(url):
        return Page(200, article_page(), url)

    return FullTextWorker(
        world["repo"], world["settings"], http_fetch=http or default_http, clock=lambda: NOW, today=lambda: "2026-09-27",
    )


def test_worker_fetches_over_http_and_the_ai_uses_the_full_text(world, tmp_path):
    from worldsignal.repo.ai import AiRepository

    repo, ids = world["repo"], world["ids"]
    repo.request(ids["a2"])
    worker = make_ft_worker(world, tmp_path)
    delay = run(worker.step())
    assert 6 <= delay <= 15  # human pace for plain downloads
    ft = repo.get(ids["a2"])
    assert ft["status"] == "done" and ft["method"] == "http" and "Hürmüz" in ft["text"]

    ai = AiRepository(world["db"])
    ai.request(ids["a2"])
    job = ai.next_job()
    assert job.article_id == ids["a2"] and job.summary == ft["text"]  # the model reads the full text


def test_feed_articles_carry_the_state_of_their_full_text(world, tmp_path):
    from worldsignal.repo.articles import ArticleFilter, ArticleRepository

    repo, ids = world["repo"], world["ids"]
    articles = ArticleRepository(world["db"])
    state = lambda: {a["id"]: a["fulltext_status"] for a in articles.list(ArticleFilter(limit=50))}  # noqa: E731
    assert state()[ids["a2"]] is None  # never asked for
    repo.request(ids["a2"])
    assert state()[ids["a2"]] == "pending"
    run(make_ft_worker(world, tmp_path).step())
    listed = {a["id"]: a for a in articles.list(ArticleFilter(limit=50))}
    assert listed[ids["a2"]]["fulltext_status"] == "done" and listed[ids["a2"]]["fulltext_chars"] > 100


def test_the_full_text_is_translated_too_only_when_asked_for(world, tmp_path):
    repo, ids, settings = world["repo"], world["ids"], world["settings"]
    woken = []
    repo.request(ids["a1"])
    worker = make_ft_worker(world, tmp_path)
    worker.on_translation_queued = lambda: woken.append(1)
    run(worker.step())
    assert repo.get(ids["a1"])["status"] == "done" and repo.get(ids["a1"])["translate_status"] is None  # default: summary only
    assert woken == []

    settings.set("fulltext.translate", True)
    repo.request(ids["a2"])
    run(worker.step())
    assert repo.get(ids["a2"])["translate_status"] == "pending" and woken == [1]  # queued for the AI worker
    assert repo.next_translation()["article_id"] == ids["a2"]

    settings.set_many({"fulltext.translate": True, "ai.enabled": False})
    repo.request(ids["a3"])
    run(worker.step())
    assert repo.get(ids["a3"])["translate_status"] is None  # without the AI nothing is queued


def test_subscription_sites_rest_at_night_unless_the_user_asks(world, tmp_path):
    repo, ids = world["repo"], world["ids"]
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    repo.enqueue([ids["a1"]], "auto")
    worker = make_ft_worker(world, tmp_path)
    worker.local_zone = timezone(timedelta(hours=3))
    worker.clock = lambda: datetime(2026, 9, 28, 0, 30, tzinfo=UTC)  # 03:30 local
    assert worker.browser_pace(world["settings"].get_preferences(), worker.clock()).resting
    run(worker.step())
    assert worker.status()["state"] == "idle"

    world["settings"].set("fulltext.browser_night_rest", False)
    assert not worker.browser_pace(world["settings"].get_preferences(), worker.clock()).resting
    worker.clock = lambda: datetime(2026, 9, 28, 9, 0, tzinfo=UTC)  # 12:00 local
    pace = worker.browser_pace(world["settings"].get_preferences(), worker.clock())
    assert pace.day_start == datetime(2026, 9, 27, 21, 0, tzinfo=UTC) and pace.gap == timedelta(minutes=20)


def test_old_google_news_links_are_not_opened(world, tmp_path):
    repo, ids = world["repo"], world["ids"]
    with world["db"].transaction() as c:
        c.execute("UPDATE articles SET url = 'https://news.google.com/rss/articles/CBMiabc?oc=5' WHERE id = ?", (ids["a2"],))
    repo.request(ids["a2"])
    opened: list[str] = []

    async def http(url):
        opened.append(url)
        return Page(200, article_page(), url)

    run(make_ft_worker(world, tmp_path, http=http).step())
    ft = repo.get(ids["a2"])
    assert opened == [] and ft["status"] == "failed" and ft["error_code"] == "aggregator_link"


def test_the_worker_never_reads_a_subscription_site_itself(world, tmp_path):
    """Sources read "in the browser" belong to the extension (fulltext/bridge.py): the worker leaves them in the queue."""
    repo, ids = world["repo"], world["ids"]
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    repo.request(ids["a1"])
    opened: list[str] = []

    async def http(url):
        opened.append(url)
        return Page(200, article_page(), url)

    run(make_ft_worker(world, tmp_path, http=http).step())
    assert opened == [] and repo.get(ids["a1"])["status"] == "pending"


def test_worker_records_blocks_and_pauses_the_site(world, tmp_path):
    repo, ids = world["repo"], world["ids"]

    async def bot_page(url):
        return Page(403, html("<p>Just a moment...</p><p>Checking your browser</p>"), url)

    repo.request(ids["b1"])
    worker = make_ft_worker(world, tmp_path, http=bot_page)
    run(worker.step())
    assert repo.get(ids["b1"])["status"] == "blocked" and repo.get(ids["b1"])["error_code"] == "bot_check"
    assert worker.status()["paused_sources"]


def test_worker_network_error_is_retried(world, tmp_path):
    repo, ids = world["repo"], world["ids"]

    async def down(url):
        raise FetchFailed("network")

    repo.request(ids["b2"])
    run(make_ft_worker(world, tmp_path, http=down).step())
    assert repo.get(ids["b2"])["status"] == "pending" and repo.get(ids["b2"])["attempts"] == 1


def test_worker_disabled(world, tmp_path):
    world["settings"].set("fulltext.enabled", False)
    worker = make_ft_worker(world, tmp_path)
    run(worker.step())
    assert worker.status()["state"] == "disabled"


# -- translations -----------------------------------------------------------------------------------
def test_chunks_follow_paragraphs_and_split_long_ones():
    text = "Kısa paragraf.\n" + ("Uzun cümle burada. " * 200) + "\nSon paragraf."
    parts = translate.chunks(text, size=500)
    assert all(len(p) <= 520 for p in parts)
    assert parts[0].startswith("Kısa paragraf.") and parts[-1].endswith("Son paragraf.")
    assert "".join(parts).count("Uzun cümle burada.") == 200
    assert translate.targets(["tr", "en"], "tr") == ["en"] and translate.targets(["tr", "en"], "ar") == ["tr", "en"]
    assert translate.targets(["pt", "ar"], "ar") == ["pt"]


def test_translation_job_on_request(world, tmp_path):
    import json

    import httpx

    from worldsignal.ai.ollama import OllamaClient
    from worldsignal.ai.worker import AiWorker
    from worldsignal.repo.ai import AiRepository

    repo, ids = world["repo"], world["ids"]
    with pytest.raises(LookupError):
        repo.request_translation(ids["a1"])  # no full text yet
    repo.request(ids["a1"])
    run(make_ft_worker(world, tmp_path).step())
    assert repo.request_translation(ids["a1"]) == "pending"

    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/ps":
            return httpx.Response(200, json={"models": []})
        body = json.loads(request.content)
        seen.append(body["messages"][0]["content"])
        return httpx.Response(200, json={"message": {"content": json.dumps({"translation": "Çeviri parçası."})}})

    world["settings"].set_many({"ai.model": "m", "ai.enabled": True})
    worker = AiWorker(AiRepository(world["db"]), world["settings"],
                      client_factory=lambda url: OllamaClient(url, transport=httpx.MockTransport(handler)),
                      fulltext=repo)
    run(worker.step())
    ft = repo.get(ids["a1"])
    assert ft["translate_status"] == "done" and "Çeviri parçası." in ft["translations"]["tr"]
    assert "en" not in ft["translations"]  # the source (alpha) is English: nothing to translate into English
    assert all("Turkish" in s for s in seen)
    assert repo.request_translation(ids["a1"], ["tr", "en"]) == "done"

    # A language added later: only it is translated, the Turkish text is kept.
    world["settings"].set("ai.languages", ["tr", "pt"])
    assert repo.request_translation(ids["a1"], ["tr", "pt"]) == "pending"
    seen.clear()
    run(worker.step())
    ft = repo.get(ids["a1"])
    assert set(ft["translations"]) == {"tr", "pt"} and seen and all("Portuguese" in s for s in seen)


def test_a_finished_summary_is_redone_when_the_full_text_arrives(world, tmp_path):
    from worldsignal.repo.ai import AiRepository

    ai, ids = AiRepository(world["db"]), world["ids"]
    with world["db"].transaction() as c:
        c.execute(
            """INSERT INTO article_ai (article_id, status, queued_at, completed_at, texts, attempts)
               VALUES (?, 'done', ?, ?, '{"tr": {"title": "Eski", "summary": ""}, "en": {"title": "Old", "summary": ""}}', 1)""",
            (ids["b1"], "2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z"),
        )
    assert ai.next_job("2000-01-01T00:00:00Z") is None
    world["repo"].request(ids["b1"])
    run(make_ft_worker(world, tmp_path).step())
    job = ai.next_job("2000-01-01T00:00:00Z")
    assert job is not None and job.article_id == ids["b1"] and job.upgrade and "Hürmüz" in job.summary


# -- stricter rules found on real pages (2026-09-28) ---------------------------------------------------
FT_TEASER = (
    "'Xi got face': China relishes equal treatment from Trump\nSubscribe to unlock this article\n"
    "Save 40% on Standard Digital\nwas TL14388 now TL8625 for your first year.\n"
    "Save now on essential digital access to trusted FT journalism on any device. Savings based on annualised "
    "monthly price.\nExplore more offers.\nExplore our full range of subscriptions.\nFor individuals\n"
    "Discover all the plans currently available in your country"
)


def test_a_subscription_offer_is_not_a_full_text():
    """The Financial Times page of a signed-out profile: 419 characters of offer, no article."""
    assert len(FT_TEASER) >= 400
    assert judge(FT_TEASER).error_code == "paywall"
    page = html("".join(f"<p>{line}</p>" for line in FT_TEASER.split("\n")))
    assert extract(page, "https://www.ft.com/content/x").error_code == "paywall"


def test_page_furniture_is_removed_from_the_text():
    consent = ("To display this content from YouTube, you must enable advertisement tracking and audience measurement.\n"
               "One of your browser extensions seems to be blocking the video player from loading.\n")
    independent = ("Become an Independent member to bookmark this article\n"
                   "Want to bookmark your favourite articles and stories to read or reference later?\n")
    for noise in (consent, independent, "Abone ol\n"):
        verdict = judge(noise + ARTICLE_TEXT)
        assert verdict.ok and verdict.text.startswith("Paragraf 0") and "YouTube" not in verdict.text
    assert judge(consent + "Short caption.").error_code == "not_article"
    # A long article that only mentions a subscription in passing stays an article.
    long_text = ARTICLE_TEXT * 3 + "\nReaders who subscribe to unlock extra features can do so. " + ARTICLE_TEXT
    assert len(long_text) > SHORT_TEXT and judge(long_text).ok


def test_stored_texts_are_rechecked_with_the_current_rules(world):
    repo, ids, db = world["repo"], world["ids"], world["db"]
    now_iso = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    with db.transaction() as c:
        for key, text in (("a1", FT_TEASER), ("a2", "Abone ol\n" + ARTICLE_TEXT), ("b1", ARTICLE_TEXT)):
            c.execute("""INSERT INTO article_fulltext (article_id, status, text, chars, queued_at, fetched_at)
                         VALUES (?, 'done', ?, ?, ?, ?)""", (ids[key], text, len(text), now_iso, now_iso))
        c.execute("""INSERT INTO article_ai (article_id, status, texts, queued_at)
                     VALUES (?, 'done', '{"tr": {"title": "Başlık", "summary": ""}}', ?)""",
                  (ids["a1"], now_iso))
    assert repo.recheck(judge, SHORT_TEXT + 500) == {"rejected": 1, "cleaned": 1}
    teaser = repo.get(ids["a1"])
    assert teaser["status"] == "failed" and teaser["error_code"] == "paywall" and teaser["text"] is None
    ai = db.conn.execute("SELECT status, requested_by_user FROM article_ai WHERE article_id = ?", (ids["a1"],)).fetchone()
    assert tuple(ai) == ("pending", 1)  # its summary is redone from the feed summary
    assert repo.get(ids["a2"])["text"].startswith("Paragraf 0")
    assert repo.get(ids["b1"])["text"] == ARTICLE_TEXT
    assert repo.recheck(judge, SHORT_TEXT + 500) == {"rejected": 0, "cleaned": 0}  # nothing left to change


def test_a_french_teaser_that_ends_in_the_paywall_is_refused():
    """Le Monde, signed out: the first paragraphs, then 'Il vous reste 81.45% ... réservée aux abonnés.'"""
    teaser = ARTICLE_TEXT + "\nIl vous reste 81.45% de cet article à lire. La suite est réservée aux abonnés."
    assert judge(teaser).error_code == "paywall"
    for ending in ("Suscríbete para seguir leyendo", "Weiterlesen mit SPIEGEL+", "Abbonati per continuare a leggere"):
        assert judge(ARTICLE_TEXT + "\n" + ending).error_code == "paywall", ending
