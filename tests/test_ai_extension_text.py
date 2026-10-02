"""A report the extension read in the user's own browser is summarised from its full text before the rest of the queue."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from test_ai import FakeOllama, add_articles, make_worker, run  # noqa: F401  (shared helpers)
from worldsignal.repo.ai import AiRepository

SINCE = "2000-01-01T00:00:00Z"


def store_text(db, article_id, method="extension", text="Tam metin burada.", fetched_at=None):
    fetched = fetched_at or datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    with db.transaction() as c:
        c.execute(
            """INSERT OR REPLACE INTO article_fulltext (article_id, status, method, text, chars, queued_at, fetched_at)
               VALUES (?, 'done', ?, ?, ?, ?, ?)""",
            (article_id, method, text, len(text), fetched, fetched),
        )


def test_an_extension_text_goes_before_the_queue(db, sources, articles):
    ids = add_articles(db, sources, articles, n=3)
    repo = AiRepository(db)
    repo.enqueue_recent(SINCE)
    oldest = ids[-1]  # the queue would take the newest first
    store_text(db, oldest)
    job = repo.next_job(SINCE)
    assert job.article_id == oldest and job.summary == "Tam metin burada."
    assert job.requested and not job.upgrade  # written in full, never in a headline-only batch


def test_other_methods_keep_their_place_in_the_queue(db, sources, articles):
    ids = add_articles(db, sources, articles, n=3)
    repo = AiRepository(db)
    repo.enqueue_recent(SINCE)
    store_text(db, ids[-1], method="http")
    assert repo.next_job(SINCE).article_id == ids[0]


def test_a_text_arriving_after_the_summary_redoes_it_and_a_failed_redo_is_not_repeated_forever(
        db, sources, articles, settings):
    ids = add_articles(db, sources, articles, n=1)
    run(make_worker(db, settings, FakeOllama()).step())
    repo = AiRepository(db)
    assert repo.get(ids[0])["status"] == "done"
    assert repo._read_by_extension(SINCE, ("tr",)) is None
    store_text(db, ids[0], fetched_at=(datetime.now(UTC) + timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
    job = repo.next_job(SINCE)
    assert job.upgrade and job.article_id == ids[0]

    broken = FakeOllama(answer="not json")
    for _ in range(4):
        run(make_worker(db, settings, broken).step())
    row = repo.get(ids[0])
    assert row["status"] == "done" and row["texts"]["tr"]["title"]  # the finished text stays
    assert repo._read_by_extension(SINCE, ("tr",)) is None  # given up after MAX_ATTEMPTS


def test_worker_summarises_an_unqueued_extension_text_without_a_row(db, sources, articles, settings):
    ids = add_articles(db, sources, articles, n=1)
    store_text(db, ids[0])
    assert AiRepository(db).get(ids[0]) is None
    run(make_worker(db, settings, FakeOllama()).step())
    row = AiRepository(db).get(ids[0])
    assert row["status"] == "done" and row["texts"]["tr"]["title"] and not row["brief"]


def test_nothing_without_a_window(db, sources, articles):
    ids = add_articles(db, sources, articles, n=1)
    store_text(db, ids[0])
    repo = AiRepository(db)
    repo.next_job()  # no window: no extension work is offered either
    assert repo.get(ids[0]) is None
