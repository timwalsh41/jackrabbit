# Triage Labels

The engineering skills speak in terms of five canonical triage roles. Jackrabbit has
**labels** (a global vocabulary, created on demand, appliable to any ticket), so each
role is recorded as a **label in the `triage:` namespace** rather than as a keyword in
the ticket description.

| Role in the skills | Recorded as a label            | Meaning                                  |
| ------------------ | ------------------------------ | ---------------------------------------- |
| `needs-triage`     | `triage:needs-triage`          | Maintainer needs to evaluate this issue  |
| `needs-info`       | `triage:needs-info`            | Waiting on reporter for more information |
| `ready-for-agent`  | `triage:ready-for-agent`       | Fully specified, ready for an AFK agent  |
| `ready-for-human`  | `triage:ready-for-human`       | Requires human implementation            |
| `wontfix`          | `triage:wontfix`               | Will not be actioned                     |

When a skill mentions a role (e.g. "apply the AFK-ready triage label"), **set** the
role as a label on the ticket and **read** it back as a label. Do not parse the ticket
description to find the role.

## Recording a role

    curl -s -X POST http://localhost:8080/api/v1/tickets/<id>/triage \
      -H 'Content-Type: application/json' \
      -d '{"role": "ready-for-agent"}'

The label is created on demand, and setting a role replaces any triage role the
ticket carried before (a ticket carries at most one triage role). Other labels on
the ticket are left alone. An unknown role is rejected with `422`.

The same effect is available by attaching the label directly:

    curl -s -X POST http://localhost:8080/api/v1/tickets/<id>/labels \
      -H 'Content-Type: application/json' \
      -d '{"name": "triage:ready-for-agent"}'

## Reading a role

    curl -s http://localhost:8080/api/v1/tickets/<id>/triage
    # {"role": "ready-for-agent", "label": {"id": 7, "name": "triage:ready-for-agent", "color": "#..."}}

    curl -s http://localhost:8080/api/v1/triage/roles
    # the five canonical roles and the label each one is recorded as

A ticket's labels are also part of the ticket payload
(`GET /api/v1/tickets/<id>` → `labels`), and the role is visible in the interface: on
the ticket page and in the backlog table.

## Until the label feature is deployed

> The description keyword `**TRIAGE_STATUS**: <role>` remains the authoritative
> triage marker until the label feature is deployed. The change of authority happens
> at deployment: from that moment the label is what counts, and the keyword in the
> description is only legacy text.
