-- Migration 002: Replace case-sensitive unique constraint on tags(name) with
-- a case-insensitive one. The application already stores tags in lowercase,
-- but the DB-level constraint was case-sensitive, allowing "Cat" and "cat"
-- to coexist as separate rows.

BEGIN;

-- Drop the explicit index and the implicit one created by the UNIQUE column
-- constraint (named tags_name_key by Postgres convention).
DROP INDEX idx_tags_name;
ALTER TABLE tags DROP CONSTRAINT tags_name_key;

-- New case-insensitive unique index replaces both.
CREATE UNIQUE INDEX idx_tags_name_lower ON tags (LOWER(name));

COMMIT;
