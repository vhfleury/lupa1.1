.PHONY: up down test lint typecheck format migrate verificar

up:
	docker compose up -d --build --wait

down:
	docker compose down

test:
	docker compose exec api python -m pytest

lint:
	docker compose exec api python -m ruff check src tests

typecheck:
	docker compose exec api python -m mypy src tests

format:
	python -m ruff format src tests
	python -m ruff check --fix src tests

migrate:
	docker compose exec api alembic upgrade head

verificar:
	docker compose exec api bash scripts/verificar.sh
