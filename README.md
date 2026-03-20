# photo-tagger

A photo tagging and search system. Photos are analysed by Claude's vision API to generate descriptive tags, which are stored in a PostgreSQL database and used to power tag-based search.

## Architecture

- **`lambda/processor.py`** — core tagging logic, designed to run as an AWS Lambda function. Accepts a single image, calls the Anthropic vision API, and stores the photo and tags in the database.
- **`lambda/searcher.py`** — search logic. Accepts a list of tags and returns matching photos ranked by number of matches.
- **`db/migrations/`** — SQL migration files applied by `db/migrate.py`.
- **`scripts/`** — local dev scripts for running the processor and searcher.
- **`features/`** — BDD integration tests using [behave](https://behave.readthedocs.io/).

## Schema

```
photos     (id, s3_key, processed_at, last_error)
tags       (id, name)
photo_tags (photo_id, tag_id)
```

## Local Development

### Prerequisites

- Docker (for local Postgres)
- Python 3.12+
- An Anthropic API key

### Setup

```bash
cp .env.example .env      # fill in ANTHROPIC_API_KEY and other values
make install              # install Python dependencies and git hooks
make local-db-start       # start local Postgres container
make local-migrate        # apply schema migrations
```

See `.env.example` for all available configuration variables.

### Processing photos

Place images in the `images/` directory, then:

```bash
make process              # process all images in images/
make process DIR=/path    # process images in a specific directory
```

### Searching

Edit the `TAGS` list in `scripts/run_searcher.py`, then:

```bash
make search
```

### Database

```bash
make local-db-shell       # open a psql session
make local-db-drop        # drop all tables (prompts for confirmation)
```

### Running tests

```bash
make test-unit            # unit tests only — no external dependencies
make test                 # BDD tests — requires local Postgres, Anthropic API key, and live AWS/Neon credentials
make test-frontend        # frontend browser tests — requires make install-playwright first
```

`make test` runs the full BDD suite including `@infrastructure` scenarios that invoke deployed AWS Lambdas and query Neon. Make sure your `.env` has `NEON_DATABASE_URL`, `SEARCHER_LAMBDA_NAME`, `PROCESSOR_LAMBDA_NAME`, and `S3_BUCKET` set.

## Useful SQL

Tag counts:
```sql
SELECT t.name, COUNT(*) AS photo_count
FROM tags t
JOIN photo_tags pt ON pt.tag_id = t.id
GROUP BY t.name
ORDER BY photo_count DESC;
```

Photos with their tags:
```sql
SELECT p.s3_key, array_agg(t.name) AS tags
FROM photos p
JOIN photo_tags pt ON pt.photo_id = p.id
JOIN tags t ON t.id = pt.tag_id
GROUP BY p.s3_key;
```
