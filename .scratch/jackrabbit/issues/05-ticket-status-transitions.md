# 05: Ticket Status Transitions (Guarded)

**What to build:** State machine for ticket status with guarded forward transitions, free backward transitions, and restore from Rejected. Audit log of all transitions.

**Blocked by:** 04

**Status:** resolved

- [x] Status enum: `Open`, `Groomed`, `In Progress`, `Ready for Review`, `Complete`, `Rejected` (jackrabbit/models.py:20-26, `TicketStatus` StrEnum)
- [x] Transition rules (ADR-0009):
  - Open → Groomed: requires `approach`, `files_to_change`, `test_plan`, `validation_steps` all non-empty
  - Groomed → In Progress: requires `branch_name` non-empty (validated format)
  - In Progress → Ready for Review: requires `pr_url` non-empty (valid URL)
  - Ready for Review → Complete: requires PR merged (manual confirmation) or Spike report accepted
  - Backward (any → previous): always allowed, no guards
  - Rejected → any prior state: allowed if that state's guard criteria currently met
  - Any → Rejected: always allowed
- [x] API: `POST /api/v1/tickets/{id}/transition` with `{to_status, reason}` → validates guard, updates ticket, writes `ticket_transition` audit row (jackrabbit/api.py:467-507; 400 on guard failure at api.py:506-507)
- [x] Service: `can_transition(ticket, to_status)` returns `(bool, error_message)` (jackrabbit/services.py:324)
- [x] Service: `transition(ticket, to_status, reason)` — atomic update + audit (jackrabbit/services.py:401-446; status update + `Transition` row added, single `commit()`)
- [x] Web: Ticket detail shows current status badge + action buttons for valid next states (jackrabbit/templates/ticket_detail.html: status badge in `renderTicket`, `renderTransitionButtons` computes valid next states incl. backward/Rejected; guarded transitions open modals) — EXCEPT the 400-error-display sub-bullet below, left unchecked
  - [x] Buttons use `hx-post="/api/v1/tickets/{id}/transition"` → returns updated status badge + history partial (ticket_detail.html:193 and modal templates `hx-post` to the API; on success the ticket content incl. badge and history is re-rendered via `htmx.ajax` GET)
  - [x] Guard failures return 400 with error message (displayed via HTMX) — `ticket_detail.html` now registers a global `htmx:responseError` handler that parses FastAPI `detail` (string or validation array) and shows it in the `#transition-error` banner (page) or `#modal-error` container (inside guarded-transition modals, all three of which gained an error div). Also fixed a pre-existing bug found en route: non-modal direct buttons (e.g. Ready for Review → Complete, Rejected restore) posted form-encoded `hx-vals` to the JSON endpoint → 422 before guards ran; they now use `hx-ext="json-enc"` + JSON Content-Type header. E2E: `test_guard_failure_error_displayed` (Rejected → Groomed restore, banner shows "Approach is required") and previously-broken `test_complete_ticket` now pass
- [x] Web: Transition history section on ticket detail (timestamp, from→to, reason) (ticket_detail.html:209-235 `renderTransitions` renders from→to badges, reason, localized timestamp; section at lines 404-407)
- [x] Unit tests: all 30+ transition combinations (forward guarded, backward free, rejected restore) (tests/unit/test_transitions.py: `TestAllTransitionCombinations.test_all_combinations` parametrized 6×6 = 36 combinations; plus dedicated guard tests)

## Answer

Verified against branch `jackrabbit-integration`.

**Evidence per criterion:**

1. **Status enum** — Satisfied. `TicketStatus(StrEnum)` with exactly `Open/Groomed/In Progress/Ready for Review/Complete/Rejected` at `jackrabbit/models.py:20-26`.
2. **Transition rules (ADR-0009)** — Satisfied in `jackrabbit/services.py`:
   - Open → Groomed requires all four fields non-empty (`_validate_guard`, services.py:283-296; test `test_open_to_groomed_requires_all_fields`).
   - Groomed → In Progress: branch_name validated for format if provided, otherwise auto-generated via `generate_branch_name` (services.py:297-311, 410-412; test `test_groomed_to_in_progress_auto_generates_branch`).
   - In Progress → Ready for Review requires valid HTTP/HTTPS `pr_url` (services.py:312-322; test `test_in_progress_to_ready_for_review_requires_pr_url`).
   - Ready for Review → Complete: guard is a documented manual confirmation — `_validate_guard` returns None for this pair (services.py:323-326). This matches the ticket's "(manual confirmation)" wording, but note the code does not require a reason or check a spike-report flag; ADR-0009's "PR merged (or report accepted)" is enforced only by human judgment.
   - Backward transitions free (services.py:341-344, `_is_backward_transition`; test `test_backward_transitions_always_allowed`).
   - Rejected → prior state re-checks that state's guard (services.py:330-339; test `test_rejected_to_prior_state_requires_guards`).
   - Any → Rejected always allowed (services.py:329; test `test_any_to_rejected_always_allowed`).
3. **API endpoint** — Satisfied. `POST /api/v1/tickets/{ticket_id}/transition` in `jackrabbit/api.py:467-507` with `TransitionRequest {to_status, reason, optional grooming/branch/pr fields}`; `ValueError` → HTTP 400 (api.py:506-507). Also exposes `GET .../transition/can` (api.py:454-464). Tests: `test_transition_endpoint`, `test_transition_endpoint_invalid_guard`, `test_can_transition_endpoint`.
4. **`can_transition`** — Satisfied. Signature `(ticket, to_status) -> tuple[bool, str | None]` at `jackrabbit/services.py:324`.
5. **`transition`** — Satisfied. `jackrabbit/services.py:401-446`: guard check, status update, `Transition` audit row + ticket added, single `commit()` (atomic). Tests: `test_successful_transition_creates_audit`, `test_multiple_transitions_create_multiple_audit_records`, `test_transition_sets_completed_at`, `test_transition_raises_on_invalid`.
6. **Web status badge + action buttons** — Satisfied, including the previously-open guard-failure sub-bullet (fixed in this pass; see **Update** below). `ticket_detail.html` renders a status badge (`getStatusBadge`), computes valid next states in `getValidTransitions`, opens HTMX modals for guarded forward transitions, and posts direct transitions via `hx-post`. Success re-renders badge + history via `htmx.ajax` GET. Guard failures are now displayed: a global `htmx:responseError` handler parses FastAPI `detail` and shows it in the `#transition-error` banner (page) or `#modal-error` div (inside each guarded-transition modal).
7. **Transition history section** — Satisfied. `renderTransitions` (ticket_detail.html:209-235) renders from→to status badges, reason, and localized timestamp; mounted as the "Transition History" section at lines 404-407.
8. **Unit tests 30+ combinations** — Satisfied. `TestAllTransitionCombinations.test_all_combinations` in `tests/unit/test_transitions.py:392-558` is parametrized over all 6 statuses × 6 statuses = 36 combinations, plus 17 focused guard/audit/endpoint tests (53 tests total).

**Update (guard-failure HTMX display, this pass):**

The final open sub-bullet — "guard failures return 400 with error message (displayed via HTMX)" — is now implemented (TDD, red→green):

- `ticket_detail.html`: global `htmx:responseError` listener + `extractErrorMessage` (handles `detail` strings and 422 validation arrays); `#transition-error` alert banner added to the Status Actions section; cleared implicitly on successful reload (renderTicket rebuilds it hidden).
- All three transition modal templates gained a `#modal-error` container so in-modal guard failures surface next to the form.
- **Bug found and fixed en route:** non-modal direct buttons (Ready for Review → Complete, Rejected-restore, backward moves) sent form-encoded `hx-vals` to the JSON-only endpoint → FastAPI 422 before guards ever ran; E2E `test_complete_ticket` was failing as a result. Buttons now use `hx-ext="json-enc"` + `hx-headers Content-Type: application/json` (same pattern as the modals).
- New tests: `tests/integration/test_transition_web.py` (detail page wires `htmx:responseError` + `#transition-error`; modals have `#modal-error`; 400-with-detail contract for HTMX requests, guard + invalid-PR-URL cases) and E2E `test_guard_failure_error_displayed` (Rejected → Groomed restore, banner shows "Approach is required").

**Commands run (full run, this pass):**
- `uv run pytest -x tests/unit tests/integration -q` → 335 passed.
- `uv run pytest tests/e2e/test_ticket_lifecycle.py -q` (against live server) → 7 passed.
- `uv run ruff check` / `ruff format` on touched test files → clean.

**Gaps / residual risks:**
- Ready for Review → Complete performs no programmatic check (manual confirmation by design; no spike-report "accepted" field exists in the model).
- In `test_all_combinations`, Rejected → prior cases use `expected = None` (asserting observed behavior rather than a pre-computed expectation) — coverage exists but expectation is weaker for those cases.
- `mypy jackrabbit` reports 37 pre-existing errors in unrelated source files (api.py, etc.); none introduced by this pass (templates and tests only; `tests/` is excluded from mypy).