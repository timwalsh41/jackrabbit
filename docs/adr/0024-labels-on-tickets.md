# ADR-0024: Labels on Tickets

## Status
Accepted (supersedes the `labels`/`tags` exclusion in ADR-0016)

## Context
ADR-0016 chose a minimal ticket model and explicitly excluded labels and tags, on the
premise that "priority + type + project + sprint cover filtering". That premise does not
hold. Project, type, status, priority and sprint are fixed, orthogonal axes of the
backlog: they answer *which* project, *what kind* of work, *where* it is. They cannot
express a cross-cutting grouping such as a subsystem, a customer, a theme for a release,
or a workaround. A user who wants "all the tickets touching the auth service" has
nowhere to put that fact, and the backlog cannot be sliced by it.

Two workarounds exist today and both are poor:

- **Links** are directional, typed and semantically about relationships between tickets
  (parent/child, blocks, relates_to). Reusing them for categorisation would corrupt
  their meaning and break their existing rules.
- **Description keywords** — the agent workflow records triage state as a
  `**TRIAGE_STATUS**: <role>` line at the top of a ticket description
  (`docs/agents/triage-labels.md`). That document calls it a stopgap "until a labels
  feature is added to Jackrabbit". The keyword is invisible to the filter bar and
  unqueryable.

The user asked for Jira-like labels: any label, definable by the user, appliable to any
ticket regardless of type, many per ticket, and searchable from the backlog view.

## Decision

### Model
A **Label** is a first-class, globally scoped entity. Labels are not owned by a project
and not by a ticket type.

```sql
CREATE TABLE label (
    id         INTEGER PRIMARY KEY,
    name       TEXT    NOT NULL,   -- display name, as first typed
    name_key   TEXT    NOT NULL UNIQUE,  -- lower(name): case-insensitive identity
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE ticket_label (
    id         INTEGER PRIMARY KEY,
    ticket_id  INTEGER NOT NULL REFERENCES ticket(id),
    label_id   INTEGER NOT NULL REFERENCES label(id),
    created_at TIMESTAMP NOT NULL,
    UNIQUE(ticket_id, label_id)
);
```

### Identity and naming
- **Case-insensitive identity.** `name_key` is the lower-cased name and is unique across
  the registry, so `Backend` and `backend` are the same label. The display name is the
  spelling first typed and is preserved.
- **Name rules.** Trimmed, at most 50 characters, restricted to letters, digits, spaces,
  hyphens, underscores and colons. Colons are permitted so that namespaced families such
  as `triage:ready-for-agent` are expressible.
- **Created on demand.** Applying a name that does not yet exist creates it. Applying an
  existing name attaches the existing label.
- **Unused labels persist.** A label with no tickets attached stays in the registry, but
  is not offered in the backlog filter list or the label picker's suggestions. Nothing a
  user typed is silently discarded.

### Colour
A label's colour is **derived** from `name_key` onto a fixed palette. There is no stored
colour and no user-editable colour. The same label therefore always looks the same, with
no administration required.

### Filtering
The ticket listing service gains a label filter: a set of label ids plus a match mode
(**all** / **any**), defaulting to **all**. The match mode is a caller-supplied setting,
exposed in the backlog as a control next to the label checkboxes.

The backlog's sortable headers and pagination links carry the active filters by
**including the filter form**, rather than by restating each filter in every request.
The sort, order and page values continue to override the form's own values. This makes
the filter form the single source of truth, so a filter cannot be silently dropped when
the table is sorted or paged.

### Search
The ticket listing service's free-text search widens from title-only to **title,
description and label names**: a ticket matches when the search text occurs in any of
the three, case-insensitively. The match remains a single substring and is not
tokenised. The backlog's search field is relabelled from "Search Title" to "Search".

### API
- The label registry can be read, including usage counts.
- A label can be attached to a ticket by name (creating it on demand) and detached by
  label id.
- Ticket create and ticket update accept a set of label names; update **replaces** the
  ticket's entire label set, so removal is expressible through update.
- The ticket payload returned to clients includes the ticket's labels.
- Ticket listing accepts label ids and the match mode as query parameters.
- Attaching a label through the web UI returns the re-rendered labels section, following
  the established pattern for links.

### Triage
The five canonical triage roles move from the `**TRIAGE_STATUS**:` description keyword
to real labels in a `triage:` namespace. Until this feature is deployed, the keyword
remains authoritative; the change of authority happens at deployment.

## Consequences

### Positive
- **Cross-cutting grouping becomes expressible** — the backlog can finally be sliced by
  something other than the fixed axes.
- **One vocabulary across projects** — `backend` means the same thing everywhere, and
  the global registry is the list of that vocabulary.
- **Queryable triage** — triage state becomes a first-class, filterable fact instead of a
  description convention.
- **Search widens for free** — a ticket is findable by what its description says and by
  how it is categorised, not only by its title.
- **The filter-duplication bug class is closed** — making the filter form the single
  source of truth removes the trap for every future filter, not just this one.

### Negative
- **Two new tables and a migration** — more schema than ADR-0016's minimalism wanted.
- **The vocabulary will contain typos** — labels are user-created and there is no rename
  or merge, so `backnd` will sit in the registry forever.
- **A wider ticket table** — the backlog gains a labels column.
- **The search box's meaning changes** — `q` no longer searches titles only, which is a
  behaviour change for anyone who relied on the old narrow meaning.

### Mitigations
- Unused labels are hidden from the filter list and picker suggestions, so typos are
  invisible until they are used.
- A labels administration screen (rename, merge, delete, recolour) is the natural next
  increment and is explicitly out of scope for this spec.
- The widened search is documented by relabelling the field, so the change is visible
  rather than silent.

## Alternatives Considered
- **Delimited string column on the ticket**: rejected — no registry, so "which labels
  exist" is unanswerable, and filtering degenerates into `LIKE` matching over packed
  text.
- **Join table without a label entity**: rejected — labels still have identity, usage
  counts and a lifecycle; a bare text column cannot carry them.
- **Case-sensitive labels**: rejected — `Bug` and `bug` would be different labels,
  fragmenting the vocabulary invisibly.
- **Stored, user-editable label colours**: rejected for now — editable colours need an
  administration surface to be reachable, and a derived colour already satisfies the
  need to scan a dense table.
- **Pruning labels that no ticket carries**: rejected — a label created for later use
  would vanish, and pruning is silent data loss.
- **Replacing `type` or `priority` with labels**: rejected — they are not
  interchangeable; labels are orthogonal to both, and the user did not ask for it.
- **Keeping labels out entirely (status quo)**: rejected — the premise of ADR-0016's
  exclusion does not hold, and the triage workflow is already held back by the missing
  feature.
