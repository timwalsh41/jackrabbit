# ADR-0027: Triage as a Label-Name Convention

## Status
Accepted (supersedes the Triage section of ADR-0024)

## Context
ADR-0024 introduced labels as a first-class entity and, in the same breath, promoted
triage into a product-level construct: the five canonical triage roles were frozen
into `jackrabbit/triage.py` as an enum, exposed through dedicated endpoints
(`GET /api/v1/triage/roles`, `GET/POST /api/v1/tickets/{id}/triage`) backed by a
`TriageService`, and rendered in the templates as a distinct triage badge.

That turns out to be the wrong layer. The triage vocabulary belongs to the skills
ecosystem (the agent workflows), not to Jackrabbit. Freezing an external vocabulary
into product code had two concrete failures:

- **422s for legitimately-canonical roles.** `POST /tickets/{id}/triage` rejected any
  role outside the frozen enum, even though the generic labels API happily accepts
  `triage:any-name-someone-coined-tomorrow`. When the skills side evolved its
  vocabulary, the tracker became the thing saying "no".
- **A weak at-most-one invariant.** `TriageService.set_role` detached other triage
  labels to keep at most one role per ticket — but the plain labels API (attach by
  name, ticket create/update with `labels`) bypasses the service entirely, so the
  invariant only held for callers that agreed to use the special endpoint. The
  tracker was enforcing a rule it could not actually guarantee.

The roles are already stored as labels in the `triage:` namespace; no data migration
is needed to stop treating them specially. The only consumers of the dedicated
endpoints and service are agent tooling and the agent-facing docs, both updated in
the same change — so there is no deprecation window to run.

## Decision
Triage is a **label-name convention over the labels feature**, owned by the skills
ecosystem and documented in `docs/agents/triage-labels.md` — which is now the single
source of truth for the five canonical names: `triage:needs-triage`,
`triage:needs-info`, `triage:ready-for-agent`, `triage:ready-for-human` and
`triage:wontfix`.

Removed outright (no deprecation window):

- `jackrabbit/triage.py` (the enum and vocabulary helpers).
- `TriageService` and the `get_triage_service` dependency.
- The three triage endpoints and their schemas
  (`TriageRoleRead`/`TriageRoleSet`/`TriageRead`).
- `Ticket.triage_role` and the triage badge markup in the templates: a `triage:*`
  label renders as an ordinary label chip, like any other label.

A role is recorded and read through the generic labels API — attach by name
(`POST /tickets/{id}/labels`), detach by label id, ticket payload `labels` field.

The **at-most-one-triage-label invariant is an mp-skills convention, not
Jackrabbit's**. It is neither documented in Jackrabbit nor enforced by it: the plain
labels API lets a ticket carry several `triage:*` labels, and tooling that expects a
single role must manage replacement itself. ADR-0024's label entity (registry,
case-insensitive `name_key`, derived colour, filtering, search) stays as-is; nothing
in this ADR touches it.

## Consequences

### Positive
- **The tracker no longer freezes an external vocabulary.** Any `triage:*` name
  attaches like any other label; the skills ecosystem can evolve its roles without
  a Jackrabbit release, and nothing 422s a role the product never heard of.
- **No phantom invariant.** Removing `TriageService` removes the pretend guarantee;
  the convention's ownership (mp-skills) is now explicit, and so is the fact that
  Jackrabbit does not enforce it.
- **Less product surface** — one module, one service, three endpoints and three
  schemas deleted; the OpenAPI document shrinks with them.

### Negative
- **A breaking API change** — clients that called `/triage` endpoints or read
  `Ticket.triage_role` must switch to the labels API.
- **The interface loses the triage badge** — `triage:*` labels are ordinary chips,
  so a ticket's triage state no longer visually stands out.
- **The convention depends on documentation** — nothing in the product prevents a
  typo'd `triage:ready-for-agnt` or two roles on one ticket.

### Mitigations
- The only known consumers are agent tooling and the agent-facing docs, updated in
  the same change; the label name rules (colons allowed, created on demand,
  case-insensitive identity) are unchanged, so existing `triage:*` labels survive
  as-is.
- `docs/agents/triage-labels.md` carries the canonical list and the
  replacement-the-role-yourself guidance.

## Alternatives Considered
- **Keep the enum, widen the endpoints to accept arbitrary names**: rejected — it
  keeps a service whose only job is to enforce a convention the labels API makes
  unenforceable, and keeps two ways to do the same attach.
- **Enforce at-most-one inside `LabelService`** (e.g. a rule namespace): rejected —
  it hard-codes the skills' workflow into the generic label machinery and couples
  the tracker to a vocabulary it does not own.
- **Deprecation window before removal**: rejected — the only consumers are agent
  tooling and docs, updated in the same pass, so a window only prolongs the
  ambiguity about which API is authoritative.
