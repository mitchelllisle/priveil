.DEFAULT_GOAL := help

.PHONY: help install serve test lint format

help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install all dependencies
	uv sync

serve: ## Run the server with hot-reload
	uv run uvicorn alias.app:app --reload --host 0.0.0.0 --port 8000

test: ## Run tests
	uv run pytest tests/ -v

lint: ## Lint and type-check
	uv run ruff check src/ tests/
	uv run mypy src/

format: ## Auto-fix lint issues
	uv run ruff format src/ tests/
	uv run ruff check --fix src/ tests/
