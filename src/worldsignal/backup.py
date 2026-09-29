"""Database backups: a daily copy, manual copies and restoring one.

Backups are consistent copies made with SQLite's backup API while the program runs, without the
story-matching vectors and zip-compressed (``db.database.write_backup``). File names:
``worldsignal-YYYYmmdd-HHMMSS-<label>.zip``; plain ``.db`` copies of versions before 0.12 are still listed
and can be restored.

Restoring cannot happen under a running program, so it is two-step: the chosen backup is
checked and *scheduled* (``restore.json`` in the data folder), the program restarts, and
:func:`apply_pending_restore` swaps the files before the database is opened. The database
that is replaced is first saved as a ``pre-restore`` backup, so a restore can be undone.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import sqlite3
import time
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from .db import Database
from .db.database import BACKUP_MEMBER, latest_schema_version, write_backup

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^worldsignal-(\d{8})-(\d{6})-([a-z0-9-]+)\.(?:zip|db)$")
KEEP_OTHERS = 10  # pre-migration / pre-restore / manual copies kept besides the daily ones
RESTORE_FILE = "restore.json"
RESTORE_RESULT_FILE = "restore-result.json"


@dataclass
class BackupInfo:
    name: str
    label: str
    created: datetime
    bytes: int

    def public(self) -> dict[str, Any]:
        return {"name": self.name, "label": self.label, "created": self.created.isoformat(timespec="seconds"),
                "bytes": self.bytes}


class InvalidBackup(Exception):
    """The file is not a usable World Signal backup (code: not_found | corrupt | too_new)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class BackupManager:
    def __init__(self, db: Database, backup_dir: Path, data_dir: Path) -> None:
        self.db = db
        self.dir = backup_dir
        self.data_dir = data_dir

    def list(self) -> list[BackupInfo]:
        found = []
        if self.dir.is_dir():
            for p in self.dir.iterdir():
                m = NAME_RE.match(p.name)
                if m and p.is_file():
                    created = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
                    found.append(BackupInfo(p.name, m.group(3), created, p.stat().st_size))
        return sorted(found, key=lambda b: (b.created, b.name), reverse=True)

    def make(self, label: str) -> BackupInfo:
        path = self.db.backup(label)
        if path is None:
            raise RuntimeError("backup directory is not configured")
        return next(b for b in self.list() if b.name == path.name)

    def daily(self, today: date, keep: int) -> BackupInfo | None:
        """Write today's backup if there is none yet, then drop old copies. Returns the new backup."""
        made = None
        if not any(b.label == "daily" and b.created.date() == today for b in self.list()):
            made = self.make("daily")
        self.prune(keep)
        return made

    def prune(self, keep_daily: int) -> int:
        removed = 0
        daily = [b for b in self.list() if b.label == "daily"]
        others = [b for b in self.list() if b.label != "daily"]
        for b in daily[max(1, keep_daily):] + others[KEEP_OTHERS:]:
            try:
                (self.dir / b.name).unlink()
                removed += 1
            except OSError:
                log.warning("Could not delete old backup %s", b.name, exc_info=True)
        return removed

    # -- restore -----------------------------------------------------------------------------
    def check(self, name: str) -> BackupInfo:
        """The backup exists, is intact and is not from a newer program version."""
        info = next((b for b in self.list() if b.name == name), None) if NAME_RE.match(name) else None
        if info is None:
            raise InvalidBackup("not_found")
        verify_backup(self.dir / name)
        return info

    def schedule_restore(self, name: str) -> BackupInfo:
        info = self.check(name)
        _write_json(self.data_dir / RESTORE_FILE, {"name": name})
        log.info("Restore of %s scheduled for the next start", name)
        return info

    def cancel_restore(self) -> None:
        (self.data_dir / RESTORE_FILE).unlink(missing_ok=True)

    def pending_restore(self) -> str | None:
        return _read_json(self.data_dir / RESTORE_FILE).get("name")

    def last_restore(self) -> dict[str, Any] | None:
        return _read_json(self.data_dir / RESTORE_RESULT_FILE) or None


def extract_backup(path: Path, target: Path) -> None:
    """The database of a backup, written to ``target`` (a zip is unpacked, an old ``.db`` copied)."""
    if path.suffix == ".zip":
        try:
            with zipfile.ZipFile(path) as zf, zf.open(BACKUP_MEMBER) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
        except (zipfile.BadZipFile, KeyError) as exc:
            raise InvalidBackup("corrupt") from exc
    else:
        shutil.copyfile(path, target)


@contextmanager
def opened_backup(path: Path) -> Iterator[Path]:
    """A readable database file of the backup ``path`` (unpacked next to it for a zip, removed afterwards)."""
    if path.suffix != ".zip":
        yield path
        return
    tmp = path.with_name(path.name + ".check")
    try:
        extract_backup(path, tmp)
        yield tmp
    finally:
        tmp.unlink(missing_ok=True)


def verify_backup(path: Path) -> None:
    with opened_backup(path) as db_file:
        _verify_database(db_file)


def _verify_database(path: Path) -> None:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            ok = conn.execute("PRAGMA quick_check").fetchone()[0]
            version = int(conn.execute("PRAGMA user_version").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise InvalidBackup("corrupt") from exc
    if ok != "ok" or version < 1:
        raise InvalidBackup("corrupt")
    if version > latest_schema_version():
        raise InvalidBackup("too_new")


def apply_pending_restore(database: Path, backup_dir: Path, data_dir: Path) -> dict[str, Any] | None:
    """Swap in a scheduled backup before the database is opened. Never raises: on any problem the
    current database stays in place and the reason is recorded for the settings page."""
    marker = data_dir / RESTORE_FILE
    name = _read_json(marker).get("name")
    if not name:
        return None
    marker.unlink(missing_ok=True)  # a failing restore must not repeat on every start
    result: dict[str, Any] = {"name": name, "at": datetime.now().isoformat(timespec="seconds"), "ok": False}
    tmp = database.with_suffix(".restoring")
    try:
        source = backup_dir / name
        if not NAME_RE.match(name) or not source.is_file():
            raise InvalidBackup("not_found")
        extract_backup(source, tmp)
        _verify_database(tmp)
        if database.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            safety = backup_dir / f"worldsignal-{stamp}-pre-restore.zip"
            src = sqlite3.connect(database)
            try:
                write_backup(src, safety)  # includes anything still in the WAL file
            finally:
                src.close()
            result["safety_copy"] = safety.name
        _retry(lambda: [Path(f"{database}{suffix}").unlink(missing_ok=True) for suffix in ("-wal", "-shm")])
        _retry(lambda: os.replace(tmp, database))
        result["ok"] = True
        log.info("Database restored from %s", name)
    except InvalidBackup as exc:
        result["error"] = exc.code
        log.error("Restore of %s refused: %s", name, exc.code)
    except (OSError, sqlite3.Error) as exc:
        result["error"] = "io"
        log.exception("Restore of %s failed: %s", name, exc)
    tmp.unlink(missing_ok=True)
    _write_json(data_dir / RESTORE_RESULT_FILE, result)
    return result


def _retry(action: Any, attempts: int = 20, delay: float = 0.5) -> None:
    """Windows keeps a file locked for a moment after another program (or an antivirus scan) let
    go of it: try again for a few seconds before giving up."""
    for i in range(attempts):
        try:
            action()
            return
        except PermissionError:
            if i == attempts - 1:
                raise
            time.sleep(delay)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict[str, Any]) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
