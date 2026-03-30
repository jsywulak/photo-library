-- Migration 009: Add UNIQUE(content_hash, bucket) constraint.
-- Applied AFTER migrate_to_hashes.py backfills all rows.
-- Prevents the same photo content from being stored twice in the same bucket.
-- Allows the same photo to coexist in inbox and photos bucket during processing.

ALTER TABLE photos
  ADD CONSTRAINT photos_content_hash_bucket_unique UNIQUE (content_hash, bucket);
