-- 0004: notebook — story notes, the daily meeting list and free day notes.
--
-- Days are the user's local calendar dates (YYYY-MM-DD). Rows that point at a story
-- keep a copy of its headline (and, for meeting items, summary, pitch and sources):
-- stories can be merged, re-summarised or removed, but what was written or proposed
-- that day must stay readable in the notebook.

CREATE TABLE story_notes (
    id          INTEGER PRIMARY KEY,
    story_id    INTEGER UNIQUE REFERENCES stories(id) ON DELETE SET NULL,
    day         TEXT    NOT NULL,              -- local day the note was started (notebook filing)
    title       TEXT    NOT NULL,              -- story headline when last saved
    body        TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL
);
CREATE INDEX idx_story_notes_day ON story_notes(day);

CREATE TABLE meeting_items (
    id          INTEGER PRIMARY KEY,
    day         TEXT    NOT NULL,
    story_id    INTEGER REFERENCES stories(id) ON DELETE SET NULL,
    position    INTEGER NOT NULL,
    comment     TEXT    NOT NULL DEFAULT '',   -- the user's one-line pitch
    -- Snapshot of the story (refreshed while it is today's list).
    title       TEXT    NOT NULL,
    summary     TEXT,
    why         TEXT,
    category    TEXT,
    sources     TEXT    NOT NULL DEFAULT '[]', -- JSON [{name, url}]
    created_at  TEXT    NOT NULL,
    updated_at  TEXT    NOT NULL,
    UNIQUE (day, story_id)
);
CREATE INDEX idx_meeting_day ON meeting_items(day, position);

CREATE TABLE day_notes (
    day         TEXT PRIMARY KEY,
    body        TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
