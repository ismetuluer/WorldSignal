-- 0001: sources, feeds, articles, full-text index, settings.
-- All timestamps are UTC ISO-8601 strings ("2026-09-27T07:33:19Z"), which sort correctly as text.

-- A source is a news outlet (e.g. BBC). One outlet can publish several feeds.
CREATE TABLE sources (
    id              INTEGER PRIMARY KEY,
    slug            TEXT    NOT NULL UNIQUE,
    name            TEXT    NOT NULL,
    homepage        TEXT,
    catalog_group   TEXT    NOT NULL,            -- western | agency | middle_east | russia_ukraine | asia | europe | turkey | other
    owner           TEXT,                        -- media group; outlets sharing an owner count as one independent source
    region          TEXT    NOT NULL,
    language        TEXT    NOT NULL,            -- ISO 639-1
    reliability     REAL    NOT NULL DEFAULT 1.0 CHECK (reliability >= 0 AND reliability <= 2),
    enabled         INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    paywalled       INTEGER NOT NULL DEFAULT 0 CHECK (paywalled IN (0, 1)),
    note            TEXT,
    origin          TEXT    NOT NULL DEFAULT 'catalog' CHECK (origin IN ('catalog', 'user')),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

CREATE TABLE feeds (
    id                   INTEGER PRIMARY KEY,
    source_id            INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    url                  TEXT    NOT NULL UNIQUE,
    label                TEXT,
    enabled              INTEGER NOT NULL DEFAULT 1 CHECK (enabled IN (0, 1)),
    verified             INTEGER NOT NULL DEFAULT 1 CHECK (verified IN (0, 1)),
    fetch_interval_min   INTEGER NOT NULL DEFAULT 15 CHECK (fetch_interval_min BETWEEN 5 AND 1440),
    etag                 TEXT,
    last_modified        TEXT,
    last_attempt_at      TEXT,
    last_success_at      TEXT,
    next_fetch_at        TEXT,
    last_status          TEXT    NOT NULL DEFAULT 'pending'
                         CHECK (last_status IN ('pending', 'ok', 'not_modified', 'error')),
    last_error_code      TEXT,                   -- machine code, translated by the UI
    last_error_detail    TEXT,                   -- technical detail for the log / tooltip
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_item_count      INTEGER,
    last_new_count       INTEGER,
    created_at           TEXT    NOT NULL
);
CREATE INDEX idx_feeds_source ON feeds(source_id);
CREATE INDEX idx_feeds_due ON feeds(enabled, next_fetch_at);

CREATE TABLE articles (
    id             INTEGER PRIMARY KEY,
    source_id      INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    feed_id        INTEGER REFERENCES feeds(id) ON DELETE SET NULL,
    dedupe_key     TEXT    NOT NULL,             -- canonical link or feed GUID
    url            TEXT    NOT NULL,
    title          TEXT    NOT NULL,
    summary        TEXT    NOT NULL DEFAULT '',
    author         TEXT,
    language       TEXT,
    published_at   TEXT,                         -- as reported by the feed (may be missing)
    first_seen_at  TEXT    NOT NULL,
    sort_at        TEXT    NOT NULL,             -- published_at, clamped to first_seen_at if missing/future
    UNIQUE (source_id, dedupe_key)
);
CREATE INDEX idx_articles_sort ON articles(sort_at DESC);
CREATE INDEX idx_articles_source_sort ON articles(source_id, sort_at DESC);

-- Full-text index. rowid = articles.id. Text is stored pre-normalised by
-- worldsignal.textnorm.fold_for_search (Turkish-aware), so it is written from
-- Python rather than by triggers. Deletion is handled by a trigger so that
-- cascaded deletes never leave orphans.
CREATE VIRTUAL TABLE articles_fts USING fts5(
    title,
    summary,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER articles_fts_delete AFTER DELETE ON articles BEGIN
    DELETE FROM articles_fts WHERE rowid = old.id;
END;

CREATE TABLE settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,                    -- JSON
    updated_at TEXT NOT NULL
);
