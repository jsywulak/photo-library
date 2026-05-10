ALTER TABLE photos ADD COLUMN state TEXT NOT NULL DEFAULT 'received';
ALTER TABLE photos ADD COLUMN uploaded_at TIMESTAMPTZ;
ALTER TABLE photos ADD COLUMN thumbnailed_at TIMESTAMPTZ;
ALTER TABLE photos ADD COLUMN tagged_at TIMESTAMPTZ;

UPDATE photos SET state = 'tagged', tagged_at = processed_at
WHERE processed_at IS NOT NULL;

UPDATE photos SET state = 'archived'
WHERE archived_at IS NOT NULL;
