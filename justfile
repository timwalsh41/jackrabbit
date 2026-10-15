# Jackrabbit justfile
# Alternative to Makefile with better syntax and features

# Default recipe
default: help

# Help
help:
	@echo "Jackrabbit - Ticket tracking and sprint management system"
	@echo ""
	@echo "Available recipes:"
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
	@echo "  migrate-create  - Create a new migration (usage: just migrate-create 'message')"
	@echo "  migrate-history - Show migration history"
	@echo "  clean           - Clean up generated files"

# Variables
UV := uv
PYTHON := python
PLAYWRIGHT := playwright

# Installation
install:
	{{UV}} sync --no-dev

dev-install:
	{{UV}} sync --all-extras
	{{UV}} run {{PLAYWRIGHT}} install --with-deps chromium

# Test recipes
test:
	just test-unit
	just test-int
	just test-e2e

test-unit:
	{{UV}} run pytest tests/unit -v --tb=short

test-int:
	{{UV}} run pytest tests/integration -v --tb=short

test-e2e:
	@echo "Starting test server..."
	{{UV}} run {{PYTHON}} -m jackrabbit.main &
	SERVER_PID=$!
	echo "Waiting for server..."
	for i in {1..30}; do
		if curl -s http://localhost:8080/health > /dev/null; then
			echo "Server ready"
			break
		fi
		sleep 0.5
	done
	E2E_BASE_URL=http://localhost:8080 {{UV}} run pytest tests/e2e -v --tb=short
	TEST_EXIT=$?
	kill $SERVER_PID 2>/dev/null || true
	exit $TEST_EXIT

test-e2e-headed:
	@echo "Starting test server..."
	{{UV}} run {{PYTHON}} -m jackrabbit.main &
	SERVER_PID=$!
	echo "Waiting for server..."
	for i in {1..30}; do
		if curl -s http://localhost:8080/health > /dev/null; then
			echo "Server ready"
			break
		fi
		sleep 0.5
	done
	E2E_BASE_URL=http://localhost:8080 PLAYWRIGHT_BROWSER=chromium CHROME_DEVTOOLS_AXI_HEADED=1 {{UV}} run pytest tests/e2e -v --tb=short
	TEST_EXIT=$?
	kill $SERVER_PID 2>/dev/null || true
	exit $TEST_EXIT

test-e2e-firefox:
	@echo "Starting test server..."
	{{UV}} run {{PYTHON}} -m jackrabbit.main &
	SERVER_PID=$!
	echo "Waiting for server..."
	for i in {1..30}; do
		if curl -s http://localhost:8080/health > /dev/null; then
			echo "Server ready"
			break
		fi
		sleep 0.5
	done
	E2E_BASE_URL=http://localhost:8080 PLAYWRIGHT_BROWSER=firefox {{UV}} run pytest tests/e2e -v --tb=short
	TEST_EXIT=$?
	kill $SERVER_PID 2>/dev/null || true
	exit $TEST_EXIT

test-e2e-webkit:
	@echo "Starting test server..."
	{{UV}} run {{PYTHON}} -m jackrabbit.main &
	SERVER_PID=$!
	echo "Waiting for server..."
	for i in {1..30}; do
		if curl -s http://localhost:8080/health > /dev/null; then
			echo "Server ready"
			break
		fi
		sleep 0.5
	done
	E2E_BASE_URL=http://localhost:8080 PLAYWRIGHT_BROWSER=webkit {{UV}} run pytest tests/e2e -v --tb=short
	TEST_EXIT=$?
	kill $SERVER_PID 2>/dev/null || true
	exit $TEST_EXIT

# Test with coverage
test-cov:
	{{UV}} run pytest tests/unit tests/integration --cov=jackrabbit --cov-report=term-missing --cov-report=html

test-cov-unit:
	{{UV}} run pytest tests/unit --cov=jackrabbit --cov-report=term-missing

test-cov-int:
	{{UV}} run pytest tests/integration --cov=jackrabbit --cov-report=term-missing

# Linting and formatting
lint:
	{{UV}} run ruff check .

lint-fix:
	{{UV}} run ruff check . --fix

format:
	{{UV}} run ruff format .

format-check:
	{{UV}} run ruff format --check .

# Type checking
typecheck:
	{{UV}} run mypy .

# Combined check
check:
	just lint
	just typecheck

# Migration recipes
migrate:
	{{UV}} run {{PYTHON}} -m jackrabbit.database

migrate-create msg:
	{{UV}} run alembic revision --autogenerate -m "{{msg}}"

migrate-history:
	{{UV}} run alembic history

migrate-current:
	{{UV}} run alembic current

migrate-upgrade rev:
	{{UV}} run alembic upgrade "{{rev}}"

migrate-downgrade rev:
	{{UV}} run alembic downgrade "{{rev}}"

# Database recipes
db-init:
	{{UV}} run {{PYTHON}} -c "from jackrabbit.database import init_db; init_db()"

db-reset:
	rm -f data/jackrabbit.db
	{{UV}} run {{PYTHON}} -c "from jackrabbit.database import init_db; init_db()"

db-seed:
	{{UV}} run {{PYTHON}} -m jackrabbit.cli seed

# Development server
dev:
	{{UV}} run {{PYTHON}} -m jackrabbit.main

dev-reload:
	{{UV}} run uvicorn jackrabbit.main:create_app --factory --reload --port 8080

# Build
build:
	{{UV}} build

# Clean
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	rm -rf test-results playwright-report
	rm -rf dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true

# Pre-commit
pre-commit-install:
	{{UV}} run pre-commit install

pre-commit-run:
	{{UV}} run pre-commit run --all-files

# CI simulation
ci:
	just check
	just test

# Watch mode
watch-test:
	{{UV}} run pytest-watch tests/unit

watch-lint:
	watchexec -e py "just lint"

# Docker (if Dockerfile exists)
docker-build:
	docker build -t jackrabbit:latest .

docker-run:
	docker run -p 8080:8080 -v $(PWD)/data:/app/data jackrabbit:latest

docker-test:
	docker run --rm jackrabbit:latest just test