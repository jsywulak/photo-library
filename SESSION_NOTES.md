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

### Usage

  Current session
  ██████████▌                                        21% used
  Resets 12am (America/New_York)

  Current week (all models)
  ██████                                             12% used
  Resets Mar 25 at 6pm (America/New_York)

## Session — 2026-03-22

### Infrastructure / packaging fixes
- All three Lambda packages were missing `lambda/utils.py` from their zips, causing runtime import errors on cold start
- `thumbnail_key` moved into `lambda/utils.py` (dependency-free) to break a circular import — `searcher.py` was pulling in `thumbnailer.py` which imports PIL, not available in the searcher package
- S3 client in the searcher Lambda switched to SigV4 presigned URLs — SigV2 mishandles STS session token characters, causing 403s on certain images
- `scripts/utils.py` renamed to `scripts/helpers.py` to avoid a `sys.modules` collision when Lambda and script code are both loaded in the same Python process during BDD tests

### Lightbox tag display
- Search query updated to return all tags per photo via `array_agg` alongside the match count
- Lightbox redesigned to show photo tags as styled chips below the image, matching the aesthetic of the search suggestion chips
- BDD scenario and Playwright step added to verify tags appear in the lightbox

### Processor Lambda test cleanup
- `step_upload_test_photo` now sets `context.test_thumbnail_key` and `context.test_thumbnail_bucket` so the EventBridge-triggered thumbnail gets deleted in `after_scenario`, not just the source photo and Neon record
- Diagnosed an orphaned Neon record (`test-71ef7c31-PXL_20260319_193406856.webp`) left by prior test runs that weren't cleaning up thumbnails; removed it manually

### Tag management (new feature)
- Migration 005: added `removed_at TIMESTAMPTZ` to `photo_tags` for logical tag removal — NULL means active, non-null means removed; existing rows unaffected
- `POST /remove-tag` endpoint in the searcher Lambda — sets `removed_at`; removed tags are excluded from search ranking and the per-photo tags list
- `POST /add-tags` endpoint — accepts `s3_key` and a list of tags; creates tags if they don't exist, restores previously-removed associations, returns 404 if photo not found
- Lightbox × button on each tag chip calls `/remove-tag` and removes the chip from the DOM
- "Add tag..." chip at the end of the tag list expands into a text input on click; Enter calls `/add-tags` and renders the new chip inline; Escape cancels
- Full BDD coverage: `photo_search.feature` (unit-level, local DB) and `searcher_lambda.feature` (infrastructure, live Lambda) for both endpoints; three new Playwright scenarios for the add-tag UI

### Usage
  Current session
  ███                                                6% used
  Resets 3am (America/New_York)

  Current week (all models)
  ██████████                                         20% used
  Resets Mar 25 at 6pm (America/New_York)

### Inbox Archive and Process actions (2026-03-25)

**Archive button**
- Migration 006: added `archived_at TIMESTAMPTZ` to `photos` table — NULL means visible in inbox, non-null means hidden
- `POST /archive-inbox` endpoint in the searcher Lambda — sets `archived_at = NOW()` on the matching inbox photo record; returns 404 if not found
- `list_inbox` query updated to filter `WHERE archived_at IS NULL` so archived photos no longer appear
- No S3 changes — the file stays in the inbox bucket, only the DB row is hidden

**Process button**
- `POST /process-inbox` endpoint — copies the S3 object from the inbox bucket to the photos bucket (`copy_object`), deletes it from the inbox bucket (`delete_object`), then removes the DB record for the inbox copy
- The inbox DB record must be deleted explicitly because `photos` has a `UNIQUE (s3_key, bucket)` constraint — the processor Lambda creates a separate row with the photos bucket, so the inbox row would otherwise remain and show a broken presigned URL
- EventBridge detects the new object in the photos bucket and automatically fires the processor Lambda, which calls Anthropic and tags the photo — no additional work needed from the searcher
- IAM: added `s3:PutObject` on the photos bucket and `s3:DeleteObject` on the inbox bucket to the searcher role in `searcher.yaml` (CloudFormation stack update deployed)

**Inbox lightbox UX**
- Both buttons live in the lightbox; Archive is on the left, Process on the right
- After either action, the lightbox auto-advances to the next photo in the grid rather than closing; falls back to the previous photo if at the end; closes and shows empty state if no photos remain
- Left arrow key → Archive, Right arrow key → Process (only active when lightbox is open)
- Inbox photo count shown in the header as "(N)" next to "Inbox"; decrements as photos are actioned
- Buttons are disabled during the in-flight request to prevent double-submission; re-enabled on error or when the lightbox opens (covers the auto-advance case where `closeLightbox` is never called)

**Tests**
- 6 new Playwright scenarios in `features/inbox.feature` covering: button visibility, successful Archive, successful Process, error state for each
- `step_open_inbox` mock updated to route by URL path so `/process-inbox` and `/archive-inbox` can return different responses than the inbox listing
- `context.mock_process_error` and `context.mock_archive_error` flags added to `environment.py` for error-state scenarios


### /usage
  Current session
  ███████████▌                                       23% used
  Resets 11pm (America/New_York)

  Current week (all models)
  █▌                                                 3% used
  Resets Apr 1 at 6pm (America/New_York)

---

## Session — 2026-03-29

### Inbox pagination

**Problem:** The inbox had ~2,000 photos and `list_inbox()` was fetching all of them on every load, making the page slow.

**Approach:** TDD — wrote failing BDD tests first, then implemented.

**Backend changes:**
- `list_inbox()` now accepts `limit` (default 50) and `cursor` (integer photo ID) parameters
- Fetches `limit + 1` rows to detect whether more pages exist, without a separate COUNT query for "has more"
- Returns `{"items": [...], "next_cursor": <id or null>, "total": <total count>}` — total from a separate COUNT query so the header count is always accurate
- Cursor logic: `WHERE id < %s ORDER BY id DESC` — stable under deletions (archived/processed photos don't shift subsequent pages)
- `searcher_handler.py`: added `?cursor=` and `?limit=` query string parsing on the `/inbox` route; returns 400 on non-integer values
- Added `_INBOX_PAGE_SIZE = 50` constant imported by the handler

**Frontend changes (`inbox.html`):**
- Added "Load more" button (hidden until a second page exists)
- New state: `nextCursor`, `isLoading`, `totalCount`
- `loadInbox(cursor)` replaces the old fetch function — appends to the grid rather than replacing it when `cursor` is set
- After archive/process, if the grid empties and `nextCursor` is set, auto-loads the next page
- Count in header uses server-provided `total`, decremented locally on each action
- Deployed frontend first (with `Array.isArray(data)` backward-compat guard), then Lambda — avoided a window where either the old or new frontend would break against the opposite Lambda version

**Tests added:**
- `features/inbox.feature`: 3 new Playwright scenarios — Load more hidden on single page, visible when more exist, clicking appends photos
- `features/searcher_lambda.feature`: 2 new `@infrastructure` scenarios — cursor pagination returns non-overlapping pages, invalid cursor returns 400
- Frontend step helpers updated with `_inbox_items(context)` to handle `mock_inbox_results = []` vs unset

### Makefile test target restructuring

**Problem:** `make test` silently ran live AWS (`@infrastructure`) tests because it only excluded `@frontend`. Two feature files were untagged.

**Changes:**
- Added `@local` tag to `features/photo_processing.feature` and `features/photo_search.feature`
- `make test` — runs unit tests (`python -m unittest discover tests/`) + all BDD tests (`behave`)
- `make test-local` — `behave --tags @local` (local Postgres + Anthropic, no AWS, no Playwright)
- `make test-frontend` — `behave --tags @frontend` (Playwright only)
- `make test-infrastructure` — `behave --tags @infrastructure` (live AWS)
- Updated `CLAUDE.md` to document the new targets

### Readability refactoring

Broad pass to eliminate copy-pasted patterns across tests, backend, and frontend.

**Tests:**
- `photo_processing_steps.py`: extracted `_run_processor(context, bucket=None)` helper — `step_run` and `step_run_with_bucket` were 95% identical, now each a 1-line delegate
- `searcher_lambda_steps.py`: added `_api_get(path, api_key=None)` and `_api_post(path, body_dict, api_key=None)` helpers — eliminated 8 repeated 8–12 line HTTP boilerplate blocks

**Backend:**
- `processor.py`: unpacked `fetchone()` by name (`photo_id, processed_at = ...`) instead of opaque index access
- `searcher.py`: extracted `_normalise_tags()` — `add_tags` and `search` both had the same inline list comprehension
- `searcher_handler.py`:
  - Added `_parse_body(event)` — replaces 5 copy-pasted `try: json.loads / except JSONDecodeError` blocks
  - Added `_db()` context manager — replaces 8 copy-pasted `conn = psycopg2.connect(...) / try: ... / finally: conn.close()` blocks

**Frontend:**
- Both HTML files: `const BASE_URL = SEARCHER_URL.replace(/\/$/, '')` defined once at the top, replacing inline `.replace()` calls on every API call
- `inbox.html`: removed `Array.isArray(data)` backward-compat guard (Lambda deployed with paginated response weeks ago)

### Usage

  Current session                                                                                                                                                                              
  █████████████████████████████████████████████████  98% used                                                                                                                                  
  Resets 3pm (America/New_York)                                                                                                                                                                
                                                                                                                                                                                                 
  Current week (all models)
  ███████▌                                           15% used
  Resets Apr 1 at 6pm (America/New_York)

---

## Session — 2026-03-29 (continued)

### Sort inbox by EXIF capture time

**Problem:** Inbox photos were ordered by `id DESC` (S3 arrival order), creating a mishmash when photos from different shoots were uploaded at different times. Goal: sort by EXIF `DateTimeOriginal`, oldest-captured-first, with no-EXIF photos at the end.

**Deployed in three backwards-compatible phases:**

**Phase 1 — Migration (no behaviour change)**
- `db/migrations/007_photo_captured_at.sql`: added `captured_at TIMESTAMPTZ` column and index to `photos`
- Applied immediately to both local and Neon — nullable column, no production impact

**Phase 2 — Processor**
- Added `_extract_captured_at(image_bytes)` to `lambda/processor.py` using Pillow's `img.getexif().get_ifd(34665).get(36867)` — `DateTimeOriginal` lives in the Exif Sub-IFD (pointer tag 34665), not the main IFD. Added fallback `or exif.get(36867)` for synthetic test JPEGs that put the tag in the main IFD.
- Inbox photo INSERTs now write `captured_at`; includes a `DO UPDATE SET captured_at = ...` for the backfill case on conflict
- BDD scenarios added (TDD): inbox photo with EXIF has `captured_at` set; without EXIF has `captured_at = NULL`
- Backfill: ran `make sync-inbox` (re-invokes the processor Lambda for all inbox photos) rather than writing a separate backfill script

**Phase 3 — Searcher**
- `list_inbox()` ORDER BY changed to `captured_at ASC NULLS LAST, id ASC`
- Cursor format changed from a bare integer ID to URL-safe base64 JSON `{"c": "<iso_timestamp_or_null>", "id": <int>}` — padding (`=`) stripped for safe use in query strings; frontend passes it back opaquely
- Legacy integer cursors still accepted for any in-flight pagination from before the change
- WHERE clause for cursor resume handles four cases: dated photos before undated tail, same date advance by id, later date, both-null tail advance by id
- `searcher_handler.py`: changed `cursor = int(raw)` to `cursor = qs.get("cursor") or None` (opaque passthrough); added `try/except ValueError` returning 400 for invalid cursors
- Three new `@local` BDD scenarios in `features/inbox_ordering.feature`: oldest-first ordering, no-EXIF photos last, cursor pagination preserves capture-time order

**Key bugs found and fixed:**
- EXIF `DateTimeOriginal` not in the main IFD for real Canon EOS R6 photos — required `get_ifd(34665)` (Sub-IFD access)
- After backfill, all `captured_at` were NULL because the Sub-IFD bug was in production before the fix
- Infrastructure test photo was inserting with `captured_at = NULL`, sorting it after 1,000+ dated photos and missing the first page — fixed by seeding with `captured_at = '1970-01-01 00:00:00+00'`
- Step name conflict: `"the inbox listing has a next_cursor"` vs existing `"the inbox response has a next_cursor"` in `searcher_lambda_steps.py` — renamed to avoid collision

### Infinite scroll

**Approach:** Keep all Load More button functionality; add infinite scroll as a toggleable option controlled by a hardcoded `INFINITE_SCROLL` flag in `inbox.html` (defaults `true` in production).

- Added `<div id="scroll-sentinel" style="height:1px;">` after the load-more container
- `IntersectionObserver` with `rootMargin: '200px'` watches the sentinel and calls `loadInbox(nextCursor)` when visible, if `nextCursor !== null && !isLoading`
- Feature flag: `const INFINITE_SCROLL = typeof window.INFINITE_SCROLL !== 'undefined' ? window.INFINITE_SCROLL : true;`
- Existing Load More Playwright tests inject `window.INFINITE_SCROLL = false` via `page.add_init_script()` so the flag doesn't interfere with button click tests
- New Playwright scenario: "Scrolling to the bottom loads more photos when infinite scroll is enabled" — uses a 400×400 viewport and `window.scrollTo(0, document.body.scrollHeight)` to trigger the observer

### Data integrity tooling

**Three-way audit (`scripts/audit_thumbnails.py`):**
- Cross-references photos S3 bucket + inbox S3 bucket + thumbnail bucket + DB
- Revealed the thumbnail count discrepancy (5,119 DB rows vs 4,490 thumbnails) was not missing thumbnails — 627 photos exist in both buckets (same `s3_key`, different `bucket` = 2 DB rows but 1 S3 object each). All S3 photos have thumbnails.
- Key fix: uses `list(db_rows)` not a dict comprehension — the dict silently dropped duplicate `s3_key` values across buckets

**`scripts/check_thumbnails.py` updated:**
- Now reports thumbnail counts separately for the processed bucket vs the inbox bucket

### S3 key listing via CLI

For buckets with spaces in key names, `aws s3 ls` breaks because it splits on whitespace. The reliable approach:

```bash
aws s3api list-objects-v2 --bucket BUCKET_NAME --query 'Contents[].Key' --output text | tr '\t' '\n' | grep -i '\.jpg$'
```

`--query Contents[].Key` extracts only the key field (handles spaces), `--output text` gives tab-separated values, `tr '\t' '\n'` splits to one key per line.


---

## Session — 2026-03-30/31

### Lambda cleanup — removing the old processor

After splitting the processor into two dedicated Lambdas (processor v2 + inbox) in a prior session, cleaned up all the leftover artifacts from the original monolithic processor:

- Deleted `infra/processor.yaml`, `scripts/deploy-processor.sh`, `scripts/package-processor.sh`, `requirements-processor-lambda.txt`
- Removed `package-processor` / `deploy-processor` Makefile targets; updated help text
- Deleted `features/processor_lambda.feature` and `features/steps/processor_lambda_steps.py`
- Updated `features/steps/infrastructure_steps.py` concurrency check to use `PROCESSOR_V2_LAMBDA_NAME` instead of `PROCESSOR_LAMBDA_NAME`
- Updated `infra/processor-v2.yaml` to set `ReservedConcurrentExecutions: 3` (original live value; limits kept low because higher concurrency overwhelms the Claude API)
- Deleted the live `photo-tagging` CloudFormation stack from AWS

**Bug found during cleanup:** Processor v2 Lambda was still running stale code — the "handle missing S3 keys gracefully" fix from commit `2547440` was applied after the v2 Lambda was last deployed. A new BDD test scenario ("Processing a missing S3 key does not crash the v2 Lambda") caught this. Redeployed v2 to fix.

### CORS fix — restrict Allow-Origin to frontend domain

The CORS `Access-Control-Allow-Origin` header was previously hardcoded to `*`. Changed it to use the `FRONTEND_DOMAIN` env var in both `searcher_handler.py` and `inbox_handler.py`.

**Bugs hit along the way:**
- `FRONTEND_DOMAIN` was set to `lax.jsywulak.com` (no scheme), but the handler was prepending `https://` — the actual frontend is served over `http://`. Fixed by storing the full origin in `.env`: `FRONTEND_DOMAIN=http://lax.jsywulak.com`.
- `features/steps/infrastructure_steps.py` was reading `FRONTEND_DOMAIN` as the S3 bucket name instead of `FRONTEND_BUCKET` — broke as soon as `FRONTEND_DOMAIN` included a scheme. Fixed to use `FRONTEND_BUCKET`.
- Removed stale `PROCESSOR_LAMBDA_NAME` from `.env` (old stack is gone).

### Usage
Hit my limit several times. Couldn't get much done during the day because of new Claude limits, and then I had so much leftover to do at night that I hit it again. Blah. :(

---

## Session — 2026-03-31

### Stats dashboard (new feature — Phase 1: Lambda)

Built a dedicated stats Lambda and deployed it before touching the frontend.

**Lambda (`lambda/stats.py` + `lambda/stats_handler.py`):**
- `GET /stats` endpoint, auth via `x-api-key` header, CORS via `FRONTEND_DOMAIN`
- Initial metrics: `inbox_count` (DB), `photos_count` (S3), `db_count` (DB), `archived_count` (DB), `top_tags`
- CloudFormation stack `photo-tagging-stats` with IAM `s3:ListBucket` and `THUMBNAIL_BUCKET` env var
- `make package-stats` / `make deploy-stats` targets added
- BDD tests: `features/stats_lambda.feature` (`@infrastructure`) — auth rejection + all fields present

**Correctness fix — inbox count:**
- Stats page showed 4,207 inbox objects (raw S3 count); inbox page title showed 1,959 (DB count). Discrepancy: ~2,248 S3 objects with no DB record.
- Fixed `inbox_count` to use the same DB query as the inbox page: `SELECT COUNT(*) FROM photos WHERE bucket = inbox AND archived_at IS NULL`.

### Stats dashboard — Phase 2: Frontend

- `frontend/stats.html` — standalone dark-themed page, card grid layout, CSS-only `ⓘ` tooltip on every card label using `data-tooltip` + `::after` pseudo-element
- `frontend/config.js` + `config.example.js` updated with `STATS_URL`
- `scripts/deploy-frontend.sh` updated to upload `stats.html` as `/stats`
- Playwright BDD tests: `features/stats_frontend.feature` — all metrics render, top tags render, error state, info icon present

### Stats — additional metrics

Expanded the Lambda to cover data-integrity health checks:

- `total_photos` — inbox + processed + archived DB counts
- `inbox_s3_count` / `processed_s3_count` — raw S3 object counts
- `thumbnail_count` — S3 objects under `thumbnails/` prefix
- `orphaned_thumbnails` — thumbnails with no matching `content_hash` in DB
- `orphaned_processed` — objects in photos bucket with no matching hash in DB
- `orphaned_inbox` — objects in inbox bucket with no matching `s3_key` in DB

Orphan detection approach: load all known keys/hashes from DB into a Python set in one query, paginate S3, check each key against the set. Same direction as `scripts/sync_check.py`.

Lambda timeout bumped to 60s (orphan scans across 3 buckets take ~35s at current scale). IAM `s3:ListBucket` extended to inbox and thumbnail buckets.

### Bug fixes

- `scripts/reprocess_errors.py` was referencing `PROCESSOR_LAMBDA_NAME` (old env var name); fixed to `PROCESSOR_V2_LAMBDA_NAME`
- `scripts/sync_check.py` same fix

### Reprocess errors

Ran `make neon-reprocess-errors` — found 42 errored photos and queued them all for reprocessing.

### Usage
  Current session                 
  █████████████████                                  34% used                                                                                                                                    
  Resets 12pm (America/New_York)                                                                                                                                                               

  Current week (all models)
  ████████████████████████████████████████▌          81% used
  Resets 6pm (America/New_York)

## Session — 2026-04-01

### Stats — per-stat endpoints for progressive loading

The stats page was slow because all metrics were fetched in a single `GET /stats` request, blocking until every stat (including slow S3 list-objects scans) completed.

**Fix:** broke each stat into its own endpoint; frontend fires all 10 in parallel and updates each card as its response arrives.

**Lambda (`lambda/stats.py`):**
- Renamed all private helpers (dropped `_` prefix) so they can be imported individually
- `get_stats()` kept intact for backwards compat

**Lambda (`lambda/stats_handler.py`):**
- Added 10 per-stat routes: `/stats/inbox-count`, `/stats/db-count`, `/stats/archived-count`, `/stats/inbox-s3-count`, `/stats/processed-s3-count`, `/stats/thumbnail-count`, `/stats/orphaned-thumbnails`, `/stats/orphaned-processed`, `/stats/orphaned-inbox`, `/stats/top-tags`
- Each returns `{"value": ...}`
- S3-only routes skip the DB connection entirely
- `GET /stats` aggregate route kept for backwards compat

**Frontend (`frontend/stats.html`):**
- Grid shown immediately with `—` placeholders (no spinner)
- 10 independent fetches; each card updates as its response arrives
- `total-photos` computed client-side once inbox + db + archived all resolve
- Per-card error state shows `err` in red

### Bug fix — `deploy-frontend.sh` stack failures

The frontend CloudFormation stack had been stuck in `UPDATE_ROLLBACK_COMPLETE` since 2026-03-31.

**Root cause:** `FRONTEND_DOMAIN` was changed to include the `http://` scheme (for CORS), but `deploy-frontend.sh` was passing it as the CloudFormation `DomainName` parameter, which is used as the S3 bucket name. CloudFormation tried to rename the bucket to `http://lax.jsywulak.com`, hit an internal AWS bug, and rolled back.

**Fix:** changed the script to use `FRONTEND_BUCKET` (scheme-free) for the CFN parameter and for the S3 upload target, instead of `FRONTEND_DOMAIN`. Also fixed the `Deployed:` echo line which was double-printing the scheme.

### Usage

  Current session                                                                                                                                                                                
  ███████████████████████████████████████            78% used                                                                                                                                    
  Resets 12pm (America/New_York)                                                                                                                                                                 
                                                                                                                                                                                                 
  Current week (all models)
  ██████████████████████████████████████████▌        85% used
  Resets 6pm (America/New_York)
