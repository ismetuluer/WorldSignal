"""Crash protection: start World Signal again when it ended without stopping properly (``system.restart_on_crash``).

A crash (an access violation, a killed process) cannot be handled inside the dying process, so a second, small process of the
same program watches it:

* the program writes ``running.flag`` when it starts and removes it when it stops properly (closing from the tray, an update,
  a restart it asked for itself); a crash leaves the flag behind;
* the watcher waits for the program to end; with the flag still there it starts the program again, as long as the setting
  is still on. It then watches the new process, and stops when the program stopped properly, or when it kept crashing
  (``MAX_CRASHES`` within ``CRASH_WINDOW`` seconds: a program that cannot start would otherwise be started over and over).

The watcher is started by the program itself at start-up (setting on) and when the setting is switched on.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import subprocess
import sys
import time
from collections import deque
from pathlib import Path

from .paths import DataPaths

log = logging.getLogger("worldsignal.watchdog")

SETTING = "system.restart_on_crash"
MAX_CRASHES = 3
CRASH_WINDOW = 600.0  # seconds
RESTART_DELAY = 5.0  # seconds: the old process must have let go of the database and the instance lock

_SYNCHRONIZE = 0x00100000
_QUERY_LIMITED = 0x1000
_INFINITE = 0xFFFFFFFF


def process_alive(pid: int) -> bool:
    """True while process ``pid`` exists."""
    if pid <= 0:
        return False
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        return True
    import ctypes

    handle = ctypes.windll.kernel32.OpenProcess(_QUERY_LIMITED, False, pid)
    if not handle:
        return False
    try:
        code = ctypes.c_ulong()
        ok = ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    finally:
        ctypes.windll.kernel32.CloseHandle(handle)


def wait_until_gone(pid: int) -> None:
    """Block until process ``pid`` has ended."""
    if os.name == "nt":
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(_SYNCHRONIZE, False, pid)
        if not handle:
            return
        try:
            ctypes.windll.kernel32.WaitForSingleObject(handle, _INFINITE)
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
        return
    while process_alive(pid):
        time.sleep(1)


def mark_running(paths: DataPaths) -> None:
    """The program is running: if it ends without ``mark_stopped``, that was a crash."""
    paths.running_flag.write_text(str(os.getpid()), encoding="utf-8")


def mark_stopped(paths: DataPaths) -> None:
    paths.running_flag.unlink(missing_ok=True)


def setting_on(database: Path) -> bool:
    """Read the setting without opening the program's own connection (the watcher must not hold the database)."""
    try:
        conn = sqlite3.connect(f"file:{database.as_posix()}?mode=ro", uri=True, timeout=5)
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (SETTING,)).fetchone()
        finally:
            conn.close()
    except sqlite3.Error:
        log.exception("Could not read %s", SETTING)
        return False
    return bool(row) and row[0] == "true"


def program_command(paths: DataPaths, *extra: str) -> list[str]:
    base = [sys.executable] if getattr(sys, "frozen", False) else [sys.executable, "-m", "worldsignal"]
    return [*base, f"--data-dir={paths.root}", *extra]


def _detached(cmd: list[str]) -> subprocess.Popen:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    return subprocess.Popen(cmd, close_fds=True, creationflags=flags, cwd=str(Path(sys.executable).parent))  # noqa: S603


def arm(paths: DataPaths) -> bool:
    """Start the watcher for this process unless one is already watching. Returns whether one was started."""
    try:
        if process_alive(int(paths.watchdog_file.read_text(encoding="utf-8").strip() or 0)):
            return False
    except (OSError, ValueError):
        pass
    child = _detached(program_command(paths, f"--watch-pid={os.getpid()}"))
    paths.watchdog_file.write_text(str(child.pid), encoding="utf-8")
    log.info("Crash protection: watcher %d started", child.pid)
    return True


def watch(paths: DataPaths, pid: int, delay: float = RESTART_DELAY) -> int:
    """The watcher process: see the module text. Returns the exit code of the watcher."""
    paths.watchdog_file.write_text(str(os.getpid()), encoding="utf-8")
    crashes: deque[float] = deque()
    try:
        while True:
            wait_until_gone(pid)
            if not paths.running_flag.exists():
                log.info("Process %d stopped properly; the watcher ends", pid)
                return 0
            if not setting_on(paths.database):
                log.info("Process %d ended without stopping properly, but the protection is off", pid)
                paths.running_flag.unlink(missing_ok=True)
                return 0
            now = time.monotonic()
            crashes.append(now)
            while crashes and now - crashes[0] > CRASH_WINDOW:
                crashes.popleft()
            if len(crashes) > MAX_CRASHES:
                log.error("Process %d crashed %d times in %d seconds; giving up", pid, len(crashes), int(CRASH_WINDOW))
                paths.running_flag.unlink(missing_ok=True)
                return 1
            log.warning("Process %d ended without stopping properly; starting World Signal again", pid)
            paths.running_flag.unlink(missing_ok=True)
            time.sleep(delay)
            pid = _detached(program_command(paths)).pid
            time.sleep(delay)  # let the new process start and write its flag before the next wait
    finally:
        try:
            if int(paths.watchdog_file.read_text(encoding="utf-8").strip() or 0) == os.getpid():
                paths.watchdog_file.unlink(missing_ok=True)
        except (OSError, ValueError):
            pass
