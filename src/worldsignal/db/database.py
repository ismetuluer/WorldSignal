"""SQLite access: connections, transactions and versioned migrations.

Design notes
------------
* One connection per thread (SQLite connections must not be shared between
  threads). WAL mode lets the web API read while the collector writes.
* Connections run in autocommit mode; every write goes through
  :meth:`Database.transaction`, which wraps it in ``BEGIN IMMEDIATE`` so an
  interrupted operation is rolled back as a whole.
* The schema version lives in ``PRAGMA user_version``. Migrations are numbered
  ``NNNN_name.sql`` files applied in order, each in its own transaction.
  Before migrating an existing database a full backup is written, which is the
  rollback path if a new version misbehaves.
"""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path

log = logging.getLogger(__name__)

_MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


def utc_now_iso(dt: datetime | None = None) -> str:
    dt = dt or datetime.now(UTC)
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_migrations() -> list[tuple[int, str, str]]:
    found = []
    for entry in resources.files("worldsignal.db.migrations").iterdir():
        m = _MIGRATION_NAME.match(entry.name)
        if m:
            found.append((int(m.group(1)), entry.name, entry.read_text(encoding="utf-8")))
    found.sort()
    for expected, (number, name, _) in enumerate(found, start=1):
        if number != expected:
            raise RuntimeError(f"Migration numbering gap at {name}; expected {expected:04d}")
    return found


def latest_schema_version() -> int:
    """The schema version this program creates (the newest migration)."""
    migrations = _load_migrations()
    return migrations[-1][0] if migrations else 0


class Database:
    def __init__(self, path: Path, backup_dir: Path | None = None) -> None:
        self.path = path
        self.backup_dir = backup_dir
        self._local = threading.local()

    # -- connections -----------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, isolation_level=None, check_same_thread=True, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @property
    def conn(self) -> sqlite3.Connection:
        c = getattr(self._local, "conn", None)
        if c is None:
            c = self._connect()
            self._local.conn = c
        return c

    def close_thread_connection(self) -> None:
        c = getattr(self._local, "conn", None)
        if c is not None:
            c.close()
            self._local.conn = None

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        c = self.conn
        if c.in_transaction:
            # Nested use joins the outer transaction.
            yield c
            return
        c.execute("BEGIN IMMEDIATE")
        try:
            yield c
        except BaseException:
            c.execute("ROLLBACK")
            raise
        else:
            c.execute("COMMIT")

    # -- schema ------------------------------------------------------------
    def schema_version(self) -> int:
        return int(self.conn.execute("PRAGMA user_version").fetchone()[0])

    def migrate(self) -> int:
        """Bring the schema up to date. Returns the resulting version."""
        migrations = _load_migrations()
        latest = migrations[-1][0] if migrations else 0
        current = self.schema_version()
        if current > latest:
            raise RuntimeError(
                f"Database schema v{current} is newer than this program (v{latest}). "
                "Please use a newer World Signal version."
            )
        if current == latest:
            return current

        if current > 0:
            self.backup(f"pre-migration-v{current}")

        c = self.conn
        for number, name, sql in migrations:
            if number <= current:
                continue
            log.info("Applying migration %s", name)
            # executescript() would auto-commit, so the whole script, including
            # the version bump, is wrapped in an explicit transaction.
            try:
                c.executescript(f"BEGIN IMMEDIATE;\n{sql}\nPRAGMA user_version = {number};\nCOMMIT;")
            except Exception:
                if c.in_transaction:
                    c.execute("ROLLBACK")
                log.exception("Migration %s failed; database left at v%s", name, number - 1)
                raise
        return self.schema_version()

    def backup(self, label: str) -> Path | None:
        """Write a consistent copy of the database using SQLite's backup API."""
        if self.backup_dir is None or not self.path.exists():
            return None
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        target = self.backup_dir / f"worldsignal-{stamp}-{label}.db"
        dst = sqlite3.connect(target)
        try:
            self.conn.backup(dst)
        finally:
            dst.close()
        log.info("Database backup written: %s", target)
        return target
