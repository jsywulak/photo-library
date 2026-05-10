# photo-tagger

A photo tagging and search system. Users upload photos to an S3 staging bucket; an AWS Lambda pipeline computes a content hash, generates a thumbnail, holds the photo in an inbox for review, and (on user trigger) calls Claude's vision API to produce 25–30 descriptive tags. A search API ranks photos by tag matches.

## Pipeline

```
upload bucket
  └─ image_handler — hash, thumbnail, INSERT inbox photos row, copy to inbox bucket
       └─ inbox bucket  ─────────────────────►  GET /inbox  (frontend lists pending)
            └─ POST /process-inbox (user trigger)
                 └─ inbox.py — UPDATE photos row in place: bucket→photos, s3_key→{hash}.jpg
                      └─ photos bucket
                           ├─ thumbnailer (EventBridge) — WebP at thumbnails/{hash}.webp
                           └─ processor v2 (EventBridge) — Anthropic vision → tags → state='tagged'
                                                            └─►  GET /search via searcher Lambda
```

Every action emits a `photo_events` row (audit log). See **Observability** below.

## Tech stack

- **Compute** — Python 3.12 on AWS Lambda. Each Lambda has its own deployment zip and CloudFormation stack.
- **Database** — Neon serverless Postgres (production), local Docker Postgres (dev/test).
- **Storage** — S3 (upload + inbox + photos + thumbnail buckets).
- **Eventing** — EventBridge S3 Object Created rules trigger image_handler, processor v2, and thumbnailer.
- **Tagging** — Anthropic vision API (`ANTHROPIC_MODEL`, default `claude-opus-4-6`).
- **Frontend** — static HTML/JS hosted on S3, talks to Lambda Function URLs with an `x-api-key` header.
- **Tests** — [behave](https://behave.readthedocs.io/) BDD suite, no mocks (real Postgres, real Anthropic, real AWS for `@infrastructure` scenarios).

## Repository layout

```
lambda/                 production Python — one module per concern, plus *_handler.py entry points
  processor.py          tagging logic; called by handler.py
  searcher.py           tag-based search + add/remove/archive; called by searcher_handler.py
  inbox.py              list + promote + archive inbox photos; called by inbox_handler.py
  image_handler.py      EventBridge target for upload bucket; INSERTs inbox photos row
  thumbnailer.py        WebP generation; called from image_handler and thumbnailer_handler.py
  stats.py              top-level stats API
  exif.py               shared EXIF DateTimeOriginal helper
  utils.py              get_required_env, thumbnail_key, record_event (photo_events writer)
db/migrations/          NNN_description.sql, applied by db/migrate.py
infra/                  CloudFormation templates — one stack per Lambda, plus S3 bucket stacks and frontend
scripts/                package-*.sh build Lambda zips; deploy-*.sh run CloudFormation
features/               BDD .feature files + steps/*.py + environment.py teardown
frontend/               static SPA (index.html / inbox.html / stats.html), config.example.js
tests/                  unit tests (test_processor.py, test_exif.py)
images/                 local sample images (gitignored — must be real JPEGs)
```

## Schema

```sql
photos (
  id BIGSERIAL PRIMARY KEY,
  s3_key TEXT NOT NULL,
  bucket TEXT NOT NULL,                     -- 'photo-tagging-inbox' | 'photo-tagging-photos'
  content_hash TEXT UNIQUE,                 -- SHA-256, single-column unique across all buckets
  original_filename TEXT,                   -- preserved from upload
  captured_at TIMESTAMPTZ,                  -- from EXIF DateTimeOriginal
  uploaded_at TIMESTAMPTZ,                  -- not yet populated (Slice 6 wires this up)
  thumbnailed_at TIMESTAMPTZ,               -- not yet populated
  state TEXT NOT NULL DEFAULT 'received',   -- received | tagged | failed | archived
  tagged_at TIMESTAMPTZ,
  processed_at TIMESTAMPTZ,                 -- alias of tagged_at, will drop in a future migration
  archived_at TIMESTAMPTZ,
  last_error TEXT,
  UNIQUE (s3_key, bucket)
);

tags (
  id BIGSERIAL PRIMARY KEY,
  name TEXT NOT NULL                        -- expression-indexed on LOWER(name); not column-UNIQUE
);

photo_tags (
  photo_id BIGINT REFERENCES photos(id) ON DELETE CASCADE,
  tag_id BIGINT REFERENCES tags(id) ON DELETE CASCADE,
  removed_at TIMESTAMPTZ,                   -- soft-delete from /remove-tag
  PRIMARY KEY (photo_id, tag_id)
);

photo_events (                              -- append-only audit log; one row per Lambda action
  id BIGSERIAL PRIMARY KEY,
  photo_id BIGINT REFERENCES photos(id) ON DELETE CASCADE,
  s3_key TEXT NOT NULL,
  bucket TEXT NOT NULL,
  event_type TEXT NOT NULL,                 -- received | thumbnail_created | thumbnail_skipped | promoted
                                            -- | tagging_started | tagged | tag_failed | tag_added
                                            -- | tag_removed | archived
  actor TEXT NOT NULL,                      -- which Lambda wrote it
  details JSONB,                            -- model name, tag name, error string, etc.
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

Source of truth is `db/migrations/NNN_*.sql`.

## Local development

### Prerequisites

- Docker (local Postgres)
- Python 3.12+
- An Anthropic API key

### Setup

```bash
cp .env.example .env       # fill in ANTHROPIC_API_KEY
make install               # Python deps + git pre-commit hooks (gitleaks)
make local-db-start        # start phototagger-db container on :5432
make local-migrate         # apply all pending migrations to local Postgres
```

### Process photos locally

Drop real JPEGs in `images/`, then:

```bash
make process               # tags everything in images/, commits to local DB
make process DIR=/path     # tag a different directory
```

`scripts/run_processor.py` calls `processor.process_one()` directly — no Lambda, no S3.

### Search

```bash
make search                # edit TAGS in scripts/run_searcher.py first
```

### Inspect the local DB

```bash
make local-db-shell        # psql session
make db-drop               # nuke all tables (prompts to confirm)
```

## Tests

```bash
make test                  # unit + all BDD (local + frontend + infrastructure)
make test-unit             # tests/ only — no external deps
make test-local            # @local BDD — needs local Postgres + Anthropic key
make test-frontend         # @frontend Playwright — run `make install-playwright` first
make test-infrastructure   # @infrastructure — hits live Lambdas + Neon + S3
```

The BDD suite uses **no mocks**. Local scenarios run against real Postgres and the real Anthropic API; infrastructure scenarios invoke deployed Lambdas and write to Neon. Test fixtures use the prefix `testA6FA7E1D-{uuid}` so `features/environment.py` can sweep stragglers in teardown.

**TDD convention:** new features start with a failing `.feature` scenario before any code change. See `features/photo_state.feature` and `features/inbox_promotion_history.feature` for recent examples.

## Deployment

Each Lambda is built into a zip by `scripts/package-<name>.sh` and deployed via CloudFormation by `scripts/deploy-<name>.sh`. The `make deploy-*` targets wrap both.

```bash
make neon-migrate                     # apply pending migrations to Neon (auto-backups first)

make deploy-processor-v2              # tagging Lambda
make deploy-searcher                  # /search, /add-tags, /remove-tag, /archive, /tags
make deploy-inbox                     # /inbox, /process-inbox, /archive-inbox
make deploy-image                     # upload-bucket EventBridge target
make deploy-thumbnailer               # photos-bucket EventBridge target
make deploy-stats                     # /stats endpoint
make deploy-frontend                  # rsync frontend/ to the public S3 bucket

make deploy-photos-bucket             # one-time: photos S3 bucket + EventBridge wiring
make deploy-inbox-bucket              # one-time: inbox S3 bucket
make deploy-upload-bucket             # one-time: upload staging S3 bucket
```

Required `.env` for deployment (`.env.example` is incomplete — extend as needed):

| Variable | Used by |
|---|---|
| `DATABASE_URL` | local Postgres + behave local tests |
| `ANTHROPIC_API_KEY` | tagging (local + Lambda) |
| `ANTHROPIC_MODEL` | optional override (default `claude-opus-4-6`) |
| `NEON_DATABASE_URL` | Lambdas + `neon-migrate` (quote it — contains `&`) |
| `S3_BUCKET` | photos bucket name |
| `INBOX_BUCKET` | inbox bucket name |
| `UPLOAD_BUCKET` | upload staging bucket name |
| `THUMBNAIL_BUCKET` | public thumbnail bucket name |
| `DEPLOYMENT_BUCKET` | where Lambda zips and CFN templates land |
| `STACK_NAME` | CloudFormation stack prefix |
| `API_KEY` | shared `x-api-key` for all Function URLs |
| `FRONTEND_DOMAIN` | full origin for CORS (e.g. `http://photos.example.com`) |
| `*_LAMBDA_NAME`, `*_URL` | populated after deploy; needed for `make test-infrastructure` |

`frontend/config.js` is gitignored — copy `config.example.js` and fill in the Function URLs after deploying.

## Observability

Every Lambda emits a `photo_events` row in the same DB transaction as its other writes. The audit log answers "what happened to this photo?" with one query:

```sql
SELECT created_at, actor, event_type, details
FROM photo_events
WHERE s3_key = '<hash>.jpg' OR photo_id = <id>
ORDER BY created_at;
```

Operational helpers:

```bash
make neon-stats                       # photo + tag counts, top tags
make neon-tags                        # full tag distribution
make neon-errors                      # photos with state='failed'
make neon-no-tags                     # tagged photos with zero tag rows (silent failures)
make neon-sync-check                  # S3 vs DB drift
make neon-check-thumbnails            # missing/orphaned thumbnails
make neon-audit-thumbnails            # three-way audit (photos / inbox / thumbnails)
make neon-clean-tags                  # delete orphaned tags
make neon-clean-orphans               # delete DB rows with no S3 object
make neon-reprocess-errors            # re-invoke processor for failed photos
```

## Conventions

Detailed conventions (transaction ownership, packaging, photo_events teardown, lifecycle column semantics) live in **[CLAUDE.md](CLAUDE.md)** — read that before touching any Lambda.
