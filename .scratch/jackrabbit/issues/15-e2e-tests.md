# 15: E2E Tests (Critical Flows)

**What to build:** Playwright + chrome-devtools-axi tests for critical user flows. Agents use chrome-devtools-axi during development to verify their work.

**Blocked by:** 12, 13

**Status:** ready-for-agent

- [ ] **Flow 1: Ticket Lifecycle** (`tests/e2e/test_ticket_lifecycle.py`)
  - Create ticket via Backlog → fills title, type, project
  - Click "Groom" → modal requires 4 fields → fill → submit → status=Groomed
  - Click "Start" → branch name pre-filled → confirm → status=In Progress
  - Click "Review" → PR URL required → fill → confirm → status=Ready for Review
  - Click "Complete" → confirm merged → status=Complete
  - Verify each transition updates badge, history, disables invalid next buttons
- [ ] **Flow 2: Sprint Workflow** (`tests/e2e/test_sprint_workflow.py`)
  - Create sprint → set dates → create tickets → assign to sprint via Backlog
  - Open Sprint view → tickets appear in status columns
  - Move tickets through statuses → Sprint view updates
  - Set actual_start → sprint status=Active
  - Set actual_finish → sprint status=Complete
- [ ] **Flow 3: Project Move** (`tests/e2e/test_project_move.py`)
  - Create two projects (MSC, WEB)
  - Create ticket in MSC → verify MSC-001
  - Move to WEB → verify WEB-001, "Formerly MSC-001" shown
  - Move back → MSC-002 (next available), original_id still MSC-001
- [ ] **Flow 4: Epic → Story Linking** (`tests/e2e/test_epic_story.py`)
  - Create Epic ticket → create 3 Story tickets
  - Link each Story as child of Epic
  - Open Epic detail → see 3 child links
  - Open Plan view → Epic shows with children
- [ ] **Flow 5: Backlog Filtering** (`tests/e2e/test_backlog_filters.py`)
  - Filter by project, type, status, sprint, text search
  - Combined filters (AND logic)
  - Clear filters button works
- [ ] **Flow 6: Reject → Restore** (`tests/e2e/test_reject_restore.py`)
  - Ticket at In Progress → Reject → status=Rejected
  - Restore to Groomed → verify guards re-checked (4 fields present)
  - Restore to Open → always allowed
- [ ] **chrome-devtools-axi integration**: each test can run with `--headed` and devtools protocol for agent debugging
- [ ] CI: runs headless in GitHub Actions; local: `pytest tests/e2e --headed`