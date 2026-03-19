-- Migration 003: Add last_error column to photos for observability.
-- Populated by the caller when tagging fails; cleared on success.
-- A NULL processed_at + non-NULL last_error means the photo failed and
-- will be retried on the next processor run.

BEGIN;

ALTER TABLE photos ADD COLUMN last_error TEXT;

COMMIT;
