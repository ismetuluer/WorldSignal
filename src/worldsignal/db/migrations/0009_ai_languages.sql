-- 0009: AI texts in the user's languages (setting "ai.languages", 0.11.0) instead of fixed Turkish + English.
-- Every AI text now lives in one JSON column per row, keyed by language:
--   article_ai.texts      {"tr": {"title": …, "summary": …}, "pt": {…}}
--   stories.ai_texts      {"tr": {"title": …, "summary": …, "why": …}, …}
--   meeting_items.texts   {"tr": {"title": …, "summary": …, "why": …}, …}   (meeting_items.title stays: the
--                         headline shown when there is no AI text, e.g. the original title)
--   article_fulltext.translations  {"tr": "…", …}
-- The Turkish and English texts written so far are copied over. The old *_tr / *_en columns are no longer read or
-- written (SQLite keeps them; dropping columns would rebuild these tables for nothing).

ALTER TABLE article_ai ADD COLUMN texts TEXT NOT NULL DEFAULT '{}';
UPDATE article_ai SET texts = json_patch(
        CASE WHEN title_tr IS NOT NULL
             THEN json_object('tr', json_object('title', title_tr, 'summary', COALESCE(summary_tr, ''))) ELSE '{}' END,
        CASE WHEN title_en IS NOT NULL
             THEN json_object('en', json_object('title', title_en, 'summary', COALESCE(summary_en, ''))) ELSE '{}' END)
 WHERE title_tr IS NOT NULL OR title_en IS NOT NULL;

ALTER TABLE stories ADD COLUMN ai_texts TEXT NOT NULL DEFAULT '{}';
UPDATE stories SET ai_texts = json_patch(
        CASE WHEN ai_title_tr IS NOT NULL
             THEN json_object('tr', json_object('title', ai_title_tr, 'summary', COALESCE(ai_summary_tr, ''),
                                                'why', COALESCE(ai_why, ''))) ELSE '{}' END,
        CASE WHEN ai_title_en IS NOT NULL
             THEN json_object('en', json_object('title', ai_title_en, 'summary', COALESCE(ai_summary_en, ''),
                                                'why', COALESCE(ai_why_en, ''))) ELSE '{}' END)
 WHERE ai_title_tr IS NOT NULL OR ai_title_en IS NOT NULL;

ALTER TABLE meeting_items ADD COLUMN texts TEXT NOT NULL DEFAULT '{}';
UPDATE meeting_items SET texts = json_patch(
        json_object('tr', json_object('title', title, 'summary', COALESCE(summary, ''), 'why', COALESCE(why, ''))),
        CASE WHEN title_en IS NOT NULL
             THEN json_object('en', json_object('title', title_en, 'summary', COALESCE(summary_en, ''),
                                                'why', COALESCE(why_en, ''))) ELSE '{}' END);

ALTER TABLE article_fulltext ADD COLUMN translations TEXT NOT NULL DEFAULT '{}';
UPDATE article_fulltext SET translations = json_patch(
        CASE WHEN text_tr IS NOT NULL THEN json_object('tr', text_tr) ELSE '{}' END,
        CASE WHEN text_en IS NOT NULL THEN json_object('en', text_en) ELSE '{}' END)
 WHERE translate_status = 'done';
