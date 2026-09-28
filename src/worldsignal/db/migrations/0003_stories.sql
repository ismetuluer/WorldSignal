-- 0003: embeddings, stories (clusters of articles about the same event) and story AI.

-- One L2-normalised float32 vector per article (little-endian bytes).
CREATE TABLE article_embeddings (
    article_id  INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    model       TEXT    NOT NULL,
    vector      BLOB    NOT NULL,
    created_at  TEXT    NOT NULL
);

CREATE TABLE stories (
    id                  INTEGER PRIMARY KEY,
    first_seen_at       TEXT    NOT NULL,            -- earliest member sort_at
    last_seen_at        TEXT    NOT NULL,            -- latest member sort_at
    article_count       INTEGER NOT NULL DEFAULT 0,
    source_count        INTEGER NOT NULL DEFAULT 0,  -- independent sources (one per media group)
    score               REAL    NOT NULL DEFAULT 0,  -- 0..100
    score_parts         TEXT    NOT NULL DEFAULT '{}', -- JSON: components and explanation tags
    turkey_relevance    TEXT    NOT NULL DEFAULT 'none' CHECK (turkey_relevance IN ('none', 'indirect', 'direct')),
    category            TEXT,                          -- most common member category (or story AI)
    representative_id   INTEGER REFERENCES articles(id) ON DELETE SET NULL,
    -- Story-level AI (Turkish title, 3-5 sentence summary, meeting pitch).
    ai_status           TEXT    CHECK (ai_status IS NULL OR ai_status IN ('pending', 'done', 'failed')),
    ai_attempts         INTEGER NOT NULL DEFAULT 0,
    ai_title_tr         TEXT,
    ai_summary_tr       TEXT,
    ai_why              TEXT,                          -- one sentence: why propose it in the meeting
    ai_issues           TEXT    NOT NULL DEFAULT '[]',
    ai_article_count    INTEGER,                       -- members when the AI text was written
    ai_model            TEXT,
    ai_error            TEXT,
    ai_completed_at     TEXT,
    created_at          TEXT    NOT NULL,
    updated_at          TEXT    NOT NULL
);
CREATE INDEX idx_stories_last_seen ON stories(last_seen_at DESC);
CREATE INDEX idx_stories_score ON stories(score DESC);
CREATE INDEX idx_stories_ai ON stories(ai_status, score DESC);

CREATE TABLE story_articles (
    article_id   INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    story_id     INTEGER NOT NULL REFERENCES stories(id) ON DELETE CASCADE,
    similarity   REAL,                                -- to the closest member when it joined
    assigned_by  TEXT    NOT NULL CHECK (assigned_by IN ('auto', 'user')),
    assigned_at  TEXT    NOT NULL
);
CREATE INDEX idx_story_articles_story ON story_articles(story_id);
