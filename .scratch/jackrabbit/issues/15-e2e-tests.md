# 15: E2E Tests (Critical Flows)

**What to build:** Playwright + chrome-devtools-axi tests for critical user flows. Agents use chrome-devtools-axi during development to verify their work.

**Blocked by:** 12, 13

**Status:** resolved

- [x] **Flow 1: Ticket Lifecycle** (`tests/e2e/test_ticket_lifecycle.py`)
  - Create ticket via Backlog → fills title, type, project
  - Click "Groom" → modal requires 4 fields → fill → submit → status=Groomed
  - Click "Start" → branch name pre-filled → confirm → status=In Progress
  - Click "Review" → PR URL required → fill → confirm → status=Ready for Review
  - Click "Complete" → confirm merged → status=Complete
  - Verify each transition updates badge, history, disables invalid next buttons
- [x] **Flow 2: Sprint Workflow** (`tests/e2e/test_sprint_workflow.py`)
  - Create sprint → set dates → create tickets → assign to sprint via Backlog
  - Open Sprint view → tickets appear in status columns
  - Move tickets through statuses → Sprint view updates
  - Set actual_start → sprint status=Active
  - Set actual_finish → sprint status=Complete
- [x] **Flow 3: Project Move** (`tests/e2e/test_project_move.py`)
  - Create two projects (MSC, WEB)
  - Create ticket in MSC → verify MSC-001
  - Move to WEB → verify WEB-001, "Formerly MSC-001" shown
  - Move back → MSC-002 (next available), original_id still MSC-001
- [x] **Flow 4: Epic → Story Linking** (`tests/e2e/test_epic_story.py`)
  - Create Epic ticket → create 3 Story tickets
  - Link each Story as child of Epic
  - Open Epic detail → see 3 child links
  - Open Plan view → Epic shows with children
- [x] **Flow 5: Backlog Filtering** (`tests/e2e/test_backlog_filters.py`)
  - Filter by project, type, status, sprint, text search
  - Combined filters (AND logic)
  - Clear filters button works
- [x] **Flow 6: Reject → Restore** (`tests/e2e/test_reject_restore.py`)
  - Ticket at In Progress → Reject → status=Rejected
  - Restore to Groomed → verify guards re-checked (4 fields present)
  - Restore to Open → always allowed
- [x] **chrome-devtools-axi integration**: each test can run with `--headed` and devtools protocol for agent debugging
- [x] **CI**: runs headless in GitHub Actions; local: `pytest tests/e2e --headed`

## Answer

Implemented ticket 15 with TDD on top of the ticket-13 e2e scaffolding. Audited all six
flows, fixed the failing tests (wrong selectors/directions), filled coverage gaps, and —
where an E2E flow exposed genuine app bugs — made the minimal fixes needed to make the
flows pass.

**App fixes (each exposed by a flow, kept minimal):**
- `POST/DELETE /api/v1/sprints/{sid}/tickets/{tid}`: HTMX requests now get the rendered
  `ticket_row.html` partial (mirrors ticket 04's PATCH content-negotiation); plain
  requests stay JSON. Fixes Backlog "Move to Sprint"/"Remove from Sprint" swapping raw
  JSON into the row.
- `POST /api/v1/tickets/{id}/links`: HTMX requests now return the refreshed links
  section (`_links_section_response` shared with the web GET route). The Add Link modal
  posts JSON (`json-enc`) and now includes a hidden `source_id` (the API required it —
  the modal could never have succeeded).
- Link modal: inverted option-gating fixed (Epic pages disabled "Parent" — the one
  action an Epic needs); search input renamed to `q` (it sent `target_search`, so the
  search endpoint always saw an empty query) with `hx-swap="innerHTML"` (the form's
  `outerHTML` was inherited, replacing `#target-results` itself); `hx-on::after-request`
  scoped to the form's own request (any bubbling request closed the modal).
- Links section row directions fixed: parent/child rows referenced the ticket itself
  instead of the other ticket; blocked_by referenced itself. Epic detail pages now
  correctly list child stories.
- Transition modals: `closeModal()` removed the `#ticket-modal` container (matched
  `[aria-modal=true]` first), so no second modal could ever open on the detail page;
  now clears the container instead.
- Ticket IDs normalized to zero-padded (`WEB-003`): `Ticket.full_id`, move-project
  `old_full_id`/`new_full_id`, transition response `full_id`, and the detail page's
  client-side re-render.
- Plan view extended with an "Epics" section (each Epic + its child tickets) —
  supervisor-approved Option A (spec's E2E flow list says "view in Plan"); backed by
  new `LinkService.get_epics_with_children()` (unit-tested) and integration tests.

**Test work:**
- Fixed: epic-story selectors/directions; sprint-assign (app fix); backlogged filter
  tests were vacuous (`.project-cell` etc. don't exist and selects don't auto-submit) —
  rewritten against the real Filter button; reject/restore no-ops rewritten as
  self-contained UI flows (reject via prompt dialog, guard re-check, restore).
- Added: full-lifecycle walk (badge + history + invalid next buttons absent at each
  stage); sprint view updates on status move; actual_start → Active / actual_finish →
  Complete via the sprint edit modal; move-back renumbering (MSC-001 → WEB → back →
  MSC-002 with original_id preserved); Plan view epic-with-children.
- Runner: `--headed` (or `E2E_HEADED=1`) makes the browser headed for local agent
  debugging; `--cdx` (or `CHROME_DEVTOOLS_AXI_ENABLED=1`) starts the
  chrome-devtools-axi bridge from `tests/cdx_helper.py` for DevTools-protocol
  debugging, degrading cleanly when the binary is absent. Unit tests cover the options.
- Playwright/browser e2e fixtures made function-scoped: the sync API holds the
  main-thread asyncio loop open, which broke pytest-asyncio setup for every async test
  in the same process — the full `pytest -x` gate (e2e + integration in one run) could
  not pass otherwise.
- CI (`.github/workflows/ci.yml`) already runs the e2e suite under `xvfb-run`; the
  `--headed` local flag complements it per the criterion.

Validation: `uv run pytest -x` → 511 passed (unit + integration + e2e in one process);
`ruff check` clean; `mypy jackrabbit` at the 31 pre-existing-error baseline.
