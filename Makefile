include .env
export

CONTAINER_NAME = phototagger-db

.PHONY: install install-hooks install-playwright local-db-start local-db-shell local-db-stop local-migrate neon-migrate test test-unit test-frontend process search db-drop package-processor deploy-processor package-searcher deploy-searcher neon-tags neon-clean-tags neon-sync-check neon-errors neon-no-tags neon-reprocess-errors neon-clean-orphans deploy-frontend help clean

help:
	@echo "Local development:"
	@echo "  make install          Install Python dependencies and git hooks"
	@echo "  make install-hooks    Install git pre-commit hooks (gitleaks secret scanning)"
	@echo "  make install-playwright  Download Chromium for frontend tests"
	@echo "  make local-db-start   Start local Postgres container"
	@echo "  make local-db-stop    Stop local Postgres container"
	@echo "  make local-db-shell   Open a psql session"
	@echo "  make local-migrate    Apply pending migrations locally"
	@echo "  make db-drop          Drop all local tables (prompts for confirmation)"
	@echo "  make test             Run BDD tests (requires real services)"
	@echo "  make test-unit        Run unit tests (no external dependencies)"
	@echo "  make test-frontend    Run frontend browser tests (requires make install-playwright)"
	@echo "  make process DIR=...  Run processor against a directory of images"
	@echo "  make search           Run searcher locally"
	@echo "  make clean            Remove build artifacts"
	@echo ""
	@echo "AWS deployment:"
	@echo "  make neon-migrate     Apply pending migrations to Neon"
	@echo "  make neon-tags        Show tag counts from Neon"
	@echo "  make neon-clean-tags  Remove tags with no associated photos"
	@echo "  make neon-stats       Show photo/tag counts and top 5 tags"
	@echo "  make neon-sync-check  Compare S3 listing vs DB (find unprocessed/orphaned)"
	@echo "  make neon-errors      List photos with processing errors"
	@echo "  make neon-no-tags     List processed photos with no tags (silent failures)"
	@echo "  make neon-reprocess-errors  Re-invoke processor Lambda for all errored photos"
	@echo "  make neon-clean-orphans     Delete DB records with no matching S3 object"
	@echo "  make deploy-processor Build and deploy the processor Lambda"
	@echo "  make deploy-searcher  Build and deploy the searcher Lambda"
	@echo "  make deploy-frontend  Upload frontend to S3"

install: install-hooks
	pip install -r requirements.txt

install-hooks:
	@bash scripts/install-hooks.sh

install-playwright:
	pip install -r requirements-playwright.txt
	playwright install chromium

local-db-start:
	@bash scripts/db-start.sh

local-db-shell:
	docker exec -it $(CONTAINER_NAME) psql -U $(DB_USER) -d $(DB_NAME)

local-db-stop:
	docker stop $(CONTAINER_NAME)

local-migrate:
	python db/migrate.py

neon-migrate:
	python db/migrate.py "$(NEON_DATABASE_URL)"

test:
	behave --tags "not @frontend"

test-unit:
	python -m unittest discover tests/

test-frontend:
	behave --tags @frontend

process:
	python scripts/run_processor.py $(DIR)

search:
	python scripts/run_searcher.py

db-drop:
	@bash scripts/db-drop.sh

package-processor:
	@bash scripts/package-processor.sh

deploy-processor: package-processor
	@bash scripts/deploy-processor.sh

package-searcher:
	@bash scripts/package-searcher.sh

deploy-searcher: package-searcher
	@bash scripts/deploy-searcher.sh

deploy-frontend:
	@bash scripts/deploy-frontend.sh

neon-tags:
	psql "$(NEON_DATABASE_URL)" -c 'SELECT name, COUNT(pt.photo_id) AS photo_count FROM tags JOIN photo_tags pt ON pt.tag_id = tags.id GROUP BY name ORDER BY photo_count DESC, name;'

neon-clean-tags:
	psql "$(NEON_DATABASE_URL)" -c 'DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM photo_tags);'

neon-stats:
	psql "$(NEON_DATABASE_URL)" -c 'SELECT (SELECT COUNT(*) FROM photos) AS photos, (SELECT COUNT(*) FROM tags) AS tags;' -c 'SELECT name, COUNT(pt.photo_id) AS photo_count FROM tags JOIN photo_tags pt ON pt.tag_id = tags.id GROUP BY name ORDER BY photo_count DESC, name LIMIT 5;'

neon-sync-check:
	python scripts/sync_check.py

neon-errors:
	psql "$(NEON_DATABASE_URL)" -c 'SELECT s3_key, last_error FROM photos WHERE last_error IS NOT NULL ORDER BY s3_key;'

neon-no-tags:
	psql "$(NEON_DATABASE_URL)" -c 'SELECT p.s3_key, p.processed_at FROM photos p WHERE p.processed_at IS NOT NULL AND NOT EXISTS (SELECT 1 FROM photo_tags pt WHERE pt.photo_id = p.id) ORDER BY p.processed_at;'

neon-reprocess-errors:
	python scripts/reprocess_errors.py

neon-clean-orphans:
	python scripts/clean_orphans.py

clean:
	rm -rf dist/ lambda/__pycache__ db/__pycache__ scripts/__pycache__ features/__pycache__

