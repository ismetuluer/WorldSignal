-- 0005: English next to Turkish for every AI text (decision 2026-09-27: the UI shows the
-- language of the interface, the other one is one click away; outputs can be made in either).
-- Rows written before this version have no English yet; the workers fill them in the
-- background (after new work), see AiRepository.next_job and StoryRepository.next_story_job.

ALTER TABLE article_ai ADD COLUMN title_en TEXT;
ALTER TABLE article_ai ADD COLUMN summary_en TEXT;

ALTER TABLE stories ADD COLUMN ai_title_en TEXT;
ALTER TABLE stories ADD COLUMN ai_summary_en TEXT;
ALTER TABLE stories ADD COLUMN ai_why_en TEXT;

ALTER TABLE meeting_items ADD COLUMN title_en TEXT;
ALTER TABLE meeting_items ADD COLUMN summary_en TEXT;
ALTER TABLE meeting_items ADD COLUMN why_en TEXT;
