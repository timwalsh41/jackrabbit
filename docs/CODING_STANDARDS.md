# Coding Standards

> Read during code review. Mechanical rules are enforced by tools; judgement calls by reviewer.

---

## Mechanical (Enforced by Tools)

### Git Hygiene
- `.gitignore` must exclude: `__pycache__/`, `*.py[cod]`, `*.egg-info/`, `.env`, `data/`, `*.db`, `*.sqlite*`, `.coverage`, `htmlcov/`, `.pytest_cache/`, `.vscode/`, `.idea/`, `*.swp`, `*.swo`
- No commit should introduce `git status` noise (bytecode, build artifacts, local DB, editor files)

### Format & Lint
- **Formatter**: `ruff format` (double quotes, 100 col, spaces) — CI enforces `--check`
- **Linter**: `ruff check` with `select = ["E","W","F","I","UP","B","C4","T20"]` — CI enforces
- **Pre-commit**: `ruff --fix`, `ruff format`, `mypy` run on every commit

### Types
- **Type checker**: `mypy` strict mode
  - `disallow_untyped_defs = true`
  - `check_untyped_defs = true`
  - `strict_equality = true`
  - `warn_return_any = true`
  - `warn_unused_configs = true`
- CI enforces `mypy .` with zero errors

### API Design
- **API-First**: Separate Pydantic request/response schemas in `schemas.py`
- **Never** expose SQLModel table classes directly in API responses
- **Never** use `from_attributes=True` on table models — only on schema `Read` models

### Configuration
- All settings via `pydantic-settings.BaseSettings` with validators
- No raw `os.getenv()` or `os.environ` in application code
- `.env.example` documents all keys with defaults

---

## Guardrails (CI + Pre-commit)

| Check | Tool | Runs On |
|-------|------|---------|
| Format | `ruff format --check` | Pre-commit + CI |
| Lint | `ruff check` | Pre-commit + CI |
| Types | `mypy` | Pre-commit + CI |
| Tests | `pytest` | CI only |
| Import sorting | `ruff check --select=I` | Pre-commit + CI |

**Required**: `.pre-commit-config.yaml` + `.github/workflows/ci.yml` in every repo.

---

## Judgement Calls (Reviewer Discretion)

### Test Coverage
- New features: unit tests (models, services) + integration tests (API endpoints)
- User-facing flows: e2e tests via `chrome-devtools-axi` + Playwright
- Bug fixes: regression test that fails before fix, passes after

### Error Handling
- API endpoints return structured errors (RFC 7807 `ProblemDetail` shape)
- Validation errors use `422` with field-level messages
- Internal errors use `500` with correlation ID for debugging

### HTML Templates
- Use Jinja2 partials (`{% include %}`) for reusable fragments
- No inline `<script>` in `base.html` — use HTMX attributes
- Template context variables documented in view functions

### Database Migrations
- Every schema change → Alembic migration (`alembic revision --autogenerate`)
- Migration files reviewed for correctness (no `DROP COLUMN` without data migration)
- `alembic upgrade head` runs in CI before tests

### Performance
- N+1 queries caught in code review: use `selectinload`/`joinedload` explicitly
- Pagination required on all list endpoints (`limit`/`offset` or cursor)
- Database indexes on all foreign keys and filter columns

---

## Tool Versions (Pinned in `pyproject.toml`)

| Tool | Version | Config Location |
|------|---------|-----------------|
| ruff | `>=0.5.0` | `[tool.ruff]` |
| mypy | `>=1.10.0` | `[tool.mypy]` |
| pytest | `>=8.2.0` | `[tool.pytest.ini_options]` |
| playwright | `>=1.44.0` | `tests/e2e/` |

---

## Quick Reference

```bash
# Local development
uv run ruff check . --fix
uv run ruff format .
uv run mypy .
uv run pytest

# Pre-commit install
uv run pre-commit install

# CI simulation
uv run ruff check . && uv run ruff format --check . && uv run mypy . && uv run pytest
```