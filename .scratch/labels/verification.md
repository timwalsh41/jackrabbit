# Verification

How agents prove their work is correct in this repo. Skills that need a check (`implement-spec`, `code-review`, `tdd`, `implement`, `retro`) read the commands here instead of guessing at the stack.

## Commands

- **Full suite:** `uv run pytest -x` — unit + integration + the Playwright browser tier. (`make test` runs the same three tiers as separate jobs, the way CI does.)
- **Fast subset:** `uv run pytest -x tests/unit tests/integration`, or equivalently `uv run pytest -x -m "not e2e"` — everything except the browser suite. Use this to gate work in the middle of a run when the e2e tier is owned by a later ticket.
- **Single test:** `uv run pytest tests/unit/test_tickets.py::test_status_transition -x -q` (replace the path::name with the failing node id from the gate output).
- **Static checks:** `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy`
- **Check timeout:** `900000` (15 min) — the full suite outruns the harness's default gate cap, so verification steps must set this explicitly rather than accept the default.

The browser tier needs Chromium installed (`make dev-install` does `uv run playwright install --with-deps chromium`) and starts the app itself on a free port via `tests/e2e/conftest.py`. Where it can't run, use the fast subset and say so — never mark work verified on a gate that skipped e2e silently.

Prefer these commands over hand-assembled ones; they're the same ones `.github/workflows/ci.yml` gates on.

## Branches

- **Base branch:** `main` (`origin/HEAD` is unset locally; `main` is what the remote gates on).
- **Integration branch naming:** `<feature-slug>-integration` — e.g. `jackrabbit-integration` for the original Kanban spec. Tickets for one spec land on that single branch, and it is never `main`.

## Pull requests

- **PR surface:** yes
- **How to open one:** `gh-axi pr create --title "..." --body-file <file> --base main --head <integration-branch>` (`gh-axi` is the repo's `gh` wrapper on `PATH`). PRs are opened only once the full-suite gate is green on the integration branch.
