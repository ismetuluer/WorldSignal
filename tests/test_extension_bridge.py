"""The extension's side of the queue: one job at a time under a lease, results through record_page."""

from datetime import UTC, datetime, timedelta

import pytest

from test_fulltext import article_page, html, source_of, world  # noqa: F401
from worldsignal.fulltext import bridge as bridge_module
from worldsignal.fulltext.bridge import COOLDOWN_MAX, COOLDOWN_START, LEASE, ExtensionBridge, UnknownLease


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def bridge(world, clock):
    world["settings"].set_many({"fulltext.browser_night_rest": False})
    world["sources"].update_source(source_of(world, "a1"), {"fulltext_mode": "browser"})
    world["repo"].request(world["ids"]["a1"])
    return ExtensionBridge(world["repo"], world["settings"], resting=lambda: False, clock=clock)


def test_a_job_is_leased_once_and_its_text_stored(bridge, world):
    job = bridge.next()
    assert job["article_id"] == world["ids"]["a1"] and job["url"].startswith("http") and job["lease"]
    assert bridge.next()["reason"] == "busy"  # one page at a time
    out = bridge.result(job["lease"], html=article_page(), final_url=job["url"])
    ft = world["repo"].get(job["article_id"])
    assert out["status"] == "done" and ft["method"] == "extension"
    assert bridge.status()["read_today"] == 1 and bridge.status()["connected"]


def test_a_closed_window_costs_nothing(bridge, world):
    job = bridge.next()
    assert bridge.result(job["lease"], error="tab_closed") == {"status": "pending"}
    ft = world["repo"].get(job["article_id"])
    assert ft["status"] == "pending" and ft["attempts"] == 0 and ft["attempted_at"] is None


@pytest.mark.parametrize("code", ["timeout", "load_failed", "script_failed"])
def test_a_page_that_was_asked_for_counts_as_an_attempt(bridge, world, clock, code):
    job = bridge.next()
    assert bridge.result(job["lease"], error=code) == {"status": "pending", "error": code}
    ft = world["repo"].get(job["article_id"])
    assert ft["status"] == "pending" and ft["attempts"] == 1 and ft["error_code"] == code
    assert ft["attempted_at"] == "2026-10-01T09:00:00Z"  # the visit stays on record: the site's pace counts it
    assert bridge.status()["last_error"] == code and bridge.status()["reading"] is None


def test_a_page_that_never_works_is_given_up_after_three_attempts(bridge, world, clock):
    statuses = []
    for _ in range(3):
        clock.now += timedelta(hours=1)  # past the cooldown and the site's gap
        job = bridge.next()
        assert job["article_id"] == world["ids"]["a1"]
        statuses.append(bridge.result(job["lease"], error="load_failed")["status"])
    assert statuses == ["pending", "pending", "failed"]
    ft = world["repo"].get(world["ids"]["a1"])
    assert ft["status"] == "failed" and ft["attempts"] == 3
    clock.now += timedelta(hours=1)
    assert bridge.next()["reason"] == "idle"  # never reopened


def test_an_empty_page_counts_as_load_failed(bridge, world):
    job = bridge.next()
    assert bridge.result(job["lease"], html="")["error"] == "load_failed"
    assert world["repo"].get(job["article_id"])["attempts"] == 1


def test_expired_lease_counts_as_a_timeout(bridge, world, clock):
    first = bridge.next()
    clock.now += LEASE + timedelta(seconds=1)
    assert bridge.next()["reason"] == "cooldown"  # a lost lease rests the site (see the cooldown tests)
    ft = world["repo"].get(first["article_id"])
    assert ft["attempts"] == 1 and ft["error_code"] == "timeout" and ft["status"] == "pending"
    assert ft["attempted_at"] == "2026-10-01T09:00:00Z"
    assert bridge.status()["last_error"] == "timeout"
    clock.now += timedelta(minutes=5)  # the cooldown and the gap between two pages the user asked for
    second = bridge.next()
    assert second["article_id"] == first["article_id"] and second["lease"] != first["lease"]
    with pytest.raises(UnknownLease):
        bridge.result(first["lease"], html=article_page())


def test_a_page_too_large_closes_the_lease_and_counts(bridge, world, clock):
    job = bridge.next()
    assert bridge.reject(job["lease"], "too_large") == {"status": "pending", "error": "too_large"}
    ft = world["repo"].get(job["article_id"])
    assert ft["attempts"] == 1 and ft["error_code"] == "too_large" and ft["attempted_at"] is not None
    assert bridge.status()["reading"] is None
    assert bridge.next()["reason"] == "cooldown"  # not "busy": the lease is closed and the site rests
    with pytest.raises(UnknownLease):
        bridge.result(job["lease"], html=article_page())
    with pytest.raises(UnknownLease):
        bridge.reject(job["lease"], "too_large")
    with pytest.raises(ValueError):
        bridge.reject("anything", "tab_closed")  # only the program's own refusals


def test_a_robot_check_pauses_the_site_and_is_not_retried(bridge, world):
    job = bridge.next()
    page = html("<p>Just a moment...</p><p>Checking your browser before accessing.</p>")
    assert bridge.result(job["lease"], html=page, final_url=job["url"])["status"] == "blocked"
    assert bridge.next()["reason"] == "idle"  # the site is paused; nothing else is queued


def test_a_refusal_status_pauses_the_site_even_without_robot_check_wording(bridge, world, clock):
    job = bridge.next()
    out = bridge.result(job["lease"], html=html("<p>Access denied.</p>"), final_url=job["url"], status=403)
    assert out == {"status": "failed", "error": "http_403"}
    paused = world["repo"].paused_sources(clock.now)
    assert [p["id"] for p in paused] == [source_of(world, "a1")]


def test_failures_read_through_the_extension_are_stored_as_extension(bridge, world, clock):
    job = bridge.next()
    bridge.result(job["lease"], error="load_failed")
    assert world["repo"].get(job["article_id"])["method"] == "extension"
    clock.now += timedelta(hours=1)
    job = bridge.next()
    bridge.result(job["lease"], html=html("<p>Access denied.</p>"), final_url=job["url"], status=403)
    ft = world["repo"].get(job["article_id"])
    assert ft["error_code"] == "http_403" and ft["method"] == "extension"  # the record_page path too


def test_the_leased_article_is_known(bridge, world):
    assert bridge.leased_article() is None
    job = bridge.next()
    assert bridge.leased_article() == job["article_id"]
    bridge.result(job["lease"], error="tab_closed")
    assert bridge.leased_article() is None


def test_an_unknown_status_reads_the_page_as_before(bridge, world):
    job = bridge.next()
    assert bridge.result(job["lease"], html=article_page(), final_url=job["url"], status=None)["status"] == "done"


@pytest.mark.parametrize(("url", "code"), [
    ("https://news.google.com/rss/articles/CBMi?oc=5", "aggregator_link"),
    ("javascript:alert(1)", "not_article"),
    ("file:///C:/Windows/win.ini", "not_article"),
    ("http://[::1/broken", "not_article"),
])
def test_links_the_extension_must_not_open_are_never_handed_out(bridge, world, url, code):
    with world["db"].transaction() as c:
        c.execute("UPDATE articles SET url = ? WHERE id = ?", (url, world["ids"]["a1"]))
    world["repo"].enqueue([world["ids"]["a2"]], "auto")  # behind a1 (the user's request): read instead
    job = bridge.next()
    assert job["article_id"] == world["ids"]["a2"]
    ft = world["repo"].get(world["ids"]["a1"])
    assert ft["status"] == "failed" and ft["error_code"] == code and ft["attempted_at"] is None


def test_a_lease_is_dropped_when_the_extension_stops_being_the_reader(bridge, world):
    job = bridge.next()
    assert bridge.status()["reading"]
    world["settings"].set("fulltext.enabled", False)
    assert bridge.next()["reason"] == "disabled"
    assert bridge.status()["reading"] is None
    with pytest.raises(UnknownLease):
        bridge.result(job["lease"], html=article_page())
    ft = world["repo"].get(job["article_id"])
    assert ft["status"] == "pending" and ft["attempts"] == 0 and ft["attempted_at"] is not None  # it may have been asked for


def test_turning_full_text_off_drops_the_lease_too(bridge, world):
    job = bridge.next()
    world["settings"].set("fulltext.enabled", False)
    assert bridge.next()["reason"] == "disabled" and bridge.status()["reading"] is None
    with pytest.raises(UnknownLease):
        bridge.result(job["lease"], error="timeout")


def test_clear_cooldown_ends_a_sites_rest(bridge, world):
    job = bridge.next()
    bridge.result(job["lease"], error="tab_closed")
    assert bridge.next()["reason"] == "cooldown"
    bridge.clear_cooldown(source_of(world, "a1"))
    bridge.clear_cooldown(999999)  # an unknown source is no error
    assert bridge.next()["article_id"] == job["article_id"]


def test_waits_while_off_resting_or_at_night(world):
    world["settings"].set("fulltext.enabled", False)
    b = ExtensionBridge(world["repo"], world["settings"], resting=lambda: True)
    assert b.next()["reason"] == "disabled"
    world["settings"].set("fulltext.enabled", True)
    assert b.next()["reason"] == "resting"
    assert b.next()["wait_seconds"] >= 60


def test_a_closed_window_rests_the_site_without_touching_the_article(bridge, world, clock):
    job = bridge.next()
    bridge.result(job["lease"], error="tab_closed")
    rest = bridge.next()
    assert rest["reason"] == "cooldown" and rest["wait_seconds"] >= 30
    ft = world["repo"].get(job["article_id"])
    assert ft["attempts"] == 0 and ft["attempted_at"] is None and bridge.status()["reading"] is None
    clock.now += COOLDOWN_START
    assert bridge.next()["article_id"] == job["article_id"]  # rested long enough: leased again


def test_an_error_rests_the_site_on_top_of_counting(bridge, world, clock):
    job = bridge.next()
    bridge.result(job["lease"], error="timeout")
    rest = bridge.next()
    assert rest["reason"] == "cooldown" and rest["wait_seconds"] >= 30


def test_each_error_in_a_row_doubles_the_rest_up_to_the_cap(bridge, clock):
    expected = COOLDOWN_START
    for _ in range(8):
        job = bridge.next()
        assert job["lease"]
        bridge.result(job["lease"], error="tab_closed")  # costs no attempt, so the same page comes back each time
        wait = min(expected, COOLDOWN_MAX)
        clock.now += wait - timedelta(seconds=1)
        assert bridge.next()["reason"] == "cooldown"
        clock.now += timedelta(seconds=1)
        expected *= 2
    assert wait == COOLDOWN_MAX


def test_a_real_answer_starts_the_backoff_over(bridge, world, clock):
    for errors_before in range(2):  # two errors: the rest is now two minutes
        job = bridge.next()
        bridge.result(job["lease"], error="tab_closed")
        clock.now += COOLDOWN_START * 2 ** errors_before
    job = bridge.next()
    bridge.result(job["lease"], html=article_page(), final_url=job["url"])
    world["repo"].request(world["ids"]["a2"])
    clock.now += timedelta(minutes=25)  # a person's pace between two pages of one site
    job = bridge.next()
    assert job["article_id"] == world["ids"]["a2"]
    bridge.result(job["lease"], error="tab_closed")
    clock.now += COOLDOWN_START  # a first error again: one minute, not four
    assert bridge.next()["article_id"] == world["ids"]["a2"]


def test_a_lost_lease_rests_the_site_and_doubles_on_repeat(bridge, clock):
    bridge.next()
    clock.now += LEASE + timedelta(seconds=1)
    assert bridge.next()["reason"] == "cooldown"
    clock.now += timedelta(minutes=3)  # the cooldown, and the gap between two pages the user asked for
    assert bridge.next()["lease"]
    clock.now += LEASE + timedelta(seconds=1)
    rest = bridge.next()
    assert rest["reason"] == "cooldown" and rest["wait_seconds"] > 60  # the second one rests two minutes


def test_a_malformed_lease_is_refused_not_a_crash(bridge):
    bridge.next()
    with pytest.raises(UnknownLease):
        bridge.result("ğüşiöç-lease", html=article_page())


def test_a_failure_while_storing_gives_the_attempt_back(bridge, world, monkeypatch):
    job = bridge.next()

    def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(bridge_module, "record_page", boom)
    with pytest.raises(RuntimeError):
        bridge.result(job["lease"], html=article_page(), final_url=job["url"])
    ft = world["repo"].get(job["article_id"])
    assert ft["status"] == "pending" and ft["attempts"] == 0 and ft["attempted_at"] is None
    assert bridge.status()["reading"] is None


def test_a_resting_site_does_not_hold_up_the_others(bridge, world, clock):
    world["sources"].update_source(source_of(world, "b2"), {"fulltext_mode": "browser"})
    world["repo"].request(world["ids"]["b2"])
    first = bridge.next()
    bridge.result(first["lease"], error="timeout")  # that site rests
    second = bridge.next()
    assert {first["article_id"], second["article_id"]} == {world["ids"]["a1"], world["ids"]["b2"]}  # the other is read meanwhile
    bridge.result(second["lease"], error="timeout")  # it rests too
    rest = bridge.next()
    assert rest["reason"] == "cooldown" and rest["wait_seconds"] >= 30


def test_cooldown_is_the_answer_only_when_nothing_else_is_available(bridge, world, clock):
    job = bridge.next()
    bridge.result(job["lease"], error="timeout")
    first = bridge.next()
    assert first["reason"] == "cooldown" and 30 <= first["wait_seconds"] <= 60
    clock.now += timedelta(seconds=45)
    assert bridge.next()["wait_seconds"] == 30  # 15 s left, never less than the minimum
    world["repo"].request(world["ids"]["b2"])  # a source that is not browser-read: still nothing to hand out
    assert bridge.next()["reason"] == "cooldown"


def fail_many_times(bridge, clock, times):
    for _ in range(times):
        job = bridge.next()
        assert job["lease"]
        bridge.result(job["lease"], error="tab_closed")  # the one error that leaves the page in the queue
        clock.now += COOLDOWN_MAX


def test_endless_failures_keep_the_rest_at_the_cap_and_never_raise(bridge, world, clock):
    fail_many_times(bridge, clock, 65)
    job = bridge.next()
    assert job["lease"]  # still working after 65 errors in a row
    bridge.result(job["lease"], error="tab_closed")
    rest = bridge.next()
    assert rest["reason"] == "cooldown" and rest["wait_seconds"] == COOLDOWN_MAX.total_seconds()
    assert world["repo"].get(job["article_id"])["attempts"] == 0


def test_a_lost_lease_after_many_failures_does_not_wedge_the_bridge(bridge, clock):
    fail_many_times(bridge, clock, 50)
    assert bridge.next()["lease"]
    clock.now += LEASE + timedelta(seconds=1)
    rest = bridge.next()
    assert rest["reason"] == "cooldown" and rest["wait_seconds"] == COOLDOWN_MAX.total_seconds()
    assert bridge.next()["reason"] == "cooldown"  # the lease was cleared: it is not expired a second time
    clock.now += COOLDOWN_MAX
    assert bridge.next()["lease"]


def test_a_lone_surrogate_lease_is_refused_not_a_crash(bridge):
    bridge.next()
    with pytest.raises(UnknownLease):
        bridge.result(chr(0xD800), html=article_page())  # what json.loads makes of a lone \ud800 escape


def test_connected_while_the_extension_keeps_to_the_wait_it_was_handed(bridge, world, clock):
    world["settings"].set("fulltext.enabled", False)
    assert bridge.next()["wait_seconds"] == 300  # disabled: come back in five minutes
    world["settings"].set("fulltext.enabled", True)
    clock.now += timedelta(seconds=300 + 59)
    assert bridge.status()["connected"] and not bridge.status()["warn"]
    clock.now += timedelta(seconds=2)
    assert not bridge.status()["connected"] and not bridge.status()["warn"]  # late, not yet worth a warning
    clock.now += timedelta(minutes=11)  # switching on starts the grace afresh (see the "fresh grace" tests)
    assert bridge.status()["warn"]  # silent for more than ten minutes


def test_a_long_cooldown_wait_is_not_a_lost_connection(bridge, clock):
    fail_many_times(bridge, clock, 8)  # the site now rests 30 minutes after each error
    job = bridge.next()
    bridge.result(job["lease"], error="tab_closed")
    rest = bridge.next()
    assert rest["reason"] == "cooldown" and rest["wait_seconds"] == COOLDOWN_MAX.total_seconds()
    clock.now += COOLDOWN_MAX
    assert bridge.status()["connected"] and not bridge.status()["warn"]
    clock.now += timedelta(seconds=61)
    assert not bridge.status()["connected"] and bridge.status()["warn"]


def test_while_reading_the_lease_time_counts(bridge, clock):
    assert bridge.next()["lease"]
    clock.now += LEASE + timedelta(seconds=30)
    assert bridge.status()["connected"]
    clock.now += timedelta(minutes=1)
    assert not bridge.status()["connected"]


def test_no_warning_at_start_up_until_ten_minutes_have_passed(bridge, clock):
    status = bridge.status()
    assert not status["connected"] and not status["warn"] and status["last_seen"] is None
    clock.now += timedelta(minutes=10)
    assert not bridge.status()["warn"]
    clock.now += timedelta(seconds=1)
    assert bridge.status()["warn"]


def test_switching_to_the_extension_later_gets_a_fresh_grace(world, clock):
    world["settings"].set("fulltext.enabled", False)
    b = ExtensionBridge(world["repo"], world["settings"], resting=lambda: False, clock=clock)
    clock.now += timedelta(hours=3)
    assert not b.status()["warn"]  # not the reader: no warning, and the grace starts over
    world["settings"].set("fulltext.enabled", True)
    assert not b.status()["warn"]  # the interface polls the status: the switch is seen now
    clock.now += timedelta(minutes=9)
    assert not b.status()["warn"]  # nine minutes after switching, not three hours after start-up
    clock.now += timedelta(minutes=2)
    assert b.status()["warn"]


def test_switching_back_after_the_extension_was_seen_gets_a_fresh_grace_too(bridge, world, clock):
    bridge.next()
    world["settings"].set("fulltext.enabled", False)
    clock.now += timedelta(hours=3)
    assert bridge.next()["reason"] == "disabled"  # the extension notices; the grace starts over
    clock.now += timedelta(hours=1)  # the browser was then closed
    world["settings"].set("fulltext.enabled", True)
    assert not bridge.status()["warn"]
    clock.now += timedelta(minutes=11)
    assert bridge.status()["warn"]


def test_no_warning_when_the_extension_is_not_the_reader(bridge, world, clock):
    world["settings"].set("fulltext.enabled", False)
    clock.now += timedelta(hours=2)
    assert not bridge.status()["connected"] and not bridge.status()["warn"]


def test_while_resting_the_answer_is_resting_even_if_a_site_is_cooling(bridge, world):
    job = bridge.next()
    bridge.result(job["lease"], error="timeout")
    bridge.resting = lambda: True
    rest = bridge.next()
    assert rest["reason"] == "resting" and rest["wait_seconds"] >= 60
