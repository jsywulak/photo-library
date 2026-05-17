-- Tag provenance: record which model produced auto-generated tags
-- and whether each photo_tags row was added by the AI or by a user.

ALTER TABLE photos
  ADD COLUMN IF NOT EXISTS tagged_by_model TEXT;

ALTER TABLE photo_tags
  ADD COLUMN IF NOT EXISTS added_by TEXT NOT NULL DEFAULT 'ai',
  ADD COLUMN IF NOT EXISTS added_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
