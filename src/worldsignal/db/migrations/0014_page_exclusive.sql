-- 0014: the article page itself carries the publisher's "Exclusive" label (read from the page the extension or the
-- worker fetched: keywords, structured data or a label above the headline; fulltext/labels.py).

ALTER TABLE articles ADD COLUMN page_exclusive INTEGER NOT NULL DEFAULT 0;
