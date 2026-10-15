# 07: Ticket ↔ Sprint Assignment

**What to build:** Assign/unassign tickets to sprints (one sprint per ticket). Sprint detail view shows tickets grouped by status.

**Blocked by:** 04, 06

**Status:** ready-for-agent

- [x] API: `POST /api/v1/sprints/{id}/tickets/{ticket_id}` — assign ticket to sprint (fails if ticket already in another sprint)
- [x] API: `DELETE /api/v1/sprints/{id}/tickets/{ticket_id}` — unassign ticket from sprint
- [ ] API: `GET /api/v1/sprints/{id}` returns sprint with nested tickets grouped by status
- [x] Ticket model: `sprint_id` FK (nullable), enforced unique per ticket via DB constraint
- [x] Web: Sprint detail page `GET /sprints/{id}` — columns for each status (Open, Groomed, In Progress, Ready for Review, Complete, Rejected) showing tickets as cards
  - HTMX: drag-drop not required; "Move to Sprint" dropdown on ticket card in backlog → `hx-post` to assign
  - Ticket card in sprint view shows "Remove from Sprint" button → `hx-delete`
- [x] Web: Backlog view adds "Sprint" column + filter; unassigned tickets show "—"
- [x] Validation: cannot assign ticket to sprint if already assigned (return 409 with current sprint info)
- [x] Unit tests: assign, unassign, double-assign prevention, sprint deletion cascades (unassigns tickets)

## Answer

**Verified on branch `jackrabbit-integration`. 7 of 8 criteria checked; criterion 3 left unchecked due to an endpoint-shape deviation (functionality exists, but at a different URL).**

### Criterion verdicts

1. **POST assign endpoint — satisfied.** `jackrabbit/api.py:251` (`POST /api/v1/sprints/{sprint_id}/tickets/{ticket_id}`) delegates to `SprintService.assign_ticket_to_sprint` (`jackrabbit/services.py:745`), which raises `ValueError("Ticket is already assigned to sprint {id}")` when the ticket is in another sprint. Tests: `tests/integration/test_sprint_api.py::test_assign_ticket_to_sprint`, `::test_assign_nonexistent_ticket_to_sprint_returns_404`, `::test_assign_ticket_to_nonexistent_sprint_returns_404`; unit tests `tests/unit/test_sprint_service.py::TestAssignTicketToSprint` (assign, reassign-to-same-sprint allowed, missing sprint/ticket).

2. **DELETE unassign endpoint — satisfied.** `jackrabbit/api.py:270` delegates to `SprintService.unassign_ticket_from_sprint` (`jackrabbit/services.py:766`), which nulls `sprint_id` and rejects wrong-sprint calls. Tests: `test_unassign_ticket_from_sprint`, unit `TestUnassignTicketFromSprint` (incl. `test_unassign_from_wrong_sprint_raises`).

3. **GET /sprints/{id} with nested tickets grouped by status — NOT satisfied as written (left unchecked).** `GET /api/v1/sprints/{id}` (`jackrabbit/api.py:148`) returns `SprintReadWithTickets` — nested tickets as a *flat* list plus a derived sprint status (`jackrabbit/schemas.py:138`). Status grouping is exposed by a *separate* endpoint, `GET /api/v1/sprints/{id}/by-status` (`api.py:176`, `services.get_sprint_with_tickets_by_status` at `services.py:788`), which the web sprint detail page consumes. The grouping capability is fully implemented and tested (`test_get_sprint_by_status` asserts all six status buckets), but the criterion names the `/sprints/{id}` URL specifically, so I left it unchecked.

4. **Ticket model `sprint_id` FK — satisfied.** `jackrabbit/models.py:80`: `sprint_id: int | None = Field(default=None, foreign_key="sprint.id", index=True)` — nullable FK, indexed. "One sprint per ticket" is enforced structurally by the single scalar FK column plus the service-level conflict check; note there is no literal DB UNIQUE constraint on `sprint_id` (and such a constraint would be semantically wrong — many tickets share one sprint). The invariant itself is verified by tests.

5. **Web sprint detail page — satisfied (minor path deviation).** `jackrabbit/web.py:174-222` serves `sprint_detail.html` at `GET /sprints/{sprint_id}/detail` and `GET /sprint/{sprint_id}` (not literally `/sprints/{id}`, which is reserved for the API). `jackrabbit/templates/sprint_detail.html:51` loops over all six statuses (Open, Groomed, In Progress, Ready for Review, Complete, Rejected) as columns with ticket cards; the sprint-view card includes a "Remove from Sprint" button with `hx-delete` (`sprint_detail.html:104`). HTMX assign path: "Move to Sprint" dropdown on the backlog ticket row (`jackrabbit/templates/ticket_row.html:114-125`, included by `backlog.html:147`) uses `hx-post` to the assign endpoint; drag-drop not implemented, matching the criterion's "not required".

6. **Backlog Sprint column + filter — satisfied.** `backlog.html:139` adds the "Sprint" column header; `backlog.html:66-77` adds the Sprint filter dropdown; `web.py:48` accepts `sprint_id` and passes it into `TicketService.list_tickets` (`services.py:471-473` filters by `Ticket.sprint_id`). Unassigned tickets render `—` (`ticket_row.html:70-72`). *Gap noted:* the "No Sprint" option (`sprint_id=0`, `backlog.html:71`) does not actually filter, because `if sprint_id:` in `services.py:471` is falsy for `0` — filtering by a specific sprint works, but filtering for unassigned tickets silently returns everything.

7. **409 with current sprint info — satisfied.** `api.py:259-262` maps the "already assigned to sprint" `ValueError` to HTTP 409; the detail message includes the current sprint id (`services.py:757`). Test: `test_assign_ticket_already_in_another_sprint_returns_409` asserts 409 and the message.

8. **Tests for assign/unassign/double-assign/cascade — satisfied.** Unit: `tests/unit/test_sprint_service.py` `TestAssignTicketToSprint::test_assign_to_other_sprint_raises`, `TestUnassignTicketFromSprint::test_unassign_ticket`. Cascade (sprint deletion unassigns tickets, `sprint_id` → NULL): `tests/integration/test_sprint_api.py::test_sprint_deletion_cascades_unassigns_tickets`.

### Commands run
- `uv run pytest tests/unit/test_sprint_service.py tests/integration/test_sprint_api.py -q` → **54 passed**
- `uv run pytest tests/unit tests/integration -rf -q` → 6 failed, 250 passed — all failures are in unrelated files (`test_move_project.py`, `test_transitions.py`) and are cross-test-isolation flakiness (OperationalError in setup); those files pass in isolation (65 passed when run alone). Not related to ticket 07.

### Gaps / residual risks
- Criterion 3's exact URL contract differs from the implementation (grouping lives at `/sprints/{id}/by-status`).
- Backlog "No Sprint" filter (`sprint_id=0`) is a no-op due to falsy-0 handling in `services.py:471`.
- Sprint deletion relies on ORM/session behavior to null out tickets (no explicit `ondelete="SET NULL"` / cascade config on the FK in `models.py`); the integration test proves current SQLite behavior works, but a different backend could differ.
- Unrelated test-isolation failures in `test_move_project.py` / `test_transitions.py` when the full suite runs together.