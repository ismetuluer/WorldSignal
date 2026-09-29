-- 0011: how much the AI writes (setting "ai.depth", 0.13.0).
-- * A story summary also extracts the facts for "my country" (countries, whether the home country is mentioned,
--   the user's topics), so the reports of a summarised story need not each be read ("stories" and "fast").
--   The story's own rating is kept next to its members' ratings; the story gets the higher of them.
-- * "fast": single reports are read ten at a time for their headline, category and facts only (brief = 1);
--   the summary is written when the user asks for it.

ALTER TABLE article_ai ADD COLUMN brief INTEGER NOT NULL DEFAULT 0;

ALTER TABLE stories ADD COLUMN ai_countries TEXT;          -- JSON list; NULL: no facts extracted
ALTER TABLE stories ADD COLUMN ai_topics TEXT NOT NULL DEFAULT '[]';
ALTER TABLE stories ADD COLUMN ai_mentions_home INTEGER NOT NULL DEFAULT 0;
ALTER TABLE stories ADD COLUMN ai_home_relevance TEXT;    -- direct | indirect | none (country.py rules)
ALTER TABLE stories ADD COLUMN ai_home_links TEXT NOT NULL DEFAULT '[]';
