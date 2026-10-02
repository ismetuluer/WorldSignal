"""Who reads which full texts, and which paid reports are queued in extension mode."""

from datetime import UTC, datetime, timedelta

from test_fulltext import make_ft_worker, run, source_of, world  # noqa: F401
from worldsignal.apikeys import SecretStore
from worldsignal.repo.fulltext import EXCLUSIVE_BOOST, PAID_BOOST


def test_the_pairing_key_is_kept_apart_from_ai_keys(tmp_path):
    store = SecretStore(tmp_path / "secrets.json", protect=lambda b: b[::-1], unprotect=lambda b: b[::-1])
    store.set("extension", "k" * 43)
    store.set("gemini", "g")
    assert store.get("extension") == "k" * 43 and "extension" not in store.status()
    store.delete("extension")
    assert store.get("extension") is None and store.get("gemini") == "g"


def test_next_job_can_be_limited_to_one_mode(world):
    repo, ids = world["repo"], world["ids"]
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    repo.request(ids["a1"])
    repo.request(ids["b2"])  # another source (a1 and a2 share one), still read over http
    now = datetime.now(UTC)
    assert repo.next_job(now, 99, modes=("http",)).article_id == ids["b2"]
    assert repo.next_job(now, 99, modes=("browser",)).article_id == ids["a1"]


def test_extension_mode_leaves_browser_sources_to_the_extension(world, tmp_path):
    repo, ids = world["repo"], world["ids"]
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    world["settings"].set("fulltext.reader", "extension")
    repo.request(ids["a1"])
    worker = make_ft_worker(world, tmp_path)
    run(worker.step())
    assert repo.get(ids["a1"])["status"] == "pending"  # untouched: no automation browser was started
    from test_fulltext import FakeSession
    assert FakeSession.instances == []


def test_paid_exclusives_come_before_other_paid_reports(world):
    repo, ids, db = world["repo"], world["ids"], world["db"]
    sid = source_of(world, "a1")
    world["sources"].update_source(sid, {"fulltext_mode": "browser"})
    with db.transaction() as c:
        c.execute("UPDATE articles SET title = 'Exclusive: Iran talks stall' WHERE id = ?", (ids["a1"],))
    since = (datetime.now(UTC) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    picks = repo.auto_candidates(since, 999, 2, "2026-10-01", paid=True)
    assert ids["a1"] in picks["exclusive"] and ids["a1"] not in picks["paid"]
    assert repo.auto_candidates(since, 999, 2, "2026-10-01")["exclusive"] == []  # automation mode: not asked
    repo.enqueue(picks["paid"], "auto", boost=PAID_BOOST)
    repo.enqueue(picks["exclusive"], "auto", boost=EXCLUSIVE_BOOST)
    assert repo.next_job(datetime.now(UTC), 99, modes=("browser",)).article_id == ids["a1"]


def make_old(world, *keys, hours=30):
    old = (datetime.now(UTC) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    with world["db"].transaction() as c:
        for key in keys:
            c.execute("UPDATE articles SET sort_at = ? WHERE id = ?", (old, world["ids"][key]))


def test_stale_automatic_picks_are_dropped_but_not_the_users_or_the_notebooks(world):
    repo, ids = world["repo"], world["ids"]
    make_old(world, "a1", "a2", "a3")
    repo.enqueue([ids["a1"], ids["b1"]], "auto", PAID_BOOST)  # a1 old, b1 fresh
    repo.enqueue([ids["a2"]], "notebook")
    repo.request(ids["a3"])
    since = (datetime.now(UTC) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert repo.drop_stale_auto(since) == 1
    assert repo.get(ids["a1"]) is None
    assert repo.get(ids["b1"])["status"] == "pending"
    assert repo.get(ids["a2"])["reason"] == "notebook" and repo.get(ids["a3"])["reason"] == "user"
    assert repo.drop_stale_auto(since) == 0


def test_stale_automatic_picks_that_were_tried_or_done_are_kept(world):
    repo, ids = world["repo"], world["ids"]
    make_old(world, "a1", "a2")
    repo.enqueue([ids["a1"], ids["a2"]], "auto")
    repo.store_text(ids["a1"], "text", "http", datetime.now(UTC))
    job = repo.next_job(datetime.now(UTC), 99)
    repo.store_failure(job, "bot_check", datetime.now(UTC))  # a2: blocked
    since = (datetime.now(UTC) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert repo.drop_stale_auto(since) == 0
    assert repo.get(ids["a1"])["status"] == "done" and repo.get(ids["a2"])["status"] == "blocked"


def test_a_stale_pick_tried_recently_or_being_read_is_kept(world):
    repo, ids = world["repo"], world["ids"]
    make_old(world, "a1", "a2", "a3")
    repo.enqueue([ids["a1"], ids["a2"], ids["a3"]], "auto")
    now = datetime.now(UTC)
    repo.mark_attempt(ids["a1"], now - timedelta(hours=2))  # tried two hours ago: its attempts still count
    repo.mark_attempt(ids["a3"], now - timedelta(hours=30))  # tried long ago: as stale as an untried one
    since = (now - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert repo.drop_stale_auto(since, keep=[ids["a2"]]) == 1  # a2: the extension is reading it
    assert repo.get(ids["a1"])["status"] == "pending" and repo.get(ids["a2"])["status"] == "pending"
    assert repo.get(ids["a3"]) is None
    assert repo.drop_stale_auto(since) == 1  # a2 no longer kept; a1 still recent
    assert repo.get(ids["a2"]) is None and repo.get(ids["a1"]) is not None


def test_the_worker_keeps_the_article_the_extension_is_reading(world, tmp_path):
    repo, ids = world["repo"], world["ids"]
    make_old(world, "a1", "a2")
    repo.enqueue([ids["a1"], ids["a2"]], "auto")
    worker = make_ft_worker(world, tmp_path)
    worker.leased = lambda: ids["a1"]
    world["settings"].set("fulltext.reader", "extension")
    run(worker.step())
    assert repo.get(ids["a1"]) is not None and repo.get(ids["a2"]) is None


def test_the_worker_drops_stale_automatic_picks_in_either_mode(world, tmp_path):
    repo, ids = world["repo"], world["ids"]
    for reader in ("extension", "automation"):
        world["settings"].set("fulltext.reader", reader)
        make_old(world, "a1")
        repo.enqueue([ids["a1"]], "auto")
        assert repo.get(ids["a1"])["status"] == "pending"
        run(make_ft_worker(world, tmp_path).step())
        assert repo.get(ids["a1"]) is None, reader


def test_old_members_of_an_important_story_are_not_picked_again_and_again(world):
    repo, ids, stories = world["repo"], world["ids"], world["stories"]
    hormuz = stories.story_of(ids["a1"])
    with world["db"].transaction() as c:
        c.execute("UPDATE stories SET score = 99, last_seen_at = ? WHERE id = ?",
                  (datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"), hormuz))
    members = [r[0] for r in world["db"].conn.execute("SELECT article_id FROM story_articles WHERE story_id = ?", (hormuz,))]
    keys = [k for k, v in ids.items() if v in members]
    since = (datetime.now(UTC) - timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert repo.auto_candidates(since, 60, 3, "2026-10-01")["auto"]  # recent members are picked
    make_old(world, *keys)
    assert repo.auto_candidates(since, 60, 3, "2026-10-01")["auto"] == []


def test_next_job_skips_excluded_sources(world):
    repo, ids = world["repo"], world["ids"]
    repo.request(ids["a1"])
    repo.request(ids["b2"])
    now = datetime.now(UTC)
    a, b = source_of(world, "a1"), source_of(world, "b2")
    assert repo.next_job(now, 99) is not None
    assert repo.next_job(now, 99, exclude_sources=[a]).article_id == ids["b2"]
    assert repo.next_job(now, 99, exclude_sources=[b]).article_id == ids["a1"]
    assert repo.next_job(now, 99, exclude_sources=[a, b]) is None
    assert repo.next_job(now, 99, exclude_sources=()).article_id in (ids["a1"], ids["b2"])
