# ADR-0014: Schema Migrations via Alembic

## Status
Accepted

## Context
SQLite schema will evolve. Options:
- Numbered migration files (Alembic)
- Auto-migration via ORM (`SQLModel.metadata.create_all`)
- Manual SQL scripts

## Decision
**Alembic** — numbered SQL migration files, run on startup.

## Consequences

### Positive
- **Reproducible** — same migrations apply to fresh DB and existing deployments
- **Reviewable** — each migration is a `.sql`/`.py` file in `alembic/versions/`
- **Rollback support** — `alembic downgrade -1` (if written reversibly)
- **Standard** — works with SQLAlchemy/SQLModel, CI/CD integration
- **Declarative models + imperative migrations** — models in code, migrations explicit

### Negative
- **More setup** — `alembic init`, config, env.py
- **Migration authoring discipline** — must write `upgrade()`/`downgrade()` correctly

### Implementation
```
alembic/
├── env.py              # connects to DATABASE_URL, runs migrations
├── script.py.mako      # template for new migrations
└── versions/
    ├── 0001_initial.py
    ├── 0002_add_groomed_fields.py
    └── ...
```

- On app startup: `alembic upgrade head` (idempotent)
- Dev workflow: `alembic revision --autogenerate -m "description"` → edit → commit
- CI: run migrations on test DB before integration tests

## Alternatives Considered
- **Auto-migration (`create_all`)**: Rejected — no history, no rollback, no review, dangerous in production (silent schema drift).
- **Manual SQL**: Rejected — no tooling, easy to forget, no ordering guarantee.