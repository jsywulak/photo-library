# Session Notes

## What we built

### Database layer
- Created `db/migrations/001_initial_schema.sql` with three tables: `photos`, `tags`, `photo_tags`, with appropriate indexes and cascade deletes
- Created `db/migrate.py` — a migration runner that tracks applied migrations in a `schema_migrations` table, making it safe to re-run
- Added `make migrate` target

### Local dev infrastructure
- Created `.env` for local Postgres connection config
- Created `.env.example` for new contributors
- Created `scripts/db-start.sh` — starts the Docker Postgres container, handles the case where a stopped container already exists
- Created `scripts/db-drop.sh` — drops all tables with a confirmation prompt
- Added Makefile targets: `install`, `db-start`, `db-stop`, `db-shell`, `db-drop`, `migrate`, `process`, `search`, `test`

### Photo processing pipeline
- Created `lambda/processor.py` — single-image Lambda handler: receives an s3_key and image bytes, checks if already processed, calls Anthropic vision API, stores photo and tags
- Created `scripts/run_processor.py` — orchestration script: lists images in a directory, reads each file, calls `process_one` per image, prints live progress, commits on success
- Resolved several issues along the way: images over Anthropic's 5MB limit (added Pillow resize), Claude returning JSON wrapped in markdown fences (added stripping), `max_tokens` too low for large tag responses (bumped to 2048)

### Search
- Created `lambda/searcher.py` — accepts a list of tags, returns matching photos ranked by number of matching tags using a single SQL query
- Created `scripts/run_searcher.py` — runs a hardcoded tag search and prints ranked results

### BDD test suite
- Scaffolded a `behave` test suite with real DB connections and real Anthropic API calls — no mocking
- `features/environment.py` — opens a psycopg2 connection before each scenario, rolls back after (keeps DB clean between tests)
- `features/photo_processing.feature` — 4 scenarios: discover photos, skip existing, save to DB, store tags
- `features/photo_search.feature` — 4 scenarios: no match, any match, ranking, exclusion
- Fixed test isolation issues: temp dirs with UUID-prefixed filenames prevent collisions with committed production data
- All 8 scenarios passing

### Repo hygiene
- `.gitignore` covering `.env`, `images/`, `.claude`, `__pycache__`, etc.
- `CLAUDE.md` with project conventions for future Claude Code sessions
- `README.md` with setup instructions, architecture overview, and useful SQL queries
- Pushed two commits to GitHub

## Decisions made
- Processor does not commit — the caller owns the transaction (keeps test rollback working cleanly)
- Complex shell logic lives in `scripts/`, not inline in the Makefile
- No mocking in BDD tests — tests call real services to catch real integration issues
- Tags stored lowercase, upserted with `ON CONFLICT DO UPDATE`
- Images resized with Pillow before sending to Anthropic if over 5MB


## Usage

Current session                                                                                                                                                                              
███████                                            14% used                                                                                                                                    
Resets 12am (America/New_York)                                                                                                                                                                 

Current week (all models)
█████                                              10% used
Resets 4pm (America/New_York)
