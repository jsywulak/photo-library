# Photo Tagger — Claude Code Guide

## Common Commands
- `make install` — install Python dependencies
- `make db-start` / `make db-stop` — start/stop local Postgres container
- `make db-shell` — open a psql session
- `make db-drop` — drop all tables (prompts for confirmation)
- `make migrate` — apply pending migrations
- `make process` — run the processor against `images/` and commit results
- `make test` — run BDD tests

## Architecture
- `lambda/processor.py` — core tagging logic, called by Lambda handler
- `db/migrations/` — SQL migration files, named `NNN_description.sql`
- `features/` — BDD tests using behave
- `scripts/` — shell scripts for local dev operations

## Conventions
- Complex shell logic goes in `scripts/`, not inline in the Makefile
- The processor never commits — the caller owns the transaction
- BDD tests use real services (Postgres, Anthropic API) — no mocking
- Tags are stored lowercase

## Environment
- Requires `.env` with `DATABASE_URL` and `ANTHROPIC_API_KEY`
- Local Postgres runs in Docker (`phototagger-db` container)
- Sample images live in `images/` (gitignored — must be real JPEGs)
