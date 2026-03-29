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

## Architecture
- `lambda/processor.py` — core tagging logic, called by `lambda/handler.py`
- `lambda/searcher.py` — search logic, called by `lambda/searcher_handler.py`
- `db/migrations/` — SQL migration files, named `NNN_description.sql`
- `features/` — BDD tests using behave
  - `features/steps/` — step definitions
  - `features/environment.py` — DB connection lifecycle and test teardown
- `scripts/` — shell scripts for local dev operations
- `infra/` — CloudFormation templates for Lambda and S3 resources

## Conventions
- Complex shell logic goes in `scripts/`, not inline in the Makefile
- The processor never commits — the caller owns the transaction
- BDD tests use real services (Postgres, Anthropic API) — no mocking
- Frontend BDD tests use Playwright with mocked Lambda URLs via `page.route()`
- Tags are stored lowercase, upserted with `ON CONFLICT (LOWER(name)) DO UPDATE` — the tags table uses an expression index on `LOWER(name)`, not a column-level UNIQUE constraint
- New features should have a failing BDD test written before implementation (TDD)

## Environment
- Requires `.env` with `DATABASE_URL`, `ANTHROPIC_API_KEY`, and `NEON_DATABASE_URL`
- `ANTHROPIC_MODEL` can be set to override the default model (`claude-opus-4-6`)
- Local Postgres runs in Docker (`phototagger-db` container)
- Sample images live in `images/` (gitignored — must be real JPEGs)
- `NEON_DATABASE_URL` contains `&` characters — always quote it in shell commands (the Makefile handles this)
- `frontend/config.js` is gitignored — use `config.example.js` as a template
