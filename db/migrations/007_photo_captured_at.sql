-- Migration 007: Store EXIF capture timestamp for inbox photos.
-- Enables sorting inbox by when the photo was taken rather than when it arrived in S3.
-- NULL means no EXIF data was available; those photos sort last.

BEGIN;

ALTER TABLE photos ADD COLUMN captured_at TIMESTAMPTZ;
CREATE INDEX idx_photos_captured_at ON photos(captured_at);

COMMIT;
