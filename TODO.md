# Tech Debt TODO

## High Priority

### Security
- [ ] Remove redundant `InvokeFunction` permission with `Principal: "*"` from `infra/searcher.yaml` — Lambda URL permission already covers public access
- [ ] Add `PublicAccessBlock` config to photos S3 bucket in `infra/processor.yaml`
- [ ] Add CloudFront distribution to frontend (`infra/frontend.yaml`) for HTTPS, caching, and remove hardcoded `us-east-1` region

### Bugs
- [ ] Fix unbound `filename` variable in `scripts/run_processor.py` error handler — loop may never run, should reference a variable that's always defined
- [ ] Validate `tags` is a list (not a string) in `searcher_handler.py` before iterating — a string payload silently iterates over characters

### Dependencies
- [ ] Add `boto3` to `requirements.txt` — used in tests and handlers but missing, breaks fresh venvs for infra BDD tests
- [ ] Split `playwright` out of `requirements.txt` into a dev-only requirements file
- [ ] Add a lock file (e.g. `requirements-lock.txt`) for reproducible builds
- [ ] Pin versions in Lambda packaging scripts (`package-processor.sh`, etc.)

## Medium Priority

### Testing
- [ ] Exclude `@infrastructure` tests from `make test` (currently only `@frontend` is excluded — infra tests require live AWS)
- [ ] Add unit tests for `searcher.py::search()` and `get_random_tags()`
- [ ] Add unit tests for `searcher_handler.py` routing logic (OPTIONS, API key check, GET /tags, POST search, malformed input)

### Code Duplication
- [ ] Extract `_neon_conn()` into a shared module — currently copy-pasted in `processor_lambda_steps.py` and `searcher_lambda_steps.py`
- [ ] Consolidate `_seed_photo` SQL duplicated across three step files into shared test helpers
- [ ] Extract error-recording pattern into a shared utility — duplicated between `handler.py` and `run_processor.py`

### Housekeeping
- [ ] Fix stale `README.md` — refers to `make db-start` / `make migrate` but actual targets are `local-db-start` / `local-migrate`
- [ ] Gitignore or remove `SESSION_NOTES.md` from the repo

## Lower Priority

### Infrastructure
- [ ] Add `DeletionPolicy: Retain` to photos S3 bucket in `infra/processor.yaml` — currently deletion of the stack deletes all photos
- [ ] Cross-reference processor and searcher stacks via `!ImportValue` instead of free-text `PhotosBucket` parameter
- [ ] Add Lambda dead-letter queue (DLQ) to processor for failed S3 events
- [ ] Explicitly set `Architectures: [x86_64]` on both Lambdas to match packaging scripts

### Code Quality
- [ ] Remove unused `s3:ListBucket` IAM permission from processor Lambda role
- [ ] Add CLI arg support to `run_searcher.py` instead of hardcoded `TAGS` list
- [ ] Move `_build_prompt()` result to a module-level constant — currently rebuilt on every image
- [ ] Replace stringly-typed `process_one` return values (`"processed"`, `"skipped"`, `"unsupported"`) with an Enum
