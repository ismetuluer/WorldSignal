"""record_page: the single path from a fetched page to the database (worker and extension)."""

from datetime import UTC, datetime

from test_fulltext import article_page, html, world  # noqa: F401  (world is a fixture)
from worldsignal.fulltext.fetch import Page
from worldsignal.fulltext.outcome import record_page

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def job_for(world, key):
    repo = world["repo"]
    repo.request(world["ids"][key])
    return repo.next_job(NOW, 99)


def test_text_is_stored_and_translation_queued_when_asked(world):
    world["settings"].set("fulltext.translate", True)
    job = job_for(world, "a2")
    woken = []
    out = record_page(world["repo"], job, Page(200, article_page(), job.url), world["settings"].get_preferences(), NOW,
                      lambda: woken.append(1), method="extension")
    ft = world["repo"].get(job.article_id)
    assert out.ok and out.status == "done" and ft["method"] == "extension" and "Hürmüz" in ft["text"]
    assert ft["translate_status"] == "pending" and woken == [1]


def test_paywall_page_is_a_failure_not_text(world):
    job = job_for(world, "a2")
    barrier = html("<p>Kısa giriş.</p><p>Subscribe to continue reading. Already a subscriber? Log in.</p>")
    out = record_page(world["repo"], job, Page(200, barrier, job.url), {}, NOW, lambda: None)
    ft = world["repo"].get(job.article_id)
    assert not out.ok and out.code == "paywall" and ft["status"] == "failed" and ft["text"] is None


def test_bot_check_blocks_and_pauses_the_site(world):
    job = job_for(world, "a2")
    check = html("<p>Just a moment...</p><p>Checking your browser before accessing.</p>")
    out = record_page(world["repo"], job, Page(403, check, job.url), {}, NOW, lambda: None)
    assert out.status == "blocked" and world["repo"].paused_sources(NOW)
