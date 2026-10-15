# 14: Unit & Integration Tests

**What to build:** Comprehensive unit tests for services and integration tests for all API endpoints.

**Blocked by:** 04, 05, 06, 07, 08, 09, 10, 13

**Status:** resolved

- [ ] **Unit tests** (`tests/unit/`):
  - `test_ticket_service.py`: `generate_branch_name`, `slugify`, `can_transition` (all 30+ combos), `move_ticket_to_project` (renumbering, original_id), `assign_to_sprint`
  - `test_sprint_service.py`: `next_sprint_number`, `sprint_status_derived`
  - `test_project_service.py`: `next_ticket_number`, `validate_prefix`
  - `test_link_service.py`: `add_link` (all 5 types, inverses, validation), `get_blockers`, `get_children`
- [ ] **Integration tests** (`tests/integration/`):
  - `test_tickets_api.py`: CRUD, filtering, pagination, transitions (guarded/unguarded), links, project move, branch/PR
  - `test_projects_api.py`: CRUD, UNS protection, ticket counts
  - `test_sprints_api.py`: CRUD, ticket assignment, status derivation
  - `test_links_api.py`: add/remove all types, symmetric relates_to, blocker queries
  - `test_migrations.py`: `alembic upgrade head` → `downgrade -1` → `upgrade head` round-trip
- [ ] Test DB: fresh SQLite file per test module (tmp_path), migrations applied
- [ ] Coverage target: >90% on `services/`, >80% on `api/`
- [ ] Run: `pytest tests/unit tests/integration -v --cov=jackrabbit`