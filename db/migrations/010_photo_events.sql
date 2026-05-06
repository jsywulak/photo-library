CREATE TABLE photo_events (
  id BIGSERIAL PRIMARY KEY,
  photo_id BIGINT REFERENCES photos(id) ON DELETE CASCADE,
  s3_key TEXT NOT NULL,
  bucket TEXT NOT NULL,
  event_type TEXT NOT NULL,
  actor TEXT NOT NULL,
  details JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_photo_events_photo_id ON photo_events(photo_id);
CREATE INDEX idx_photo_events_created_at ON photo_events(created_at);
