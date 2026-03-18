include .env
export

CONTAINER_NAME = phototagger-db

.PHONY: install local-db-start local-db-shell local-db-stop local-migrate neon-migrate test process search db-drop package-processor deploy-processor package-searcher deploy-searcher neon-tags deploy-frontend help clean

help:
	@echo "Local development:"
	@echo "  make install          Install Python dependencies"
	@echo "  make local-db-start   Start local Postgres container"
	@echo "  make local-db-stop    Stop local Postgres container"
	@echo "  make local-db-shell   Open a psql session"
	@echo "  make local-migrate    Apply pending migrations locally"
	@echo "  make db-drop          Drop all local tables (prompts for confirmation)"
	@echo "  make test             Run BDD tests"
	@echo "  make process DIR=...  Run processor against a directory of images"
	@echo "  make search           Run searcher locally"
	@echo "  make clean            Remove build artifacts"
	@echo ""
	@echo "AWS deployment:"
	@echo "  make neon-migrate     Apply pending migrations to Neon"
	@echo "  make neon-tags        Show tag counts from Neon"
	@echo "  make deploy-processor Build and deploy the processor Lambda"
	@echo "  make deploy-searcher  Build and deploy the searcher Lambda"
	@echo "  make deploy-frontend  Upload frontend to S3"

install:
	pip install -r requirements.txt

local-db-start:
	@bash scripts/db-start.sh

local-db-shell:
	docker exec -it $(CONTAINER_NAME) psql -U $(DB_USER) -d $(DB_NAME)

local-db-stop:
	docker stop $(CONTAINER_NAME)

local-migrate:
	python db/migrate.py

neon-migrate:
	python db/migrate.py $(NEON_DATABASE_URL)

test:
	behave

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
	psql "$(NEON_DATABASE_URL)" -c "SELECT name, COUNT(pt.photo_id) AS photo_count FROM tags JOIN photo_tags pt ON pt.tag_id = tags.id GROUP BY name ORDER BY photo_count DESC, name;"

clean:
	rm -rf dist/ lambda/__pycache__ db/__pycache__ scripts/__pycache__ features/__pycache__

