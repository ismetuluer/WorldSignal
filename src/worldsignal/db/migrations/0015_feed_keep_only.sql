-- 0015: a feed may keep only some of its items. "exclusive": only reports whose own headline carries the publisher's
-- exclusive label (the Reuters exclusives, found through Bing News searches that also return other things).

ALTER TABLE feeds ADD COLUMN keep_only TEXT;
