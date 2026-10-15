# Jackrabbit Makefile
# Provides convenient targets for development and CI tasks

.PHONY: help install dev-install test test-unit test-int test-e2e lint typecheck format check migrate migrate-create migrate-history clean

# Default target
help:
	@echo "Jackrabbit - Ticket tracking and sprint management system"
	@echo ""
	@echo "Available targets:"
	@echo "  help            - Show this help message"
	@echo "  install         - Install production dependencies"
	@echo "  dev-install     - Install all dependencies including dev tools"
	@echo "  test            - Run all tests (unit + integration + e2e)"
	@echo "  test-unit       - Run unit tests only"
	@echo "  test-int        - Run integration tests only"
	@echo "  test-e2e        - Run end-to-end tests only"
	@echo "  lint            - Run ruff linter"
	@echo "  typecheck       - Run mypy type checker"
	@echo "  format          - Format code with ruff"
	@echo "  check           - Run lint + typecheck (quick CI check)"
	@echo "  migrate         - Run database migrations to head"
	@echo "  migrate-create  - Create a new migration (usage: make migrate-create MSG='message')"
	@echo "  migrate-history - Show migration history"
	@echo "  clean           - Clean up generated files"

# Installation targets
install:
	uv sync --no-dev

dev-install:
	uv sync --all-extras
	uv run playwright install --with-deps chromium

# Test targets
test: test-unit test-int test-e2e

test-unit:
	uv run pytest tests/unit -v --tb=short

test-int:
	uv run pytest tests/integration -v --tb=short

test-e2e:
	@echo "Starting test server..."
	@uv run python -m jackrabbit.main & \
	SERVER_PID=$$!; \
	echo "Waiting for server..."; \
	for i in {1..30}; do \
		if curl -s http://localhost:8080/health > /dev/null; then \
			echo "Server ready"; \
			break; \
		fi; \
		sleep 0.5; \
	done; \
	E2E_BASE_URL=http://localhost:8080 uv run pytest tests/e2e -v --tb=short; \
	TEST_EXIT=$$?; \
	kill $$SERVER_PID 2>/dev/null || true; \
	exit $$TEST_EXIT

test-e2e-headed:
	@echo "Starting test server..."
	@uv run python -m jackrabbit.main & \
	SERVER_PID=$$!; \
	echo "Waiting for server..."; \
	for i in {1..30}; do \
		if curl -s http://localhost:8080/health > /dev/null; then \
			echo "Server ready"; \
			break; \
		fi; \
		sleep 0.5; \
	done; \
	E2E_BASE_URL=http://localhost:8080 PLAYWRIGHT_BROWSER=chromium CHROME_DEVTOOLS_AXI_HEADED=1 uv run pytest tests/e2e -v --tb=short; \
	TEST_EXIT=$$?; \
	kill $$SERVER_PID 2>/dev/null || true; \
	exit $$TEST_EXIT

test-e2e-firefox:
	@echo "Starting test server..."
	@uv run python -m jackrabbit.main & \
	SERVER_PID=$$!; \
	echo "Waiting for server..."; \
	for i in {1..30}; do \
		if curl -s http://localhost:8080/health > /dev/null; then \
			echo "Server ready"; \
			break; \
		fi; \
		sleep 0.5; \
	done; \
	E2E_BASE_URL=http://localhost:8080 PLAYWRIGHT_BROWSER=firefox uv run pytest tests/e2e -v --tb=short; \
	TEST_EXIT=$$?; \
	kill $$SERVER_PID 2>/dev/null || true; \
	exit $$TEST_EXIT

test-e2e-webkit:
	@echo "Starting test server..."
	@uv run python -m jackrabbit.main & \
	SERVER_PID=$$!; \
	echo "Waiting for server..."; \
	for i in {1..30}; do \
		if curl -s http://localhost:8080/health > /dev/null; then \
			echo "Server ready"; \
			break; \
		fi; \
		sleep 0.5; \
	done; \
	E2E_BASE_URL=http://localhost:8080 PLAYWRIGHT_BROWSER=webkit uv run pytest tests/e2e -v --tb=short; \
	TEST_EXIT=$$?; \
	kill $$SERVER_PID 2>/dev/null || true; \
	exit $$TEST_EXIT

# Run tests with coverage
test-cov:
	uv run pytest tests/unit tests/integration --cov=jackrabbit --cov-report=term-missing --cov-report=html

test-cov-unit:
	uv run pytest tests/unit --cov=jackrabbit --cov-report=term-missing

test-cov-int:
	uv run pytest tests/integration --cov=jackrabbit --cov-report=term-missing

# Linting and formatting
lint:
	uv run ruff check .

lint-fix:
	uv run ruff check . --fix

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

# Type checking
typecheck:
	uv run mypy .

# Combined check (for CI)
check: lint typecheck

# Migration targets
migrate:
	uv run python -m jackrabbit.database

migrate-create:
	@if [ -z "$(MSG)" ]; then \
		echo "Usage: make migrate-create MSG='migration message'"; \
		exit 1; \
	fi
	uv run alembic revision --autogenerate -m "$(MSG)"

migrate-history:
	uv run alembic history

migrate-current:
	uv run alembic current

migrate-upgrade:
	@if [ -z "$(REV)" ]; then \
		echo "Usage: make migrate-upgrade REV=revision"; \
		exit 1; \
	fi
	uv run alembic upgrade $(REV)

migrate-downgrade:
	@if [ -z "$(REV)" ]; then \
		echo "Usage: make migrate-downgrade REV=revision"; \
		exit 1; \
	fi
	uv run alembic downgrade $(REV)

# Database targets
db-init:
	uv run python -c "from jackrabbit.database import init_db; init_db()"

db-reset:
	rm -f data/jackrabbit.db
	uv run python -c "from jackrabbit.database import init_db; init_db()"

db-seed:
	uv run python -m jackrabbit.cli seed

# Development server
dev:
	uv run python -m jackrabbit.main

dev-reload:
	uv run uvicorn jackrabbit.main:create_app --factory --reload --port 8080

# Build and package
build:
	uv build

# Clean up
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	rm -rf test-results playwright-report
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Pre-commit
pre-commit-install:
	uv run pre-commit install

pre-commit-run:
	uv run pre-commit run --all-files

# CI simulation
ci: check test

# Watch mode for development
watch-test:
	uv run pytest-watch tests/unit

watch-lint:
	watchexec -e py "make lint"

# Docker targets (if Dockerfile exists)
docker-build:
	docker build -t jackrabbit:latest .

docker-run:
	docker run -p 8080:8080 -v $(PWD)/data:/app/data jackrabbit:latest

docker-test:
	docker run --rm jackrabbit:latest make test