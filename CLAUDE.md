# Photo Tagger — Claude Code Guide

## Common Commands
- `make install` — install Python dependencies
- `make install-playwright` — download Chromium for frontend tests
- `make local-db-start` / `make local-db-stop` — start/stop local Postgres container
- `make local-db-shell` — open a psql session
- `make local-db-drop` — drop all tables (prompts for confirmation)
- `make local-migrate` — apply pending migrations locally
- `make neon-migrate` — apply pending migrations to Neon
- `make process` — run the processor against `images/` and commit results
- `make test` — run unit tests and all BDD tests (local, frontend, and infrastructure)
- `make test-local` — run local BDD tests only (no AWS, no Playwright)
- `make test-unit` — run unit tests (no external dependencies)
- `make test-frontend` — run Playwright frontend tests
- `make test-infrastructure` — run BDD tests against live AWS (Lambda, Neon, S3)
- `make neon-stats` — show photo/tag counts and top 5 tags from Neon
- `make neon-tags` — show all tag counts from Neon
- `make neon-clean-tags` — delete orphaned tags from Neon
- `make neon-reconcile` — diff S3 vs photos table, write `orphan_s3_only`/`orphan_db_only` events

## Architecture
- `lambda/processor.py` — core tagging logic, called by `lambda/handler.py`
- `lambda/searcher.py` — search logic, called by `lambda/searcher_handler.py`
- `lambda/inbox.py` — inbox listing/promotion/archive, called by `lambda/inbox_handler.py`
- `lambda/image_handler.py` — fires on upload-bucket S3 events; computes hash, thumbnails, copies to inbox, INSERTs the inbox `photos` row
- `lambda/thumbnailer.py` / `lambda/thumbnailer_handler.py` — generates 400×400 WebP thumbnails
- `lambda/exif.py` — shared `extract_captured_at()` helper used by processor + image_handler
- `lambda/utils.py` — `get_required_env()`, `thumbnail_key()`, and `record_event()` (the shared photo_events writer used by every Lambda)
- `db/migrations/` — SQL migration files, named `NNN_description.sql`
- `features/` — BDD tests using behave
  - `features/steps/` — step definitions
  - `features/environment.py` — DB connection lifecycle and test teardown
- `scripts/` — shell scripts for local dev operations; `package-*.sh` builds Lambda zips, `deploy-*.sh` runs CloudFormation
- `infra/` — CloudFormation templates for Lambda and S3 resources

## Conventions
- Complex shell logic goes in `scripts/`, not inline in the Makefile
- The processor never commits — the caller owns the transaction. `record_error()` is the explicit exception: it opens its own transaction after the caller's rollback so failure-state writes survive
- BDD tests use real services (Postgres, Anthropic API) — no mocking
- Frontend BDD tests use Playwright with mocked Lambda URLs via `page.route()`
- Tags are stored lowercase, upserted with `ON CONFLICT (LOWER(name)) DO UPDATE` — the tags table uses an expression index on `LOWER(name)`, not a column-level UNIQUE constraint
- New features should have a failing BDD test written before implementation (TDD)
- Every Lambda action writes a `photo_events` row via `utils.record_event()` (event types: `received`, `thumbnail_created`, `thumbnail_skipped`, `promoted`, `tagging_started`, `tagged`, `tag_failed`, `tag_added`, `tag_removed`, `archived`, plus `orphan_s3_only` / `orphan_db_only` written by `scripts/reconcile_pipeline.py`). Image_handler and thumbnailer wrap their DB writes in try/except so a Neon outage cannot break upload/thumbnail generation
- `photos.state` (`received` / `tagged` / `failed` / `archived`) is the canonical lifecycle column. `processed_at` is kept as a parallel alias of `tagged_at` until a future migration drops it. `uploaded_at` is set by image_handler on the initial INSERT; `thumbnailed_at` is set by thumbnailer_handler after a successful WebP write
- Tag provenance lives on the tables: `photos.tagged_by_model` records the Anthropic model that produced the tags; `photo_tags.added_by` is `'ai'` (processor) or `'user'` (searcher `/add-tags`); `photo_tags.added_at` defaults to `NOW()`
- S3 object metadata is the out-of-band audit trail: every photo/inbox object carries `content-hash`, `original-filename`, and `pipeline-stage` (`received` → `awaiting_review` → `tagged`); tagged objects additionally carry `tagged-by-model`. Stage transitions use `CopyObject` with `MetadataDirective='REPLACE'` (so re-read and re-pass every key — REPLACE doesn't merge)
- Async Lambdas (processor v2, image_handler, thumbnailer) have dedicated SQS DLQs wired via `AWS::Lambda::EventInvokeConfig` with `MaximumRetryAttempts=0` for fail-fast. URLs surface as `*DLQUrl` stack outputs; `.env` consumers (the `@infrastructure` DLQ test) read `PROCESSOR_V2_DLQ_URL` / `IMAGE_LAMBDA_DLQ_URL` / `THUMBNAILER_DLQ_URL`
- Lambda packaging: each Lambda has its own `requirements-<name>-lambda.txt`; the `package-*.sh` script copies only the Lambda's source files plus shared modules (`utils.py`, `exif.py`) into the build dir. `image_handler` and `thumbnailer` bundle `psycopg2-binary` because `utils.py` imports `psycopg2.extras.Json` at module load
- `features/environment.py` deletes `photo_events` rows by `s3_key` before the photos delete in teardown — `ON DELETE CASCADE` only handles events whose `photo_id` is set, but image_handler/thumbnailer events are written before the photos row exists

## Environment
- Requires `.env` with `DATABASE_URL`, `ANTHROPIC_API_KEY`, and `NEON_DATABASE_URL`
- `ANTHROPIC_MODEL` can be set to override the default model (`claude-opus-4-6`)
- Local Postgres runs in Docker (`phototagger-db` container)
- Sample images live in `images/` (gitignored — must be real JPEGs)
- `NEON_DATABASE_URL` contains `&` characters — always quote it in shell commands (the Makefile handles this)
- `frontend/config.js` is gitignored — use `config.example.js` as a template
