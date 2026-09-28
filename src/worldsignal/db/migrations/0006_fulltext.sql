-- 0006: full text of articles (phase 5).
--
-- How a source's full text is fetched:
--   off     - never (RSS summary and link only)
--   http    - a plain download of the article page (free sites)
--   browser - the user's browser with their subscription session (paid sites)
-- Paid sources start 'off': the user turns 'browser' on for the ones they subscribe to.
ALTER TABLE sources ADD COLUMN fulltext_mode TEXT NOT NULL DEFAULT 'http'
    CHECK (fulltext_mode IN ('off', 'http', 'browser'));
-- After a bot check or repeated refusals the site is left alone until this time.
ALTER TABLE sources ADD COLUMN fulltext_paused_until TEXT;
UPDATE sources SET fulltext_mode = 'off' WHERE paywalled = 1;

-- One row per article: queue entry, result and (on request) translations.
CREATE TABLE article_fulltext (
    article_id        INTEGER PRIMARY KEY REFERENCES articles(id) ON DELETE CASCADE,
    status            TEXT    NOT NULL DEFAULT 'pending'
                      CHECK (status IN ('pending', 'done', 'failed', 'blocked')),
    reason            TEXT    NOT NULL DEFAULT 'auto' CHECK (reason IN ('auto', 'notebook', 'user')),
    priority          REAL    NOT NULL DEFAULT 0,
    attempts          INTEGER NOT NULL DEFAULT 0,
    method            TEXT,                 -- http | browser (what was used)
    text              TEXT,                 -- extracted article text (local use only, never in outputs)
    chars             INTEGER,
    error_code        TEXT,                 -- paywall | bot_check | http_403 | not_article | timeout | browser_missing ...
    queued_at         TEXT    NOT NULL,
    attempted_at      TEXT,                 -- last attempt (rate limiting per site)
    fetched_at        TEXT,
    -- Translations of the full text, made on request.
    translate_status  TEXT    CHECK (translate_status IS NULL OR translate_status IN ('pending', 'done', 'failed')),
    text_tr           TEXT,
    text_en           TEXT,
    translated_at     TEXT
);
CREATE INDEX idx_fulltext_queue ON article_fulltext(status, priority DESC);
CREATE INDEX idx_fulltext_attempted ON article_fulltext(attempted_at);
CREATE INDEX idx_fulltext_translate ON article_fulltext(translate_status);
