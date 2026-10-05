-- 0013: breaking-news alerts (setting notify.breaking). A story is announced once as breaking news, apart from the
-- "spreading fast" announcement (notified_at).

ALTER TABLE stories ADD COLUMN breaking_notified_at TEXT;
