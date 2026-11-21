# Triage Labels

The five canonical triage roles are a convention of the **skills ecosystem**, not a
Jackrabbit construct. Jackrabbit provides **labels** (a global vocabulary, created on
demand, applicable to any ticket); each role is recorded as a **label name** in the
`triage:` namespace. This document is the single source of truth for the five names.

| Label name              | Meaning                                  |
| ----------------------- | ---------------------------------------- |
| `triage:needs-triage`   | Maintainer needs to evaluate this issue  |
| `triage:needs-info`     | Waiting on reporter for more information |
| `triage:ready-for-agent`| Fully specified, ready for an AFK agent  |
| `triage:ready-for-human`| Requires human implementation            |
| `triage:wontfix`        | Will not be actioned                     |

Triage labels are **ordinary labels** (ADR-0027): Jackrabbit neither documents nor
enforces any role vocabulary, and nothing in the product attaches meaning to a
`triage:*` name. They render like any other label chip, and a ticket may carry
whatever labels its workflow gives it.

## Recording a role

Attach the label by name through the generic labels API (created on demand):

    curl -s -X POST http://localhost:8080/api/v1/tickets/<id>/labels \
      -H 'Content-Type: application/json' \
      -d '{"name": "triage:ready-for-agent"}'

Detach with `DELETE /api/v1/tickets/<id>/labels/<label_id>`, or replace the label set
via ticket update (`PATCH /api/v1/tickets/<id>` with `labels`). There is no
dedicated triage endpoint (JRB-032 removed it); this document is the single
source of truth for the role names.

## Reading a role

A ticket's labels are part of the ticket payload (`GET /api/v1/tickets/<id>` →
`labels`) and readable directly via `GET /api/v1/tickets/<id>/labels`. Triage labels
render as ordinary label chips on the ticket page and in the backlog table.

> At-most-one-role is an mp-skills convention, not enforced by Jackrabbit: the plain
> labels API lets a ticket carry several `triage:*` labels at once. Tooling that
> expects a single role must manage replacement itself (detach the old label when
> attaching the new one).
