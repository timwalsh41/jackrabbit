# 03: Project CRUD (API + Web)

**What to build:** Full CRUD for Projects via `/api/v1/projects` REST API and SSR web pages. UNS project protected from deletion. Project list page, create form, edit form.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] API: `GET /api/v1/projects` (list), `POST /api/v1/projects` (create), `GET /api/v1/projects/{id}` (get), `PATCH /api/v1/projects/{id}` (update), `DELETE /api/v1/projects/{id}` (delete)
- [ ] Validation: prefix unique, 2-10 chars uppercase; name required; color hex format
- [ ] `DELETE /api/v1/projects/{id}` returns 403 if `is_system=true` (protects UNS)
- [ ] Web: `GET /projects` — table of projects with prefix, name, color badge, ticket count, actions
- [ ] Web: `GET /projects/new` — create form (HTMX `hx-post` → returns row partial)
- [ ] Web: `GET /projects/{id}/edit` — edit form (HTMX `hx-patch` → returns row partial)
- [ ] Web: Delete button with `hx-delete` + `hx-confirm` (disabled for UNS)
- [ ] Base template `base.html` with HTMX loaded, navigation bar (Backlog, Sprints, Plan, Projects)
- [ ] All templates use glossary vocabulary: "Project", "Ticket", "Sprint"