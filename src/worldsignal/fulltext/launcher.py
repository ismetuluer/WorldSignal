"""Starting the user's own browser for the extension: a normal start (no automation flags), without a window, only
when it is not running. The extension then opens its own minimized reading window."""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


def is_running(exe: Path, run: Callable[..., Any] = subprocess.run) -> bool:
    try:
        out = run(["tasklist", "/FI", f"IMAGENAME eq {exe.name}", "/FO", "CSV", "/NH"],
                  capture_output=True, text=True, check=False, timeout=10,  # a hung tasklist must not delay shutdown
                  creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout or ""
    except subprocess.TimeoutExpired:
        log.warning("tasklist did not answer in time; assuming %s is running (no second copy is started)", exe.name)
        return True
    return exe.name.lower() in out.lower()


def start_hidden(exe: Path, popen: Callable[..., Any] = subprocess.Popen) -> None:
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    popen([str(exe), "--no-startup-window"], close_fds=True, creationflags=flags)  # noqa: S603
