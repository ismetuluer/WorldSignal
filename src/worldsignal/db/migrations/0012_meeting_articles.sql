-- 0012: a single report can be put on the meeting list (not only a whole story).
-- An item has either a story_id (a story) or an article_id (one report); the snapshot columns work the same way.
-- A story item that lost its story keeps story_id NULL and article_id NULL ("story gone"); a report item whose report
-- was deleted keeps its snapshot the same way.

ALTER TABLE meeting_items ADD COLUMN article_id INTEGER REFERENCES articles(id) ON DELETE SET NULL;
CREATE UNIQUE INDEX idx_meeting_article ON meeting_items(day, article_id) WHERE article_id IS NOT NULL;
