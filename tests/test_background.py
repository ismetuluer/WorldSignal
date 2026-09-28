"""Phase 7 backend: daily backups, restore, notifications and their API."""

import json
import sqlite3
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from test_api import TOKEN, ctx  # noqa: F401  (the API fixture)
from test_stories import NOW, seed_articles
from worldsignal.api.app import create_app
from worldsignal.backup import (
    KEEP_OTHERS, RESTORE_FILE, RESTORE_RESULT_FILE, BackupManager, InvalidBackup, apply_pending_restore,
)
from worldsignal.db import Database
from worldsignal.maintenance import Maintenance
from worldsignal.notify import Notifier, in_quiet_hours, spreading_count
from worldsignal.repo.history import HistoryRepository
from worldsignal.repo.stories import StoryRepository


@pytest.fixture
def backups(db, data_paths):
    return BackupManager(db, data_paths.backups, data_paths.root)


def fake_backup(dir_, stamp: str, label: str, db_source=None):
    path = dir_ / f"worldsignal-{stamp}-{label}.db"
    if db_source is not None:
        dst = sqlite3.connect(path)
        db_source.conn.backup(dst)
        dst.close()
    else:
        path.write_bytes(b"x")
    return path


# -- backups --------------------------------------------------------------------------------------
def test_daily_backup_once_per_day_and_old_ones_pruned(db, backups, data_paths):
    for i in range(5):
        fake_backup(data_paths.backups, f"2026090{i + 1}-080000", "daily")
    today = datetime.now().date()
    made = backups.daily(today, keep=3)
    assert made is not None and made.label == "daily" and made.created.date() == today
    assert backups.daily(today, keep=3) is None  # already done today
    daily = [b for b in backups.list() if b.label == "daily"]
    assert len(daily) == 3 and daily[0].name == made.name  # newest first, oldest removed
    # The copy is a real, readable database.
    conn = sqlite3.connect(data_paths.backups / made.name)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == db.schema_version()
    conn.close()


def test_other_backups_are_kept_separately(backups, data_paths):
    for i in range(KEEP_OTHERS + 3):
        fake_backup(data_paths.backups, f"202609{i + 10:02d}-080000", "pre-migration-v1")
    fake_backup(data_paths.backups, "20260901-080000", "daily")
    backups.prune(keep_daily=5)
    labels = [b.label for b in backups.list()]
    assert labels.count("pre-migration-v1") == KEEP_OTHERS and labels.count("daily") == 1
    (data_paths.backups / "notes.txt").write_text("not a backup")
    assert all(b.name.startswith("worldsignal-") for b in backups.list())


def test_manual_backup_and_check(db, backups, data_paths):
    info = backups.make("manual")
    assert backups.check(info.name).name == info.name
    with pytest.raises(InvalidBackup) as e:
        backups.check("../worldsignal.db")
    assert e.value.code == "not_found"
    broken = fake_backup(data_paths.backups, "20260920-080000", "manual")
    with pytest.raises(InvalidBackup) as e:
        backups.check(broken.name)
    assert e.value.code == "corrupt"


def test_backup_from_a_newer_program_is_refused(db, backups, data_paths):
    info = backups.make("manual")
    conn = sqlite3.connect(data_paths.backups / info.name)
    conn.execute("PRAGMA user_version = 999")
    conn.close()
    with pytest.raises(InvalidBackup) as e:
        backups.schedule_restore(info.name)
    assert e.value.code == "too_new" and backups.pending_restore() is None


def test_restore_swaps_the_database_and_keeps_a_safety_copy(data_paths):
    db = Database(data_paths.database, backup_dir=data_paths.backups)
    db.migrate()
    db.conn.execute("CREATE TABLE marker (v TEXT)")
    db.conn.execute("INSERT INTO marker VALUES ('old')")
    manager = BackupManager(db, data_paths.backups, data_paths.root)
    info = manager.make("manual")
    db.conn.execute("UPDATE marker SET v = 'new'")
    manager.schedule_restore(info.name)
    assert manager.pending_restore() == info.name
    db.close_thread_connection()

    result = apply_pending_restore(data_paths.database, data_paths.backups, data_paths.root)
    assert result["ok"] is True and result["name"] == info.name
    assert not (data_paths.root / RESTORE_FILE).exists()
    reopened = Database(data_paths.database)
    assert reopened.conn.execute("SELECT v FROM marker").fetchone()[0] == "old"
    safety = sqlite3.connect(data_paths.backups / result["safety_copy"])
    assert safety.execute("SELECT v FROM marker").fetchone()[0] == "new"  # the replaced data is not lost
    safety.close()
    reopened.close_thread_connection()
    assert json.loads((data_paths.root / RESTORE_RESULT_FILE).read_text(encoding="utf-8"))["ok"] is True


def test_failed_restore_leaves_the_database_and_does_not_repeat(data_paths):
    db = Database(data_paths.database)
    db.migrate()
    db.close_thread_connection()
    (data_paths.root / RESTORE_FILE).write_text(json.dumps({"name": "worldsignal-20260101-000000-gone.db"}), encoding="utf-8")
    result = apply_pending_restore(data_paths.database, data_paths.backups, data_paths.root)
    assert result["ok"] is False and result["error"] == "not_found"
    assert data_paths.database.exists() and not (data_paths.root / RESTORE_FILE).exists()
    assert apply_pending_restore(data_paths.database, data_paths.backups, data_paths.root) is None


def test_maintenance_makes_the_daily_backup_first(db, settings, backups):
    m = Maintenance(HistoryRepository(db, StoryRepository(db)), settings, backups, clock=lambda: NOW)
    m.run_once()
    assert m.status()["last_backup"].endswith("-daily.db") and m.status()["backup_error"] is None

    class Broken(BackupManager):
        def daily(self, today: date, keep: int):
            raise OSError("disk full")

    m2 = Maintenance(HistoryRepository(db, StoryRepository(db)), settings, Broken(db, backups.dir, backups.data_dir),
                     clock=lambda: NOW)
    m2.run_once()  # the retention part still runs
    assert m2.status()["backup_error"] == "OSError" and m2.status()["last_run_at"] is not None


# -- notifications ----------------------------------------------------------------------------------
@pytest.mark.parametrize(("hour", "start", "end", "quiet"), [
    (23, 23, 7, True), (3, 23, 7, True), (7, 23, 7, False), (12, 23, 7, False),
    (13, 12, 14, True), (14, 12, 14, False), (5, 7, 7, False),
])
def test_quiet_hours(hour, start, end, quiet):
    assert in_quiet_hours(hour, start, end) is quiet


def test_spreading_count_reads_the_score_tags():
    assert spreading_count(json.dumps({"tags": [{"kind": "sources", "count": 9}, {"kind": "spreading", "count": 6}]})) == 6
    assert spreading_count(None) == 0 and spreading_count("{broken") == 0


def make_story(db, sources, articles, key: str, score: float, spreading: int, minutes_ago: int = 5):
    ids = seed_articles(db, sources, articles, [("alpha", key, f"Story {key}", minutes_ago)])
    stories = StoryRepository(db)
    sid = stories.assign(ids[key], None, similarity=1.0)
    parts = {"tags": [{"kind": "spreading", "count": spreading, "hours": 3}]}
    with db.transaction() as c:
        c.execute("UPDATE stories SET score = ?, score_parts = ?, last_seen_at = ?, ai_title_tr = ?, ai_title_en = ? WHERE id = ?",
                  (score, json.dumps(parts), (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   f"Hikâye {key}", f"Story EN {key}", sid))
    return sid


@pytest.fixture
def notifier(db, settings):
    shown = []
    n = Notifier(db, settings, clock=lambda: NOW)
    n.show = lambda title, body, sid: shown.append((title, body, sid))
    n.shown = shown
    settings.set("notify.quiet", False)
    return n


def test_one_spreading_story_is_announced_once(db, sources, articles, notifier):
    big = make_story(db, sources, articles, "big", 75, 6)
    make_story(db, sources, articles, "slow", 80, 2)  # important but not spreading
    make_story(db, sources, articles, "minor", 40, 9)  # spreading but not important
    make_story(db, sources, articles, "old", 90, 9, minutes_ago=60 * 5)  # no longer recent
    alert = notifier.check()
    assert alert is not None and alert.story_id == big
    assert notifier.shown == [("Hızla yayılıyor · 6 kaynak", "Hikâye big", big)]
    notifier._last_shown = None
    assert notifier.check() is None  # never twice
    assert notifier.status()["sent"] == 1 and notifier.status()["available"] is True


def test_several_stories_become_one_notification_in_english(db, sources, articles, notifier, settings):
    a = make_story(db, sources, articles, "a", 90, 7)
    make_story(db, sources, articles, "b", 70, 5)
    settings.set("ui.language", "en")
    alert = notifier.check()
    assert (alert.title, alert.body, alert.story_id) == ("2 stories spreading fast", "Story EN a and 1 more", a)


def test_quiet_hours_gap_disabled_and_unavailable(db, sources, articles, notifier, settings):
    make_story(db, sources, articles, "q", 90, 7)
    hour = NOW.astimezone().hour
    settings.set("notify.quiet", True)
    settings.set("notify.quiet_start", hour)
    settings.set("notify.quiet_end", (hour + 1) % 24)
    assert notifier.check() is None
    settings.set("notify.quiet", False)
    settings.set("notify.enabled", False)
    assert notifier.check() is None
    settings.set("notify.enabled", True)
    notifier._last_shown = NOW - timedelta(minutes=2)  # too soon after the previous one
    assert notifier.check() is None
    notifier._last_shown = None
    shown = notifier.show
    notifier.show = None  # server-only mode: nothing is marked as announced
    assert notifier.check() is None and notifier.status()["available"] is False
    notifier.show = shown
    assert notifier.check() is not None  # announced once a desktop can show it


def test_a_failing_display_does_not_break_the_check(db, sources, articles, notifier):
    make_story(db, sources, articles, "f", 90, 7)
    notifier.show = lambda *a: 1 / 0
    assert notifier.check() is not None


# -- API ----------------------------------------------------------------------------------------------
def client_for(c):  # noqa: F811
    return TestClient(create_app(c), headers={"X-WorldSignal-Token": TOKEN})


def test_backup_and_notification_api(ctx):  # noqa: F811
    with client_for(ctx) as c:
        made = c.post("/api/backups").json()
        assert made["label"] == "manual" and made["bytes"] > 0
        listing = c.get("/api/backups").json()
        assert listing["backups"][0]["name"] == made["name"]
        assert listing["pending_restore"] is None and listing["can_restart"] is False
        scheduled = c.post("/api/backups/restore", json={"name": made["name"]}).json()
        assert scheduled["scheduled"]["name"] == made["name"] and scheduled["can_restart"] is False
        assert c.get("/api/backups").json()["pending_restore"] == made["name"]
        assert c.delete("/api/backups/restore").status_code == 204
        assert c.get("/api/backups").json()["pending_restore"] is None
        assert c.post("/api/backups/restore", json={"name": "nope.db"}).json()["detail"]["code"] == "backup_not_found"
        assert c.post("/api/app/restart").json()["detail"]["code"] == "restart_unavailable"
        assert c.post("/api/notify/test").json()["detail"]["code"] == "notify_unavailable"
        shown = []
        ctx.notifier.show = lambda *a: shown.append(a)
        restarted = []
        ctx.restart = lambda: restarted.append(True)
        assert c.post("/api/notify/test").json() == {"ok": True} and shown[0][0] == "World Signal bildirimi"
        assert c.post("/api/app/restart").json() == {"ok": True} and restarted == [True]
        status = c.get("/api/status").json()
        assert status["notify"]["available"] is True
        prefs = c.patch("/api/settings", json={"notify.min_sources": 3, "app.close_to_tray": False,
                                               "backup.keep_daily": 7}).json()
        assert (prefs["notify.min_sources"], prefs["app.close_to_tray"], prefs["backup.keep_daily"]) == (3, False, 7)
        assert c.patch("/api/settings", json={"notify.quiet_start": 24}).status_code == 422
        assert c.patch("/api/settings", json={"notify.min_sources": 1}).status_code == 422


def test_restore_waits_for_a_file_still_held_by_the_old_process(data_paths, monkeypatch):
    """After a restart Windows can hold the old database for a moment; the swap retries."""
    import worldsignal.backup as backup_mod

    db = Database(data_paths.database, backup_dir=data_paths.backups)
    db.migrate()
    manager = BackupManager(db, data_paths.backups, data_paths.root)
    info = manager.make("manual")
    manager.schedule_restore(info.name)
    db.close_thread_connection()
    real_replace, calls = backup_mod.os.replace, []

    def flaky_replace(src, dst):
        if dst == data_paths.database:
            calls.append(dst)
            if len(calls) < 3:
                raise PermissionError(32, "in use")
        real_replace(src, dst)

    monkeypatch.setattr(backup_mod.os, "replace", flaky_replace)
    monkeypatch.setattr(backup_mod.time, "sleep", lambda s: None)
    result = apply_pending_restore(data_paths.database, data_paths.backups, data_paths.root)
    assert result["ok"] is True and len(calls) == 3
    assert not data_paths.database.with_suffix(".restoring").exists()


def test_a_restore_that_keeps_failing_cleans_up(data_paths, monkeypatch):
    import worldsignal.backup as backup_mod

    db = Database(data_paths.database, backup_dir=data_paths.backups)
    db.migrate()
    manager = BackupManager(db, data_paths.backups, data_paths.root)
    manager.schedule_restore(manager.make("manual").name)
    db.close_thread_connection()

    real_replace = backup_mod.os.replace

    def locked(src, dst):
        if dst == data_paths.database:
            raise PermissionError(32, "in use")
        real_replace(src, dst)

    monkeypatch.setattr(backup_mod.os, "replace", locked)
    monkeypatch.setattr(backup_mod.time, "sleep", lambda s: None)
    result = apply_pending_restore(data_paths.database, data_paths.backups, data_paths.root)
    assert result == {**result, "ok": False, "error": "io"}
    assert not data_paths.database.with_suffix(".restoring").exists() and data_paths.database.exists()


def test_wait_for_exit_returns_when_the_process_ends():
    import subprocess
    import sys
    import time

    from worldsignal.__main__ import wait_for_exit

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(0.5)"])
    t0 = time.monotonic()
    wait_for_exit(proc.pid, timeout=10)
    assert proc.poll() is not None or proc.wait(timeout=1) == 0
    assert time.monotonic() - t0 < 5
    wait_for_exit(999_999_999, timeout=1)  # unknown process: returns at once
