-- Migration 001: Initial schema
-- Tables: photos, tags, photo_tags

BEGIN;

CREATE TABLE photos (
    id          BIGSERIAL PRIMARY KEY,
    s3_key      TEXT        NOT NULL UNIQUE,
    processed_at TIMESTAMPTZ
);

CREATE TABLE tags (
    id   BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE photo_tags (
    photo_id BIGINT NOT NULL REFERENCES photos(id) ON DELETE CASCADE,
    tag_id   BIGINT NOT NULL REFERENCES tags(id)   ON DELETE CASCADE,
    PRIMARY KEY (photo_id, tag_id)
);

-- Indexes
CREATE INDEX idx_photo_tags_tag_id  ON photo_tags(tag_id);
CREATE INDEX idx_tags_name          ON tags(name);
CREATE INDEX idx_photos_processed_at ON photos(processed_at);

COMMIT;
