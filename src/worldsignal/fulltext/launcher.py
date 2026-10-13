"""Starting the user's own browser for the extension: a normal start (no automation flags), without a window, only
when it is not running. The extension then opens its own minimized reading window (it has no other window to open a tab in).

With a ``profile`` (a folder of World Signal's own) the browser is started on that profile instead, and "running" means
that profile is open: the everyday browser may run or not without mattering."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .fetch import profile_in_use

log = logging.getLogger(__name__)


def is_running(exe: Path, profile: Path | None = None, run: Callable[..., Any] = subprocess.run) -> bool:
    if profile is not None:
        return profile_in_use(profile)
    try:
        out = run(["tasklist", "/FI", f"IMAGENAME eq {exe.name}", "/FO", "CSV", "/NH"],
                  capture_output=True, text=True, check=False, timeout=10,  # a hung tasklist must not delay shutdown
                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout or ""
    except subprocess.TimeoutExpired:
        log.warning("tasklist did not answer in time; assuming %s is running (no second copy is started)", exe.name)
        return True
    return exe.name.lower() in out.lower()


def profile_pids(exe: Path, profile: Path, run: Callable[..., Any] = subprocess.run) -> list[int]:
    """The processes of ``exe`` that run on ``profile`` (the browser and its helpers: the profile's folder is on every
    command line)."""
    path = str(profile.resolve()).replace("'", "''")
    script = (f"Get-CimInstance Win32_Process -Filter \"Name='{exe.name}'\" | "
              f"Where-Object {{ $_.CommandLine -and $_.CommandLine.Contains('{path}') }} | ForEach-Object {{ $_.ProcessId }}")
    out = run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], capture_output=True, text=True,
              check=False, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout or ""
    return [int(x) for x in out.split() if x.isdigit()]


def has_visible_window(pids: list[int]) -> bool:
    """A browser window of these processes is open on the screen and not minimized: somebody is using it. The extension's
    own reading window is minimized, and a stuck one left behind does not count."""
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    wanted = set(pids)
    found: list[int] = []
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def visit(hwnd: int, _lparam: int) -> bool:
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value in wanted and user32.IsWindowVisible(hwnd) and not user32.IsIconic(hwnd):
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(hwnd, cls, 64)
            if cls.value.startswith("Chrome_WidgetWin"):
                found.append(hwnd)
        return True

    user32.EnumWindows(enum_proc(visit), 0)
    return bool(found)


def stop_profile(exe: Path, profile: Path, run: Callable[..., Any] = subprocess.run,
                 pids_of: Callable[..., list[int]] = profile_pids,
                 visible: Callable[[list[int]], bool] = has_visible_window) -> int:
    """End the browser that runs on World Signal's own ``profile`` (never the everyday browser: only processes whose command
    line holds that profile folder). Returns how many processes were ended, or -1 when a window of it is open on the screen
    (somebody is using it: it is left alone)."""
    pids = pids_of(exe, profile)
    if not pids:
        return 0
    if visible(pids):
        return -1
    for pid in pids:
        run(["taskkill", "/F", "/PID", str(pid)], capture_output=True, check=False, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return len(pids)


def start_hidden(exe: Path, profile: Path | None = None, popen: Callable[..., Any] = subprocess.Popen) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    args = [str(exe)]
    if profile is not None:
        profile = profile.resolve()  # a relative path would be read from the browser's own folder
        profile.mkdir(parents=True, exist_ok=True)
        args += [f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check"]
    popen([*args, "--no-startup-window"], close_fds=True, creationflags=flags)  # noqa: S603
