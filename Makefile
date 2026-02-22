include .env
export

CONTAINER_NAME = phototagger-db

.PHONY: install db-start db-shell db-stop migrate migrate-neon test process search db-drop package-processor deploy-processor

install:
	pip install -r requirements.txt

db-start:
	@bash scripts/db-start.sh

db-shell:
	docker exec -it $(CONTAINER_NAME) psql -U $(DB_USER) -d $(DB_NAME)

db-stop:
	docker stop $(CONTAINER_NAME)

migrate:
	python db/migrate.py

migrate-neon:
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

