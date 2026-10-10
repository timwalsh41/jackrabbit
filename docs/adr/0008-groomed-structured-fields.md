# ADR-0008: Groomed Status Requires Structured Fields

## Status
Accepted

## Context
Spec defines "Groomed = approach has been assessed, code and test updates identified, validation plan." Options for enforcement:
- Required structured fields: `approach`, `files_to_change`, `test_plan`, `validation_steps`
- Free-text only
- Hybrid: structured + optional free text

## Decision
**Four required structured fields** to enter `Groomed` status:
1. `approach` — technical approach/design summary
2. `files_to_change` — list of files/modules expected to change
3. `test_plan` — what tests to add/update (unit, integration, e2e)
4. `validation_steps` — manual verification steps for reviewer

## Consequences

### Positive
- **Meaningful gate** — "Groomed" means ready for implementation, not just "looked at"
- **Forces clarity** — writer must think through approach before coding
- **Enables automation** — "show me groomed tickets missing test_plan"
- **Review efficiency** — reviewer sees structured info, not prose hunt
- **Agent-friendly** — structured fields are parseable for AI-assisted implementation

### Negative
- **More friction** — can't just type "looks good" to groom
- **Fields may feel redundant** — small tickets might not need all four

### Mitigations
- Fields can be brief (bullet points acceptable)
- UI shows fields inline on ticket detail; "Mark Groomed" button validates all four present
- For trivial tickets (typo fix), fields can be "N/A" or one-liners

## Alternatives Considered
- **Free-text**: Rejected — "Groomed" becomes meaningless checkbox; no enforcement of thinking.
- **Hybrid**: Rejected — optional fields don't create the gate; required fields do.