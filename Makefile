include .env
export

CONTAINER_NAME = phototagger-db

.PHONY: install db-start db-shell db-stop migrate test

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

test:
	behave
