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

---

## Session 2 — AWS deployment, frontend, and custom domain

### Lambda Function URL
- Fixed a 403 on the searcher Function URL caused by an AWS change (October 2025): public Function URLs now require both `lambda:InvokeFunctionUrl` AND `lambda:InvokeFunction` permissions. Added `SearcherFunctionInvokePermission` to `infra/searcher.yaml`.
- Added CORS preflight handling (`OPTIONS` → 200) to `searcher_handler.py` so browsers can make cross-origin requests from any origin.
- Added API key auth via `x-api-key` header; key lives in `.env` and is passed as a CloudFormation `NoEcho` parameter.

### Presigned URLs
- Updated `lambda/searcher.py` to accept an optional `s3_client` and `bucket`, and generate a presigned S3 URL (1hr expiry) for each result.
- Updated `infra/searcher.yaml` to give the searcher role `s3:GetObject` on the photos bucket and pass `S3_BUCKET` as an env var.
- Local `photo_search` BDD tests still work — `s3_client`/`bucket` are optional, URL generation is skipped when absent.

### `/tags` endpoint
- Added `GET /tags` route to `searcher_handler.py` — returns 20 random tag names from the database.
- Added `get_random_tags()` to `searcher.py` using `ORDER BY RANDOM() LIMIT 20`.
- BDD tests: returns a list of strings, at most 20 items, 401 with wrong key.

### Frontend
- Built `frontend/index.html` — single-file static app: tag chip input, debounced search-as-you-type, responsive photo grid, lightbox.
- `frontend/config.js` (gitignored) holds `SEARCHER_URL` and `API_KEY`; `config.example.js` is committed as a template.
- On load, fetches 20 random tags and displays them as clickable suggestion pills; already-active tags dim.
- Added `make deploy-frontend` target — uploads `index.html` and `config.js` to the frontend S3 bucket.

### S3 static hosting + custom domain
- Created `infra/frontend.yaml` — S3 bucket with public read policy and website hosting enabled.
- Added Route 53 CNAME record for `lax.jsywulak.com` → S3 website endpoint. (A alias record didn't work — Route 53 can't resolve aliases to S3 website endpoints because they're themselves CNAMEs.)
- `FRONTEND_DOMAIN` and `HOSTED_ZONE_ID` live in `.env`; no domain or zone ID hardcoded in committed files.
- Added `make neon-tags` — lists all tags with photo counts, sorted by most common.

### BDD test additions
- Infrastructure: frontend bucket has website hosting enabled; website URL returns 200.
- Searcher: Function URL reachable with valid key (HTTP test, not boto3); 401 on wrong key; presigned URL accessible from S3; `/tags` endpoint returns list of strings ≤ 20.
- Total: 22 scenarios passing.

### Decisions made
- CORS handled entirely in Lambda response headers — no CloudFormation-level CORS config (it caused unexpected 403s).
- CNAME record for subdomain instead of Route 53 alias (alias doesn't work for S3 website endpoints).
- Domain and hosted zone ID kept out of committed files — passed via `.env`.

(I did come close to hitting the session limit before I ran out -- debugging the invoke function stuff was token-expensive.)

Current session
███                                                6% used
Resets 1am (America/New_York)

Current week (all models)
█████▌                                             11% used
Resets Mar 1 at 4pm (America/New_York)

---

## Session 3 — Code quality, security, processor improvements, and test coverage

### Code quality & setup
- Pinned all dependency versions in `requirements.txt`
- Moved hardcoded `claude-opus-4-6` model to an `ANTHROPIC_MODEL` env var with a sensible default
- Created `.env.example` documenting all required variables (local and AWS)
- Added `make help`, `make clean`, `make test-unit`, `make test-frontend`, `make install-playwright` targets
- Fixed `make neon-migrate` and `make neon-tags` — the `&` in the Neon URL was being interpreted as a shell background operator; fixed by quoting

### Security
- Audited git history for secrets — found `frontend/config.js` (containing the API key) was tracked
- Removed it from git tracking with `git rm --cached` and added it to `.gitignore`
- Rotated the exposed API key

### Database migrations
- `002_tag_case_constraint.sql` — replaced the column-level `UNIQUE` constraint on `tags.name` with an expression index on `LOWER(name)` for true case-insensitive uniqueness
- `003_photo_error_tracking.sql` — added `last_error TEXT` column to `photos` so failed processing attempts are recorded
- Fixed all `ON CONFLICT (name)` references across the codebase to `ON CONFLICT (LOWER(name))` after the migration broke them (processor.py, photo_search_steps.py, photo_processing_steps.py, searcher_lambda_steps.py)

### Error tracking
- Updated `lambda/handler.py` and `scripts/run_processor.py` to record errors to `last_error` after a rollback, using a fresh transaction so the error survives even when the main transaction fails

### Processor improvements
- Added a large curated `_PREFERRED_TAGS` list (~280 tags) to the prompt so the model uses consistent terminology
- Built `_build_prompt()` to construct the full prompt dynamically from that list
- Added retry logic: photos with a `NULL` processed_at are retried rather than skipped
- Added NEF/non-JPEG rejection — `process_one()` now returns `"unsupported"` for anything that isn't `.jpg`/`.jpeg`

### Unit tests
- Added `tests/test_processor.py` with 4 unit tests for `_prepare_image`: passthrough under limit, resize when over limit, corrupt image handling, image too small to resize

### Frontend BDD tests
- Added `features/frontend.feature` with 11 scenarios covering: initial state, tag suggestions, chip add/remove via click and keyboard, search results grid, empty results message, lightbox open/close (× button, Escape, backdrop click)
- Added `features/steps/frontend_steps.py` using Playwright with Lambda URL mocking via `page.route()`
- Updated `features/environment.py` with browser lifecycle management for `@frontend` scenarios

### Infrastructure
- Fixed IAM policy in `infra/processor.yaml` to include `s3:ListBucket` (was causing AccessDenied errors in CloudWatch)
- Added `ReservedConcurrentExecutions: 10` to the processor Lambda to prevent runaway API costs
- Added a BDD scenario to `features/infrastructure.feature` validating the concurrency limit is in place

### NEF file cleanup
- Queried Neon for all non-JPEG files in the database and deleted them
- Added a BDD scenario for NEF rejection before implementing the feature (TDD)
- Deployed the fix

### Database utilities
- Added `make neon-clean-tags` to delete orphaned tags from Neon
- Added `make neon-stats` to show photo/tag counts and top 5 tags
- Fixed `after_scenario` in `environment.py` to clean up orphaned tags after infrastructure test teardowns, so test runs no longer pollute the live site

### Decisions made
- TDD workflow for NEF rejection: wrote failing BDD test first, then implemented
- `ReservedConcurrentExecutions: 10` chosen to rate-limit Lambda invocations without blocking local processing scripts
- Orphaned tag cleanup runs in the same transaction as photo deletion during teardown — atomic and safe

  Current session                                                                                                                                                                                
  ██████████████▌                                    29% used                                                           
  Resets 11pm (America/New_York)                                                                                                                                                                 
                                                                                                                                                                                                 
  Current week (all models)
  ██                                                 4% used
  Resets Mar 25 at 6pm (America/New_York)

---

## Session 4 — Tech debt, security hardening, and data integrity tooling

### Security
- **Removed insecure Lambda permission** — `infra/searcher.yaml` had `lambda:InvokeFunction` with `Principal: "*"` (no conditions), allowing anyone to invoke the function directly, bypassing the API key. Replaced with the correct two-permission pattern for `AuthType: NONE` Function URLs: `lambda:InvokeFunctionUrl` + `lambda:InvokeFunction` with `lambda:InvokedViaFunctionUrl: true` condition.
- Went through a CloudFormation ghost resource cycle (CFN thought the old permission existed but it didn't) — had to remove, deploy, re-add, deploy.
- **Gitleaks secret scanning** — installed as a pre-commit hook via `scripts/install-hooks.sh`. One historical finding (already-rotated API key) acknowledged in `.gitleaksignore`.

### Bug fixes
- **`_prepare_image` base64 threshold** — the resize check compared raw file size against 5 MB, but Anthropic's limit applies to the base64-encoded size (~33% larger). Images in the 3.75–5 MB raw range passed the check but failed at the API. Fixed by lowering `MAX_IMAGE_BYTES` to `5 MB × 3/4 ≈ 3.75 MB`. Wrote a failing BDD test first using a JPEG padded to exactly 4.5 MB via JPEG comment blocks (FF FE markers) — producing the exact same API error as the 107 production failures. Applied fix, confirmed green.
- **Unbound `filename` in `run_processor.py`** — if the processor threw before the loop started, `record_error` would reference an undefined variable. Fixed with a `filename = None` sentinel and guard.
- **Lambda Function URL 403s** (carried over from earlier) — confirmed root cause and fixed in CFN template.

### Input validation
- Added `isinstance(tags, list)` check in `searcher_handler.py` — returns 400 if a string is passed instead of a list.

### Code quality
- **Extracted `_neon_conn()`** into `features/steps/common.py` — was duplicated across multiple step files.
- **Extracted `_seed_photo()`** into `common.py` — SQL for seeding test photos was duplicated across three step files.
- **Extracted `record_error()`** into `lambda/processor.py` — the error-recording pattern was duplicated between `handler.py` and `run_processor.py`.

### Dependencies
- Split requirements into purpose-specific files: `requirements.txt`, `requirements-playwright.txt`, `requirements-processor-lambda.txt`, `requirements-searcher-lambda.txt`, `requirements-lock.txt`.
- Updated `package-processor.sh` and `package-searcher.sh` to use pinned Lambda-specific files so zips don't bundle unnecessary packages.

### BDD test additions
- **Infrastructure** — new scenario validating the live Lambda resource policy (no unrestricted `InvokeFunction`, correct Function URL condition). Concurrency limit scenario updated from 10 → 3.
- **String tags validation** — scenario for the 400 response when `tags` is a string.
- **Large image resize** — scenario using a JPEG padded to 4.5 MB via JPEG comment blocks to reproduce the exact production base64 failure.

### Documentation
- **README** — fixed stale make targets, removed stale `.env` block, added `last_error` to schema, clarified test requirements.

### Data integrity tooling
Four new `make` targets for ongoing DB/S3 health checks:

- **`neon-sync-check`** — compares S3 listing vs DB; reports files in S3 not in DB and DB records not in S3, with a status breakdown (processed/errored/stuck).
- **`neon-errors`** — lists all photos with `last_error` set.
- **`neon-no-tags`** — lists processed photos with no tag associations (silent failures).
- **`neon-reprocess-errors`** — queries all errored photos and re-invokes the processor Lambda asynchronously for each one.
- **`neon-clean-orphans`** — deletes DB records with no matching S3 object. Includes a safety floor (aborts if S3 returns fewer than 1,000 images, suggesting an incomplete listing).

### Production cleanup
- Ran `neon-errors`: found 107 errors — all base64 size failures (the `_prepare_image` bug).
- Deployed the fix, ran `neon-reprocess-errors`, confirmed all 107 cleared.
- Ran `neon-sync-check`: found 17 orphaned `Mehndi/` DB records (processed with subdirectory path as `s3_key`, files since removed from S3). Ran `neon-clean-orphans` to delete them, then `neon-clean-tags` to remove 2 orphaned tags.
- Final state: **1,278 photos, all processed OK, fully consistent with S3**.


---

## Session — 2026-03-20

### Model swap and prompt tuning
- Switched image recognition model from `claude-opus-4-6` to `claude-sonnet-4-6`
- Bumped tag range in the prompt from "20-30" to "25-30" to improve tag variety
- Added `s3_key` context to processor error log messages so failures can be traced back to a specific image
- Added BDD scenario proving error logs include the image filename

### Production cleanup
- Found and deleted 174–175 zero-byte images from `photo-tagging-photos` S3 bucket (corrupt at source)
- Ran `neon-clean-orphans` to remove 180 orphaned DB records (the zero-byte photos + stale test records)
- Ran `neon-clean-tags` to remove orphaned tags

### Thumbnail pipeline (new feature)
- Added `lambda/thumbnailer.py` — core logic: fetches photo from S3, applies EXIF orientation, center-crops to square, resizes to 400×400, saves as WebP quality 85, skips if thumbnail already exists
- Added `lambda/thumbnailer_handler.py` — Lambda entry point, reads `SOURCE_BUCKET` / `THUMBNAIL_BUCKET` env vars
- Added `infra/thumbnailer.yaml` — CloudFormation stack creating the `photo-tagging-thumbnails` public S3 bucket (with bucket policy granting public `s3:GetObject`) and the thumbnailer Lambda with appropriate IAM permissions
- Added `scripts/backfill_thumbnails.py` — invokes the thumbnailer Lambda for every processed photo in Neon, with configurable parallelism via `ThreadPoolExecutor` (currently 20 workers)
- Added `scripts/package-thumbnailer.sh` and `scripts/deploy-thumbnailer.sh`
- Added `make package-thumbnailer`, `make deploy-thumbnailer`, `make backfill-thumbnails` targets

### Searcher update
- Updated `lambda/searcher.py` to return `thumbnail_url` (plain public S3 URL) alongside the existing presigned `url` in each search result
- Updated `lambda/searcher_handler.py` to read and pass through `THUMBNAIL_BUCKET`
- Updated `infra/searcher.yaml` and `scripts/deploy-searcher.sh` to wire in `ThumbnailBucket`

### Frontend update (blue-green)
- Deployed thumbnail-aware frontend as `index2.html` alongside existing `index.html` for safe validation
- Grid now uses `thumbnail_url` for fast-loading thumbnails; lightbox still opens the full presigned URL
- After validating thumbnails looked correct, promoted `index2.html` to `index.html` and cleaned up
- Fixed `HOOK-ERROR in after_feature` in `environment.py` — replaced `context._playwright.__exit__()` with `context._playwright.stop()`

### Bug fix: sideways thumbnails
- Discovered portrait-orientation photos were generating sideways thumbnails due to EXIF rotation not being applied
- Fixed by wrapping `Image.open()` with `ImageOps.exif_transpose()` before cropping
- Redeployed thumbnailer, wiped thumbnail bucket, re-ran backfill

### BDD test coverage added
- `features/thumbnailer_lambda.feature` — 3 `@infrastructure` scenarios (Lambda active, creates WebP, skips existing)
- `features/backfill_thumbnails.feature` — 2 `@infrastructure` scenarios (creates thumbnails, skips existing)
- `features/searcher_lambda.feature` — added scenario asserting `thumbnail_url` in search results
- `features/frontend.feature` — added scenarios asserting grid uses thumbnail URL and lightbox uses full-size URL

  Current session                                                              
  ██████████▌                                        21% used 
  Resets 12am (America/New_York)                                                 

  Current week (all models)
  ██████                                             12% used
  Resets Mar 25 at 6pm (America/New_York)
