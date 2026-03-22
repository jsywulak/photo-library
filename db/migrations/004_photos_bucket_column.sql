-- Migration 004: Track source bucket for each photo.
-- Adds a 'bucket' column so inbox and processed photos can share the same
-- s3_key without conflict. The unique constraint moves from s3_key alone
-- to (s3_key, bucket).
--
-- Existing rows default to 'photo-tagging-photos' (the original bucket).

BEGIN;

ALTER TABLE photos ADD COLUMN bucket TEXT NOT NULL DEFAULT 'photo-tagging-photos';

ALTER TABLE photos DROP CONSTRAINT photos_s3_key_key;
ALTER TABLE photos ADD CONSTRAINT photos_s3_key_bucket_key UNIQUE (s3_key, bucket);

COMMIT;
