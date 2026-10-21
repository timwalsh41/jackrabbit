# JRB-001 — Labels on tickets (spec)

Source: Jackrabbit epic JRB-001 (ticket id 1, project JRB) in the tracker at
http://localhost:8080/api/v1/tickets/1. This file is the frozen copy of that spec for
the implement-spec run. Children must not edit it.

Implementation tickets (children of this epic): JRB-002, JRB-003, JRB-004, JRB-005.

## Agent operating notes (read this first)

The tracker convention docs are not tracked in git, so they are copied next to this spec:

- `.scratch/labels/issue-tracker.md` — how to read, update and resolve a ticket.
- `.scratch/labels/verification.md` — the gate commands.

Your ticket is named by its human-readable id, e.g. `JRB-003`. Read it with:

    curl -s http://localhost:8080/api/v1/tickets/by-id/JRB/3

(the trailing number is the ticket's `number` field, not its id). To resolve it, PATCH
its description: check off each `- [ ]` criterion as `- [x]`, append an `## Answer`
summary at the end, and set the first-line `**Status:**` line to `resolved`:

    curl -s -X PATCH http://localhost:8080/api/v1/tickets/<id> \
      -H 'Content-Type: application/json' \
      -d '{"description": "<full new description>"}'

Do NOT walk the ticket through the Groomed/In Progress/Ready for Review/Complete
status transitions — the `**Status:**` line is what the workflow reads.

The integration branch is `labels-integration`; your worktree already branches from it.
The gate is `uv run pytest -x` (full) and `uv run pytest -x tests/unit tests/integration`
(fast subset). Do not commit; leave changes uncommitted in your worktree.

---

**TRIAGE_STATUS**: ready-for-agent

## Problem Statement

A developer working in the Jackrabbit backlog can only categorise a ticket along the axes the system already models: project, type, status, priority and sprint. Those axes answer *which* project a ticket belongs to, *what kind* of work it is and *where* it sits. None of them can express a cross-cutting grouping — a subsystem, a customer, a theme for a release, a workaround, "needs design review". A developer who wants to see every ticket touching the auth service has nowhere to record that fact, and the backlog cannot be sliced by it.

The available workarounds are both poor. A **Link** is directional, typed and semantically about relationships between tickets, so reusing it for categorisation would corrupt its meaning and break its existing rules. A free-text convention in the description — the `**TRIAGE_STATUS**:` keyword the agent workflow uses to record triage state — is invisible to the filter bar and cannot be queried. The agent-facing triage instructions describe that keyword as a stopgap "until a labels feature is added to Jackrabbit".

Separately, a developer can find a ticket only by its title. A ticket whose description says it changes the billing reconciliation job, or which is tagged as concerning the auth service, is invisible to search.

## Solution

A user can define any label and apply it to any ticket, regardless of the ticket's type. A ticket can carry many labels at once. Labels are a single global vocabulary shared by every project, created on demand by typing them, and applied from the ticket page or from the ticket form. The backlog can be filtered by label — by one label, by several, matching all of them or any of them — and the free-text search covers a ticket's title, its description and its labels.

## User Stories

1. As a developer, I want to apply a label to a ticket, so that I can categorise work beyond type and status.
2. As a developer, I want to apply a label to an Epic, a Story, a Bug or a Spike alike, so that labels are available to every kind of work.
3. As a developer, I want a ticket to carry several labels at once, so that I can describe it along several dimensions.
4. As a developer, I want to remove a label from a ticket, so that a ticket's categorisation stays accurate as the work changes.
5. As a developer, I want to type a brand-new label name and have it created for me, so that I am not blocked by a vocabulary that must be curated in advance.
6. As a developer, I want the label picker to suggest labels already in use, so that I reuse the existing vocabulary instead of inventing near-duplicates.
7. As a developer, I want the labels I have used to be available to my other tickets, so that the vocabulary converges on a shared set rather than scattering.
8. As a developer, I want to see a ticket's labels on the ticket page, so that I know how the ticket is categorised without opening anything else.
9. As a developer, I want to see the labels of many tickets in the backlog table at once, so that I can read the categorisation of a whole list.
10. As a developer, I want to set labels when creating a ticket, so that a new ticket is categorised from the start rather than needing a detour afterwards.
11. As a developer, I want to edit a ticket's labels from the edit form, so that I can correct them in one place.
12. As a developer, I want a ticket to be allowed to have no labels at all, so that labelling stays optional.
13. As a developer, I want each label to be visually distinct from its neighbours, so that I can scan a list of tickets quickly.
14. As a developer, I want the same label to look the same everywhere it appears, so that a colour consistently signals a meaning.
15. As a developer, I want `Backend` and `backend` to be recognised as the same label, so that the vocabulary does not fragment by capitalisation.
16. As a developer, I want a label to keep the spelling I first typed, so that it reads the way I wrote it.
17. As a developer, I want to be told when a label name is not allowed, so that I do not create a label that cannot be found later.
18. As a developer, I want label names to allow spaces and a colon-prefixed namespace, so that I can group related labels under a family.
19. As a maintainer, I want to filter the backlog by a label, so that I can see the slice of work carrying it.
20. As a maintainer, I want to select several labels at once, so that I can narrow to the tickets carrying all of them.
21. As a maintainer, I want to switch between "must carry all selected labels" and "must carry any selected label", so that I can narrow or broaden without changing my selection.
22. As a maintainer, I want the label filter to list every label currently in use, so that I can discover the vocabulary by browsing rather than by remembering.
23. As a maintainer, I want my label filter to survive sorting the table and paging through results, so that my filter is not silently dropped by an unrelated click.
24. As a maintainer, I want the label filter to combine with the other filters, so that I can slice by project, type, status and label together.
25. As a maintainer, I want to clear all filters with a single action, so that I can start over from a confusing result.
26. As a project lead, I want the same label to mean the same thing in every project, so that the vocabulary is shared rather than per-project.
27. As a developer, I want the search box to find a ticket by its title, so that I can look up work I half remember.
28. As a developer, I want the search box to find a ticket by its description, so that I can find work by what it says.
29. As a developer, I want the search box to find a ticket by its label name, so that I can find work by how it is categorised.
30. As a developer, I want one search box to cover title, description and labels, so that I do not have to guess which control to reach for.
31. As a maintainer, I want free-text search to keep working on top of the active filters, so that I can combine a phrase with a narrowed view.
32. As a maintainer, I want a label that no ticket carries to stay in the vocabulary, so that nothing I typed is silently thrown away.
33. As a maintainer, I want labels that no ticket carries kept out of the filter list, so that the list only offers meaningful choices.
34. As a maintainer, I want the five canonical triage roles to be real labels, so that triage state is visible in the interface and queryable rather than hidden in a description.
35. As a maintainer, I want the triage roles namespaced, so that they do not collide with labels I invent for my own use.
36. As an agent, I want to read and write a ticket's triage state as a label, so that automation does not have to parse a description keyword.
37. As an integrator, I want to read the label vocabulary together with its usage, so that I can populate a picker and know which labels matter.
38. As an integrator, I want to attach a label to a ticket by name, so that a new label is created on demand.
39. As an integrator, I want to detach a label from a ticket, so that I can correct a categorisation programmatically.
40. As an integrator, I want to set a ticket's whole set of labels when creating or updating it, so that I can write a ticket in a single call.
41. As an integrator, I want a ticket's labels included in the ticket payload, so that reading a ticket does not need a second call.
42. As an integrator, I want to filter a ticket listing by label, so that I can script the same slice the backlog view shows.
43. As a developer, I want deleting a ticket to leave nothing behind, so that the label vocabulary is not polluted by attachments to a ticket that no longer exists.

## Implementation Decisions

### Domain model
- A **Label** is a first-class, globally scoped entity with a display name and a case-insensitive identity key. A Label belongs to no project and to no ticket type.
- A Ticket carries zero or more Labels through a join table. Any Label may be applied to any Ticket, and a Ticket may carry any number of Labels.
- Label identity is case-insensitive: the identity key is the lower-cased name, unique across the registry. The display name is the first spelling typed, and is preserved.
- Label names are trimmed, at most 50 characters, and restricted to letters, digits, spaces, hyphens, underscores and colons. Colons are permitted so that namespaced families such as `triage:ready-for-agent` are expressible.
- A Label's colour is derived deterministically from its identity key onto a fixed palette. There is no stored colour and no user-editable colour.
- Labels are created on demand: applying a name that does not yet exist creates it; applying an existing name attaches the existing Label.
- A Label with no tickets attached persists in the registry. It is not offered in the backlog filter list or in the picker's suggestions.
- Deleting a Ticket removes its Label attachments.

### Service surface
- A label service owns: finding or creating a Label by name, attaching, detaching, replacing a Ticket's full set of Labels, reading the registry with usage counts, and listing the Labels in use.
- The ticket listing service gains a label filter: a set of label ids plus a match mode of **all** or **any**, defaulting to **all**. The match mode is a caller-supplied setting, not fixed behaviour.
- The ticket listing service's free-text search widens from title-only to title, description and label names: a ticket matches when the search text occurs in any of the three, case-insensitively. The match remains a single substring and is not tokenised.
- Ticket listing continues to paginate and sort exactly as before; the label filter composes with every existing filter.

### JSON API
- The label registry can be read, including usage counts.
- A label can be attached to a ticket by name, and detached from a ticket by label id.
- Ticket create and ticket update accept a set of label names. Update **replaces** the ticket's entire label set, so removal is expressible through update.
- The ticket payload returned to clients includes the ticket's Labels, each with its id, name and colour.
- Ticket listing accepts label ids and the match mode as query parameters.
- Attaching a label through the web interface returns the re-rendered labels section, following the established pattern for links.

### Web and HTMX
- The ticket page gains a labels section, loaded the same way as the links section: a server-rendered partial swapped in by HTMX, with its own add-label modal mounted inside the section.
- The ticket create and edit form gains a chip input: typed text is committed as a chip on Enter, existing labels are suggested as the user types, and a name that does not yet exist is created.
- The backlog gains a labels column, and the table's empty-state row spans the new column count.
- The backlog filter bar gains a collapsible labels panel holding a checkbox per label in use, and a control choosing whether the selected labels must all match or any may match.
- The backlog's sortable headers and pagination links carry the active filters by **including the filter form**, rather than by restating each filter in every request. Sort, order and page continue to override the form's own values. This makes the filter form the single source of truth, so no filter can be silently dropped when the table is sorted or paged.
- The free-text search field is relabelled from "Search Title" to "Search", to match its widened behaviour.
- The project-scoped ticket view shares the backlog's filter form and gains the label filter and labels column for free.

### Documentation and domain
- A new ADR records the label model and supersedes the earlier decision that deliberately excluded labels. That earlier ADR is annotated as superseded in that respect.
- The glossary gains a Label term, and the Ticket and Backlog View entries are updated to mention labels.
- The triage role mapping moves from a description keyword to real labels in a `triage:` namespace, and the agent-facing triage instructions are updated to match. The keyword remains authoritative until this feature is deployed.

## Testing Decisions

- A good test asserts only external behaviour: a label's effect is observed through an API response, the rendered HTML, or the browser — never through internal attributes, SQL, or the shape of internal objects.
- The feature is tested at three seams, mirroring the existing test layout:
  - **Service level (unit)**, over an in-memory database: name normalisation and case-insensitive identity, the allowed character set and length limit, create-on-demand, colour derivation, attach / detach / replace semantics, both match modes selecting the right tickets, and search covering description and label names.
  - **HTTP level (integration)**: the label endpoints' request and response contracts, the ticket payload including its labels, the label filter on a ticket listing, and the backlog page's rendered filter panel and labels column. These follow the existing pattern of asserting on response status and response text.
  - **Browser level (end-to-end)**: applying a label from the ticket page, filtering the backlog by one label and by several labels in both match modes, and finding a ticket by searching for its label name.
- Prior art: the link feature's unit, integration and end-to-end tests are the closest existing analogue and should be followed in structure and naming.
- Regression coverage is required for the refactor that makes the filter form the single source of truth: the pre-existing filters must be shown to survive sorting and paging, not only the new label filter.
- The end-to-end tier must not depend on leftover database state; titles and label names asserted through search are run-unique.

## Out of Scope
- A labels administration screen: no renaming, merging or deleting of labels, and no editing of label colours.
- Bulk application of a label to several tickets at once.
- Labels on anything other than a ticket — not on projects, sprints or links.
- Per-project or per-ticket-type label vocabularies, and any restriction on which labels may be applied to which kind of ticket.
- Saved or named filters, and any label-based report or dashboard.
- Renaming a label by changing its spelling: the display name is fixed at first creation, and only new labels can be introduced with a different spelling.
- Notifications or automation triggered by label changes.
- Any record of label changes in a ticket's history; a label change moves the ticket's last-modified time only.

## Further Notes

- This supersedes the earlier decision that excluded labels from the ticket model on the grounds that priority, type, project and sprint already covered filtering. That reasoning does not hold: those axes are fixed and orthogonal, and cannot express the cross-cutting groupings labels exist for.
- The triage migration is a behaviour change for the agent workflow. Until the label feature is deployed, the description keyword remains the authoritative triage marker; the change of authority happens at deployment.
- The label vocabulary is user-driven and will therefore contain typos. The absence of a rename or merge capability is a deliberate consequence of the current scope, and a labels administration screen is the natural next increment.
- A label on a ticket does not imply anything about the ticket's type, priority or status. Labels are orthogonal to the fixed axes, and a ticket may carry several that appear to overlap.

