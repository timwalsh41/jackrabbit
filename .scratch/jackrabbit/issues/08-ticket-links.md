# 08: Ticket Links (parent/child, blocks/blocked_by, relates_to)

**What to build:** Typed links between tickets. Three type pairs: parent/child (Epic→Story), blocks/blocked_by (dependencies), relates_to (bidirectional association).

**Blocked by:** 04

**Status:** resolved

- [x] Link types: `parent`, `child`, `blocks`, `blocked_by`, `relates_to` (ADR-0015)
- [x] API: `GET /api/v1/tickets/{id}/links` — list all links for ticket (both directions)
- [x] API: `POST /api/v1/tickets/{id}/links` — add link `{target_ticket_id, link_type}`
  - Validation: `parent` only to Epic-type ticket; `child` only from Epic-type ticket
  - `blocks`/`blocked_by` create inverse automatically (two rows or symmetric check)
  - `relates_to` creates symmetric pair (or single undirected row)
  - Prevent self-links, duplicate links
- [x] API: `DELETE /api/v1/tickets/{id}/links/{link_id}` — remove link (removes inverse if paired)
- [x] Service: `get_blockers(ticket_id)` → tickets with `blocks`→this; `get_blocked(ticket_id)` → this→`blocks`
- [x] Web: Ticket detail shows "Links" section with type-labeled rows
  - "Add Link" button → modal: select type, search target ticket (by ID/title)
  - Each link row: type badge, target ticket link, "Remove" button (`hx-delete`)
  - `blocks` links show ⚠ warning if blocker not Complete
- [x] Web: Backlog view — "Blocked" indicator on tickets with open blockers
- [x] Unit tests: all type pairs, inverse creation, validation rules, blocker queries

## Answer

Verification performed on branch `jackrabbit-integration` (HEAD 97f36c3). All 9 acceptance criteria are satisfied.

**Evidence per criterion:**

1. **Link types** — `LinkType` StrEnum defines all five values (`parent`, `child`, `blocks`, `blocked_by`, `relates_to`) at `jackrabbit/models.py:29`; `TicketLink` table (`jackrabbit/models.py:117`) with source/target FKs and bidirectional `Relationship`s on `Ticket`.
2. **GET links (both directions)** — `jackrabbit/api.py:577` (`get_ticket_links`); service `LinkService.get_links_for_ticket` (`jackrabbit/services.py`) queries `source_id == ticket OR target_id == ticket`. Covered by `TestGetLinksForTicket::test_get_links_returns_both_directions` in `tests/unit/test_links.py` (asserts 4 links incl. incoming and outgoing for a middle ticket).
3. **POST links + validation** — `jackrabbit/api.py:527` (`create_link`, returns 201, maps `ValueError` → 400). Minor naming deviation: request body is `TicketLinkCreate {source_id, target_id, link_type}` (`jackrabbit/schemas.py:249`) rather than `{target_ticket_id, link_type}` — functionally equivalent (target ticket id + link type). Validation in `LinkService._validate_link` (`jackrabbit/services.py:954`): self-links rejected ("Cannot link a ticket to itself"), duplicates return existing row (`create_link` dedup check at ~:985), `parent` requires Epic source, `child` requires Epic target (matches the Epic→Story semantics; Epic↔Epic allowed). `blocks`/`blocked_by` create automatic inverse rows; `relates_to` creates the symmetric row (`_get_inverse_link_type` + `create_link` at `jackrabbit/services.py:943–1040`).
4. **DELETE link with inverse removal** — `jackrabbit/api.py:554` (`delete_link`, 404 checks for missing link / link not belonging to ticket); `LinkService.delete_link` deletes the paired inverse for all three type pairs.
5. **Blocker queries** — `LinkService.get_blockers` / `get_blocked` (`jackrabbit/services.py`, end of `LinkService`); only `BLOCKS`-type rows, filtered by target/source respectively. Also exposed via `GET /tickets/{id}/blockers` and `/blocked` (`jackrabbit/api.py:584–594`).
6. **Web links section** — `ticket_links_section.html` (Add Link button → `hx-get="/tickets/{id}/links/modal"`), `ticket_link_modal.html` (type select with Epic-gating, target search by ID/title via `hx-get="/tickets/search"` → `jackrabbit/web.py:619`), `ticket_link_row.html` (type badge, target ticket link, status badge, `hx-delete` Remove form hitting `DELETE /api/v1/tickets/{id}/links/{link_id}`, and ⚠ "Not Complete" warning for `blocks` links whose other ticket is not Complete). Routes at `jackrabbit/web.py:251–330`; detail page hosts `#links-section-container` (`ticket_detail.html:411`).
7. **Backlog Blocked indicator** — `ticket_row.html:74–82` computes open blockers from `ticket.incoming_links` (blocks-type with non-Complete source) and renders a red "Blocked" badge; included from `backlog.html:147` under a "Blocked" column header.
8. **Unit tests** — `tests/unit/test_links.py`: 36 tests across creation/inverse, deletion/inverse, both-direction listing, blocker queries, parametrized type-constraint matrix, and complex scenarios (chains, multiple blockers). All pass.

**Tests run:** `uv run pytest tests/unit/test_links.py -q` → 36 passed; `uv run pytest tests/unit tests/integration -q -k "link or Links"` → 37 passed. Full `tests/unit tests/integration` suite: 247 passed with 2 failures + 7 setup errors, all confined to move-project and plan-API areas (tickets 06/07 scope, unrelated to links).

**Gaps:** (a) POST body field named `target_id`/`source_id` instead of the spec's `target_ticket_id` — cosmetic naming deviation, behavior matches spec; (b) e2e link tests exist (`tests/e2e/test_epic_story.py`) but were not run — they require a live server on `localhost:8080` (Playwright); template and service behavior was verified by code inspection + unit tests instead.