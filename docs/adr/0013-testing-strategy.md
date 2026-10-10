# ADR-0013: Testing Strategy — Full Pyramid with chrome-devtools-axi

## Status
Accepted

## Context
AGENTS.md requires "appropriate and complementary unit and end-to-end test coverage." User added: agents must test E2E using `chrome-devtools-axi` during development.

## Decision
**Three-layer pyramid**:

### 1. Unit Tests (fast, isolated)
- **Target**: Service functions, model validation, utility functions, status transition guards
- **Tool**: `pytest` + `pytest-asyncio`
- **Speed**: <1s per test, run on every change
- **Coverage**: >90% of business logic

### 2. Integration Tests (API endpoints)
- **Target**: FastAPI routes, database operations, migration round-trips
- **Tool**: `pytest` + `httpx.AsyncClient` (test client) + test SQLite (`:memory:` or temp file)
- **Speed**: ~100ms per test
- **Coverage**: All API endpoints, all status transitions, all link types, sprint assignment, project move

### 3. E2E Tests (critical user flows)
- **Target**: Complete user journeys in real browser
- **Tool**: `playwright` + `chrome-devtools-axi` (for agent-driven testing)
- **Flows**:
  - Create ticket → groom → start → review → complete
  - Create sprint → add tickets → start sprint → finish sprint
  - Move ticket between projects (verify renumbering)
  - Create epic → link stories → view plan
  - Filter backlog by project/type/status
- **Speed**: ~5-10s per flow
- **Run**: Pre-commit (subset), CI (full), agent development loop (continuous)

### Agent E2E Testing with chrome-devtools-axi
- Agents use `chrome-devtools-axi` to drive real Chrome during development
- Verify UI updates after API calls
- Catch HTMX swap issues, form validation, JavaScript errors
- Integrated into agent workflow: "run the E2E test for ticket creation"

## Consequences

### Positive
- **Confidence** — unit catches logic bugs, integration catches API/DB bugs, E2E catches UI/integration bugs
- **Agent-friendly** — `chrome-devtools-axi` lets agents verify their own work
- **Fast feedback** — unit/integration run in <10s; E2E subset in <30s
- **Regression prevention** — migrations tested, status guards tested, UI flows tested

### Negative
- **More test code to maintain** — but pays off in reduced bugs
- **E2E flakiness** — mitigated by deterministic test data, retries, headless Chrome
- **chrome-devtools-axi learning curve** — but enables powerful agent verification

## Alternatives Considered
- **Unit + Integration only**: Rejected — misses HTMX swap bugs, form issues, JS errors.
- **Integration-heavy**: Rejected — unit tests catch logic errors faster and more precisely.