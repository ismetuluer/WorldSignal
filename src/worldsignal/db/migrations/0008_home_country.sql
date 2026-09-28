-- 0008: relevance to the user's country instead of a fixed Türkiye (0.9.0).
-- The relevance now lives on the article and is decided by country.py from what the AI found (countries, topics)
-- and the country's name in the text. The AI's findings are kept so it can be recomputed whenever the user's
-- country or its related countries/topics/keywords change (settings key "home.applied").
-- Since this version the columns article_ai.turkey_relevance / turkey_links are no longer read; stories.turkey_relevance
-- keeps its name but means "relevance to the user's country".
ALTER TABLE articles ADD COLUMN home_relevance TEXT NOT NULL DEFAULT 'none'
    CHECK (home_relevance IN ('none', 'indirect', 'direct'));
ALTER TABLE articles ADD COLUMN home_links TEXT NOT NULL DEFAULT '[]';  -- JSON: "home_mentioned", "neighbour:GR", "related:KZ", "topic:nato"
CREATE INDEX idx_articles_home ON articles(home_relevance);

-- The facts the AI found, kept so relevance can be recomputed without asking the AI again.
ALTER TABLE article_ai ADD COLUMN topics TEXT NOT NULL DEFAULT '[]';
ALTER TABLE article_ai ADD COLUMN mentions_turkey INTEGER NOT NULL DEFAULT 0;
UPDATE article_ai
   SET topics = (SELECT json_group_array(substr(j.value, 7)) FROM json_each(article_ai.turkey_links) j
                  WHERE j.value LIKE 'topic:%')
 WHERE turkey_links LIKE '%topic:%';
UPDATE article_ai SET mentions_turkey = 1 WHERE turkey_links LIKE '%turkey_mentioned%';
