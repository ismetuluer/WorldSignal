"""Filesystem locations.

User data (database, logs, backups, browser profile) always lives on the local
disk, never next to the program: the program folder may be a network share
where SQLite is not safe. The default is ``%LOCALAPPDATA%\\WorldSignal``; the
``WORLDSIGNAL_DATA_DIR`` environment variable overrides it (used by tests and
for development).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NAME = "WorldSignal"


def default_data_dir() -> Path:
    override = os.environ.get("WORLDSIGNAL_DATA_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    if base:
        return Path(base) / APP_NAME
    return Path.home() / f".{APP_NAME.lower()}"


def resource_dir() -> Path:
    """Directory holding bundled read-only resources (catalog, UI files).

    In a PyInstaller build this is the unpacked bundle; in development it is
    the source package directory.
    """
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / "worldsignal"
    return Path(__file__).resolve().parent


def ui_dist_dir() -> Path:
    """Directory with the compiled web interface (``frontend/dist``)."""
    bundled = resource_dir() / "ui"
    if bundled.is_dir():
        return bundled
    return Path(__file__).resolve().parents[2] / "frontend" / "dist"


def extension_dir() -> Path | None:
    """The browser extension's folder (the one the user loads in the browser), or None when it is missing.

    Next to the program in a PyInstaller build; the repository's ``extension/`` in development.
    """
    if getattr(sys, "frozen", False):
        folder = Path(sys.executable).parent / "extension"
    else:
        folder = Path(__file__).resolve().parents[2] / "extension"
    return folder if folder.is_dir() else None


@dataclass(frozen=True)
class DataPaths:
    root: Path

    @property
    def database(self) -> Path:
        return self.root / "worldsignal.db"

    @property
    def logs(self) -> Path:
        return self.root / "logs"

    @property
    def backups(self) -> Path:
        return self.root / "backups"

    @property
    def debug_pages(self) -> Path:
        """Pages kept for diagnosis while the setting ``debug.save_pages`` is on (never in a backup or a release)."""
        return self.root / "debug-pages"

    @property
    def browser_profile(self) -> Path:
        """World Signal's own browser profile (subscription logins for full text)."""
        return self.root / "browser-profile"

    @property
    def instance_file(self) -> Path:
        return self.root / "instance.json"

    @property
    def running_flag(self) -> Path:
        """Present while the program runs; still there after it ended = it crashed (watchdog.py)."""
        return self.root / "running.flag"

    @property
    def watchdog_file(self) -> Path:
        """The process id of the crash-protection watcher."""
        return self.root / "watchdog.pid"

    @property
    def lock_file(self) -> Path:
        return self.root / "instance.lock"

    def ensure(self) -> "DataPaths":
        for p in (self.root, self.logs, self.backups):
            p.mkdir(parents=True, exist_ok=True)
        return self
