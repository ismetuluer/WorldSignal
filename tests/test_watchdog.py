"""Crash protection (watchdog.py): the watcher starts the program again only after a crash, only while the setting is on."""

import json
import os
import sqlite3
import subprocess
import sys

import pytest

from worldsignal import watchdog
from worldsignal.paths import DataPaths


@pytest.fixture
def paths(tmp_path):
    p = DataPaths(tmp_path).ensure()
    conn = sqlite3.connect(p.database)
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.commit()
    conn.close()
    return p


def set_setting(paths, on):
    conn = sqlite3.connect(paths.database)
    conn.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (watchdog.SETTING, json.dumps(on)))
    conn.commit()
    conn.close()


def ended_process():
    """A process that has already ended: what the watcher waits for."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc


class FakeProgram:
    """Stands in for starting the program: counts the starts; ``crash`` leaves the flag behind like a crash does."""

    def __init__(self, paths, crash):
        self.paths, self.crash, self.starts = paths, crash, 0

    def __call__(self, cmd):
        self.starts += 1
        if self.crash:
            self.paths.running_flag.write_text("x")
        return ended_process()


def test_a_proper_stop_is_left_alone(paths, monkeypatch):
    set_setting(paths, True)
    program = FakeProgram(paths, crash=False)
    monkeypatch.setattr(watchdog, "_detached", program)
    assert watchdog.watch(paths, ended_process().pid, delay=0) == 0  # no flag: it stopped properly
    assert program.starts == 0


def test_a_crash_starts_the_program_again(paths, monkeypatch):
    set_setting(paths, True)
    watchdog.mark_running(paths)  # the flag a crash leaves behind
    program = FakeProgram(paths, crash=False)  # the new program then stops properly
    monkeypatch.setattr(watchdog, "_detached", program)
    assert watchdog.watch(paths, ended_process().pid, delay=0) == 0
    assert program.starts == 1


def test_a_crash_with_the_protection_off_is_not_restarted(paths, monkeypatch):
    set_setting(paths, False)
    watchdog.mark_running(paths)
    program = FakeProgram(paths, crash=False)
    monkeypatch.setattr(watchdog, "_detached", program)
    assert watchdog.watch(paths, ended_process().pid, delay=0) == 0
    assert program.starts == 0 and not paths.running_flag.exists()


def test_a_program_that_keeps_crashing_is_given_up_on(paths, monkeypatch):
    set_setting(paths, True)
    watchdog.mark_running(paths)
    program = FakeProgram(paths, crash=True)
    monkeypatch.setattr(watchdog, "_detached", program)
    assert watchdog.watch(paths, ended_process().pid, delay=0) == 1
    assert program.starts == watchdog.MAX_CRASHES


def test_flag_and_arm(paths, monkeypatch):
    watchdog.mark_running(paths)
    assert paths.running_flag.read_text() == str(os.getpid())
    watchdog.mark_stopped(paths)
    assert not paths.running_flag.exists()
    started = []
    monkeypatch.setattr(watchdog, "_detached", lambda cmd: started.append(cmd) or ended_process())
    assert watchdog.arm(paths) is True and f"--watch-pid={os.getpid()}" in started[0][-1]
    paths.watchdog_file.write_text(str(os.getpid()))  # a watcher that is alive
    assert watchdog.arm(paths) is False and len(started) == 1


def test_setting_on_reads_the_database(paths):
    assert watchdog.setting_on(paths.database) is False
    set_setting(paths, True)
    assert watchdog.setting_on(paths.database) is True
    assert watchdog.setting_on(paths.root / "missing.db") is False
