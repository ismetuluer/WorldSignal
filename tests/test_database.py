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
    backups = list(data_paths.backups.glob("*pre-migration*.zip"))
    assert len(backups) == 1
    from worldsignal.backup import opened_backup

    with opened_backup(backups[0]) as db_file:
        copy = sqlite3.connect(db_file)
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


def test_turkish_and_english_ai_texts_move_to_the_language_columns(data_paths, monkeypatch):
    """0009: the fixed *_tr / *_en columns become one JSON column per row, nothing is lost."""
    import json

    real = database_module._load_migrations()
    database = Database(data_paths.database, backup_dir=data_paths.backups)
    monkeypatch.setattr(database_module, "_load_migrations", lambda: [m for m in real if m[0] <= 8])
    database.migrate()
    c = database.conn
    now = "2026-09-28T08:00:00Z"
    c.execute("""INSERT INTO sources (id, slug, name, catalog_group, region, language, created_at, updated_at)
                 VALUES (1, 's', 'S', 'other', 'global', 'en', ?, ?)""", (now, now))
    c.execute("INSERT INTO feeds (id, source_id, url, created_at) VALUES (1, 1, 'https://s.example/rss', ?)", (now,))
    for aid in (1, 2, 3):
        c.execute("""INSERT INTO articles (id, source_id, feed_id, dedupe_key, url, title, first_seen_at, sort_at)
                     VALUES (?, 1, 1, ?, 'https://s.example/a', 'Headline', ?, ?)""", (aid, f"k{aid}", now, now))
    c.execute("""INSERT INTO article_ai (article_id, status, title_tr, summary_tr, title_en, summary_en, queued_at)
                 VALUES (1, 'done', 'Başlık', 'Özet.', 'Title', 'Summary.', ?)""", (now,))
    c.execute("INSERT INTO article_ai (article_id, status, title_tr, summary_tr, queued_at) VALUES (2, 'done', 'Yalnız', NULL, ?)",
              (now,))
    c.execute("INSERT INTO article_ai (article_id, status, queued_at) VALUES (3, 'pending', ?)", (now,))
    c.execute("""INSERT INTO stories (id, first_seen_at, last_seen_at, ai_status, ai_title_tr, ai_summary_tr, ai_why,
                                      ai_title_en, ai_summary_en, ai_why_en, created_at, updated_at)
                 VALUES (1, ?, ?, 'done', 'H', 'Ö', 'N', 'S', 'Sum', 'W', ?, ?)""", (now, now, now, now))
    c.execute("""INSERT INTO meeting_items (day, story_id, position, title, summary, why, title_en, created_at, updated_at)
                 VALUES ('2026-09-28', 1, 0, 'H', 'Ö', NULL, 'S', ?, ?)""", (now, now))
    c.execute("""INSERT INTO article_fulltext (article_id, status, text, queued_at, translate_status, text_tr, text_en)
                 VALUES (1, 'done', 'Text', ?, 'done', 'Metin', 'Text')""", (now,))

    monkeypatch.setattr(database_module, "_load_migrations", lambda: real)
    database.migrate()
    texts = {r[0]: json.loads(r[1]) for r in c.execute("SELECT article_id, texts FROM article_ai")}
    assert texts[1] == {"tr": {"title": "Başlık", "summary": "Özet."}, "en": {"title": "Title", "summary": "Summary."}}
    assert texts[2] == {"tr": {"title": "Yalnız", "summary": ""}} and texts[3] == {}
    story = json.loads(c.execute("SELECT ai_texts FROM stories").fetchone()[0])
    assert story == {"tr": {"title": "H", "summary": "Ö", "why": "N"}, "en": {"title": "S", "summary": "Sum", "why": "W"}}
    item = json.loads(c.execute("SELECT texts FROM meeting_items").fetchone()[0])
    assert item == {"tr": {"title": "H", "summary": "Ö", "why": ""}, "en": {"title": "S", "summary": "", "why": ""}}
    assert json.loads(c.execute("SELECT translations FROM article_fulltext").fetchone()[0]) == {"tr": "Metin", "en": "Text"}
    database.close_thread_connection()
