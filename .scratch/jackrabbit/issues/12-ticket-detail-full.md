# 12: Ticket Detail Page (Full)

**What to build:** Complete ticket detail view with all fields, links, transition history, and action buttons (status transitions, link management, sprint assignment, project move, edit).

**Blocked by:** 04, 05, 08, 10

**Status:** resolved

- [ ] Web: `GET /tickets/{id}` — single page with sections:
  - **Header**: Ticket ID (`MSC-005`), Title, Type badge, Status badge (with transition buttons), Priority, Story Points
  - **Metadata**: Project link, Sprint link (or "Unassigned" + "Assign to Sprint" dropdown), Branch name (copy), PR URL (link), "Formerly MSC-003" if moved
  - **Description**: Markdown-rendered (HTMX safe)
  - **Groomed Fields** (collapsible): Approach, Files to Change, Test Plan, Validation Steps — editable inline if not Complete/Rejected
  - **Links**: Table of links (type, target ticket link, remove button) + "Add Link" button
  - **Transition History**: Chronological list (timestamp, from→to, reason)
  - **Actions**: Edit (→ `/tickets/{id}/edit`), Move Project, Delete (confirm)
- [ ] All mutations via HTMX partials: status buttons, link add/remove, sprint assign, project move, field edits
- [ ] URL-based: deep-linkable, browser back/forward works
- [ ] 404 page for non-existent tickets