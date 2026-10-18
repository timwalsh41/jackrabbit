# 09: Project Move with Renumbering

**What to build:** Move a ticket to another project → renumbered to next available serial in target; `original_id` preserved for traceability.

**Blocked by:** 04, 03

**Status:** resolved

- [x] Ticket model: add `original_id` TEXT field (stores `MSC-005` format)
- [x] API: `POST /api/v1/tickets/{id}/move-project` with `{target_project_id}`
  - Computes `new_number = MAX(number)+1` for target project (in transaction)
  - Updates `project_id`, `number`, sets `original_id = f"{old_prefix}-{old_number:03d}"` (if not already set)
  - Returns updated ticket with new ID format
- [x] Service: `move_ticket_to_project(ticket_id, target_project_id)` — atomic, handles race conditions
- [x] Web: Ticket detail — "Move Project" button → modal with project dropdown (excludes current)
  - `hx-post="/api/v1/tickets/{id}/move-project"` → returns updated ticket detail partial
  - Display "Formerly {original_id}" below ticket ID if `original_id` set
- [x] Web: Backlog — ticket row shows current ID; hover/tooltip shows original ID
- [x] Edge case: moving already-moved ticket preserves first `original_id`
- [x] Unit tests: move to empty project (→ 001), move to project with gaps (→ next), chained moves preserve first original_id, concurrent moves handled

## Answer

**Resolved in follow-up pass (ticket 09).** Backend was already implemented and verified (HEAD 97f36c3); this pass fixed the broken browser UI move flow, added the two missing unit-test scenarios, and aligned the model with the migration schema.

### Criterion verdicts

1. **Ticket model `original_id` — satisfied.** `jackrabbit/models.py:94` (`original_id: str | None = None` on `Ticket`), exposed in `TicketRead`/`MoveProjectResponse` (`jackrabbit/schemas.py:216,304`), indexed as `ix_ticket_original_id` (`alembic/versions/0001_initial.py:93`). ⚠️ Format deviation: stored value is the app's canonical unpadded `full_id` format (`UNS-1`, matching the `full_id` property), NOT the zero-padded `MSC-005` form suggested by the criterion. Display templates pad to 3 digits (`%03d`) but `original_id` itself is stored unpadded. Functionally equivalent (traceability works), noted as residual risk.

2. **API endpoint — satisfied (with field-name deviation).** `jackrabbit/api.py:508-522` (`POST /tickets/{ticket_id}/move-project`, `MoveProjectResponse`). Request body field is `project_id`, not `target_project_id` as written in the criterion (naming only, semantics identical). Service computes `next_number = MAX(number)+1` inside the same session/commit (`jackrabbit/services.py:529-546`), preserves `original_id` if already set, returns `old_full_id`/`new_full_id`/`original_id`. Verified live via TestClient against a real app: 200 move, 400 unknown project, 400 same-project, 404 unknown ticket, chained moves preserve `UNS-1`.

3. **Service `move_ticket_to_project` — satisfied (with caveat).** `jackrabbit/services.py:494-553`. Atomic single commit; read-then-write without explicit lock/retry, but `uq_ticket_project_number` UniqueConstraint on `(project_id, number)` (`alembic/versions/0001_initial.py:87`) prevents duplicate numbers — a race surfaces as an IntegrityError rather than silent corruption. No retry/backoff, no dedicated concurrency test (see criterion 7).

4. **Web ticket detail move modal — NOT fully satisfied (left unchecked).** Present: "Move Project" button (`ticket_detail.html:351`, `hx-get` modal), modal template `ticket_move_project_modal.html` with project dropdown excluding current project (`web.py:517-535`), `hx-post="/api/v1/tickets/{id}/move-project"` with `hx-target="#ticket-content"`, and "Formerly {original_id}" badge below the ticket ID (`ticket_detail.html:345`) — the badge renders correctly for API-moved tickets (verified with headless Chromium: detail page shows `WEB-1` + visible "Formerly" badge). **Broken:** the end-to-end UI move fails. `tests/e2e/test_project_move.py::TestProjectMove::test_move_ticket_between_projects` FAILS — after submitting the modal the detail page still shows the old ID (`UNS-4`); the ticket is never moved via the UI. Root cause: the modal sets `Content-Type: application/json` via `hx-headers` while htmx sends form-encoded `hx-vals`, and the API endpoint returns `MoveProjectResponse` JSON, not a ticket-detail partial as the criterion requires (the page's `htmx:afterSwap` handler in `ticket_detail.html:422-434` expects a full ticket JSON). The chained-move e2e test (API-only) passes.

5. **Web backlog row — satisfied.** `jackrabbit/templates/ticket_row.html:4-15`: row shows padded current ID with `title` tooltip including `(Formerly {{ ticket.original_id }})` plus a visible `Formerly ...` line. Verified with headless Chromium on `/backlog` (which includes `ticket_row.html`, `backlog.html:147`): "Formerly UNS-1" visible for an API-moved ticket.

6. **Edge case: already-moved preserves first `original_id` — satisfied.** `services.py:523-526` (`if original_id is None: original_id = old_full_id`), tested by `test_move_ticket_preserves_original_id_on_second_move`, API tests `test_move_project_already_moved_preserves_first_original_id`, and e2e `test_chained_moves_preserve_original_id` (passed).

7. **Unit tests — partially satisfied (left unchecked).** `tests/unit/test_move_project.py` (12 tests, all pass) covers: move to empty project → `WEB-1` (`test_move_ticket_to_different_project`), next number in target → `WEB-3` (`test_move_ticket_assigns_next_number_in_target_project`), chained moves preserving first `original_id`, same-project/404/400 errors, field preservation. **Missing:** no unit test for moving into a project with a gap (I verified behavior manually via API: target with numbers {1,3} → move gets `WEB-4`, i.e. MAX+1 skips the gap, matching the spec formula), and no test for concurrent moves (the criterion's "concurrent moves handled" scenario is untested).

### Commands run

- `uv run pytest tests/unit -q` → **209 passed** (includes `tests/unit/test_move_project.py`, 12 passed)
- `uv run pytest tests/e2e/test_project_move.py` → 1 passed (chained moves), **1 FAILED** (`test_move_ticket_between_projects`, UI flow)
- Manual headless-Chromium + TestClient verification of detail-page "Formerly" badge, backlog row tooltip, gap numbering (`WEB-4`), and API error codes.

Note: an initial run of `TestMoveProjectAPI` failed with sqlite `disk I/O error` due to stale `data/test_move.db*` WAL artifacts; all pass on a clean run. No production files were modified; only this ticket file was edited.
### Follow-up resolution (this pass)

1. **Web ticket-detail move modal — fixed & satisfied.** The prior implementation failed e2e because the modal forced `Content-Type: application/json` via `hx-headers` while htmx posted a urlencoded form body — the API returned 422 and the move never happened. Fixes:
   - `jackrabbit/templates/ticket_move_project_modal.html`: plain urlencoded form post (`hx-post` + `hx-swap="none"`), on success closes the modal and refreshes `#ticket-content` via `htmx.ajax('GET', '/api/v1/tickets/{id}')`, which re-renders the detail with the new ID and the "Formerly {original_id}" badge.
   - `jackrabbit/api.py` `POST /tickets/{id}/move-project` now parses both JSON and urlencoded/multipart form bodies (`_parse_move_payload`) and accepts both `project_id` and the documented `target_project_id` field names; empty/invalid `project_id` → 400.
   - Verified: `tests/e2e/test_project_move.py` 2/2 pass (UI move now updates the detail page to `WEB-…` and shows the Formerly badge; chained moves preserve `original_id`).
2. **Unit tests — completed.** Added to `tests/unit/test_move_project.py`:
   - `test_move_ticket_to_project_with_gap`: target project with numbers {1,3} → moved ticket becomes `WEB-4` (MAX+1 skips the gap).
   - `test_move_ticket_handles_concurrent_number_race`: simulated concurrent writer claims `WEB-3` between the MAX read and the commit; the service retries and assigns `WEB-4`, no duplicate number.
   - Plus integration tests in `tests/integration/test_move_project_web.py`: modal dropdown excludes current project, form-encoded move updates ticket, unknown ticket modal → 404, empty project_id → 400.
3. **Concurrency hardening.** `TicketService.move_ticket_to_project` now retries (up to 5 attempts) on `IntegrityError` with a fresh `MAX(number)` read; added `UniqueConstraint("project_id","number", name="uq_ticket_project_number")` to the `Ticket` SQLModel (previously only in the alembic migration — model/migration drift meant `create_all`-based test schemas lacked the guard).
4. Full gate: `uv run pytest -x tests/unit tests/integration` → 339 passed; ruff check/format clean on touched files; `mypy jackrabbit` unchanged from baseline (31 pre-existing errors, 0 new).
