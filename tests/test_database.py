import sqlite3

import pytest

from worldsignal.db import Database
from worldsignal.db import database as database_module


def test_fresh_database_is_migrated_to_latest(db):
    latest = database_module._load_migrations()[-1][0]
    assert db.schema_version() == latest
    tables = {r[0] for r in db.conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table')")}
    assert {"sources", "feeds", "articles", "articles_fts", "settings"} <= tables
    assert db.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert db.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_migrate_is_idempotent_and_does_not_back_up_when_current(db, data_paths):
    before = list(data_paths.backups.iterdir())
    db.migrate()
    assert list(data_paths.backups.iterdir()) == before


def test_newer_schema_is_refused(db):
    db.conn.execute("PRAGMA user_version = 999")
    with pytest.raises(RuntimeError, match="newer"):
        db.migrate()


def test_pending_migration_backs_up_first_and_failed_migration_rolls_back(data_paths, monkeypatch):
    database = Database(data_paths.database, backup_dir=data_paths.backups)
    real = database_module._load_migrations()
    database.migrate()
    database.conn.execute("INSERT INTO settings VALUES ('k', '1', 'now')")

    broken = (len(real) + 1, f"{len(real) + 1:04d}_broken.sql", "CREATE TABLE extra (id INTEGER);\nTHIS IS NOT SQL;")
    monkeypatch.setattr(database_module, "_load_migrations", lambda: [*real, broken])
    with pytest.raises(sqlite3.Error):
        database.migrate()

    # Rolled back: version unchanged, partial table not created, data intact.
    assert database.schema_version() == len(real)
    assert database.conn.execute("SELECT name FROM sqlite_master WHERE name = 'extra'").fetchone() is None
    assert database.conn.execute("SELECT value FROM settings WHERE key = 'k'").fetchone()[0] == "1"
    backups = list(data_paths.backups.glob("*pre-migration*.db"))
    assert len(backups) == 1
    copy = sqlite3.connect(backups[0])
    assert copy.execute("SELECT value FROM settings WHERE key = 'k'").fetchone()[0] == "1"
    copy.close()
    database.close_thread_connection()


def test_transaction_rolls_back_on_error(db):
    with pytest.raises(ValueError):
        with db.transaction() as c:
            c.execute("INSERT INTO settings VALUES ('x', '1', 'now')")
            raise ValueError("boom")
    assert db.conn.execute("SELECT COUNT(*) FROM settings WHERE key = 'x'").fetchone()[0] == 0


def test_nested_transaction_joins_outer(db):
    with pytest.raises(ValueError):
        with db.transaction():
            with db.transaction() as c:
                c.execute("INSERT INTO settings VALUES ('y', '1', 'now')")
            raise ValueError("outer fails")
    assert db.conn.execute("SELECT COUNT(*) FROM settings WHERE key = 'y'").fetchone()[0] == 0


def test_corrupt_database_file_raises_clear_error(data_paths):
    data_paths.database.write_bytes(b"this is not a database" * 100)
    database = Database(data_paths.database, backup_dir=data_paths.backups)
    with pytest.raises(sqlite3.DatabaseError):
        database.migrate()
    database.close_thread_connection()
