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


def start_hidden(exe: Path, profile: Path | None = None, popen: Callable[..., Any] = subprocess.Popen) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    args = [str(exe)]
    if profile is not None:
        profile = profile.resolve()  # a relative path would be read from the browser's own folder
        profile.mkdir(parents=True, exist_ok=True)
        args += [f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check"]
    popen([*args, "--no-startup-window"], close_fds=True, creationflags=flags)  # noqa: S603
