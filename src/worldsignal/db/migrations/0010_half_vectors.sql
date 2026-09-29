-- 0010: story-matching vectors are stored as 16-bit floats (half the space). Measured on 6,000 real vectors: the
-- largest change of a similarity was 0.0001, and 4 of 27,122 pairs above the merge threshold (0.55) changed side.
-- Vectors written before stay 32-bit ('f4') until they are removed (they are kept only a few days).

ALTER TABLE article_embeddings ADD COLUMN dtype TEXT NOT NULL DEFAULT 'f4';
