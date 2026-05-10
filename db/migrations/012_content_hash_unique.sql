-- Migration 012: loosen content_hash uniqueness from (content_hash, bucket) to (content_hash) alone.
-- Unblocks Slice 4 (in-place UPDATE during inbox→photos promotion): a single photos
-- row migrates from one bucket to another rather than being DELETEd and re-INSERTed.

BEGIN;

-- Pre-migration cleanup: dedupe rows that share a content_hash across buckets.
-- These accumulated when image_handler's inbox INSERT (Slice 2) raced with the old
-- inbox.process_inbox_photo path (DELETE+let-processor-INSERT). Strategy: keep the
-- photos-bucket row (tagged & canonical), re-point its events from the inbox sibling,
-- then drop the inbox sibling.

UPDATE photo_events pe
   SET photo_id = canonical.id
  FROM photos dup
  JOIN photos canonical
    ON canonical.content_hash = dup.content_hash
   AND canonical.bucket = 'photo-tagging-photos'
   AND canonical.id <> dup.id
 WHERE pe.photo_id = dup.id
   AND dup.bucket = 'photo-tagging-inbox';

DELETE FROM photos
 WHERE id IN (
   SELECT inbox_row.id
     FROM photos inbox_row
     JOIN photos photos_row
       ON photos_row.content_hash = inbox_row.content_hash
      AND photos_row.bucket = 'photo-tagging-photos'
      AND photos_row.id <> inbox_row.id
    WHERE inbox_row.bucket = 'photo-tagging-inbox'
 );

ALTER TABLE photos DROP CONSTRAINT photos_content_hash_bucket_unique;
ALTER TABLE photos ADD CONSTRAINT photos_content_hash_unique UNIQUE (content_hash);

COMMIT;
