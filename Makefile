.PHONY: install dev lint test evaluate verify docker

install:
	uv sync --extra dev

dev:
	uv run uvicorn app.main:app --reload

lint:
	uv run ruff check app tests scripts
	uv run ruff format --check app tests scripts

test:
	uv run pytest --cov=app --cov-report=term-missing

evaluate:
	uv run python scripts/run_evaluation.py

verify: lint test
	uv run python scripts/run_evaluation.py --check

docker:
	docker compose up --build
