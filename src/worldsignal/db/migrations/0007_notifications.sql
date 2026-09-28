-- 0007: Windows notifications for important stories that spread quickly (phase 7).
-- A story is announced at most once; this records when.
ALTER TABLE stories ADD COLUMN notified_at TEXT;
