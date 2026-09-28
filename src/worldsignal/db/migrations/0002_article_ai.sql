-- 0002: AI enrichment of articles (Turkish title/summary, category, Türkiye relevance).
-- One row per article doubles as queue entry (status = 'pending') and cached result ('done').

CREATE TABLE article_ai (
    article_id        INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    status            TEXT    NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'done', 'failed')),
    priority          REAL    NOT NULL DEFAULT 0,       -- higher runs first
    requested_by_user INTEGER NOT NULL DEFAULT 0 CHECK (requested_by_user IN (0, 1)),
    attempts          INTEGER NOT NULL DEFAULT 0,
    model             TEXT,
    prompt_version    INTEGER,
    title_tr          TEXT,
    summary_tr        TEXT,
    category          TEXT,
    countries         TEXT    NOT NULL DEFAULT '[]',    -- JSON list of ISO 3166-1 alpha-2 codes found in the text
    turkey_relevance  TEXT CHECK (turkey_relevance IS NULL OR turkey_relevance IN ('none', 'indirect', 'direct')),
    turkey_links      TEXT    NOT NULL DEFAULT '[]',    -- JSON list explaining the relevance ("neighbour:GR", "topic:nato")
    issues            TEXT    NOT NULL DEFAULT '[]',    -- JSON list of fidelity warnings
    error_code        TEXT,
    duration_ms       INTEGER,
    queued_at         TEXT    NOT NULL,
    completed_at      TEXT
);
CREATE INDEX idx_article_ai_queue ON article_ai(status, priority DESC);
CREATE INDEX idx_article_ai_category ON article_ai(category);
CREATE INDEX idx_article_ai_turkey ON article_ai(turkey_relevance);

-- Search index for the Turkish AI texts (rowid = article id), normalised in Python like articles_fts.
CREATE VIRTUAL TABLE article_ai_fts USING fts5(
    title_tr,
    summary_tr,
    tokenize = 'unicode61 remove_diacritics 2'
);
CREATE TRIGGER article_ai_fts_delete AFTER DELETE ON article_ai BEGIN
    DELETE FROM article_ai_fts WHERE rowid = old.article_id;
END;
