# 02: Database layer & migrations

**What to build:** SQLite engine with WAL mode, SQLModel session management, Alembic migration setup. On startup, `alembic upgrade head` runs automatically. Initial migration creates all 5 tables (project, ticket, sprint, ticket_link, ticket_transition) and seeds the UNS project.

**Blocked by:** 01

**Status:** resolved

- [ ] `database.py`: SQLite engine with `PRAGMA journal_mode=WAL`, session factory, `init_db()` runs migrations
- [ ] `alembic.ini` + `alembic/env.py` configured to read `DATABASE_URL` from settings
- [ ] `alembic revision --autogenerate -m "initial schema"` creates `0001_initial.py`
- [ ] Migration creates tables per ADR-0016/0015/0017 schema:
  - `project`: id, prefix, name, description, color, is_system, created_at
  - `ticket`: id, project_id, number, type, status, title, description, priority, story_points, sprint_id, branch_name, pr_url, approach, files_to_change, test_plan, validation_steps, created_at, updated_at, UNIQUE(project_id, number)
  - `sprint`: id, number, planned_start, planned_duration_days, actual_start, actual_finish, created_at
  - `ticket_link`: id, source_ticket_id, target_ticket_id, link_type, created_at, UNIQUE(source, target, type)
  - `ticket_transition`: id, ticket_id, from_status, to_status, reason, at
- [ ] UNS project seeded in migration: `INSERT INTO project (prefix, name, description, color, is_system) VALUES ('UNS', 'Unsorted', 'Default project for tickets without a project', '#6b7280', true)`
- [ ] `alembic upgrade head` runs on app startup (idempotent)
- [ ] Test: fresh DB → startup → tables exist + UNS present