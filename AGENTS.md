# Development guidelines

- When making technical decisions, don't give much weight to development cost
- When doing bug fixes always start by reproducing the bug in an end-to-end test setting as closely aligned with the real user workflow as possible
- Prefer established reputable third party libraries to building functionality from scratch
- Ensure for any new feature or fix that we add appropriate and complementary unit and end-to-end test coverage
- Fast-forward merges only, no merge commits
- Refer to `docs/CODING_STANDARDS.md` for project standards

# Tools and utilities

- Use `uv` to manage Python packages
- Use `gh-axi` skill to interact with GitHub
- Use `lavish-axi` skill to create interactive local html samples and prototypes for user feedback
- Use `chrome-devtools-axi` skill for browser interaction
- Use `treehouse` (available on system path) for worktree management
- Use the terminal tool to read files outside of the project workspace

# Interrogation protocol

**Every** multi-choice user prompt **must** use the `ask_question` tool. Never present options as markdown/list in assistant messages.

# Session logs

Current session log: `~/.pi/agent/sessions/--workspace-projects-jackrabbit--/<timestamp>_<id>.jsonl`

# Tool economy

Batch related `read`/`bash` calls. Avoid re-reading files within a session — cache in memory.

# Other

- Do not create a `CLAUDE.md` file

# Agent skills

## Issue tracker

Issues tracked as Jackrabbit tickets (prod instance, project `JRB`; epics for specs, stories for implementation stages). See `docs/agents/issue-tracker.md`.

## Triage labels

The five canonical triage roles — `needs-triage`, `needs-info`, `ready-for-agent`,
`ready-for-human` and `wontfix` — are recorded as labels in a `triage:` namespace
(`triage:needs-triage`, `triage:needs-info`, `triage:ready-for-agent`,
`triage:ready-for-human`, `triage:wontfix`). A ticket's triage role is recorded
and read as a label, never as a keyword in the ticket description.

Record a role (the label is created on demand, and replaces any previous role):

    curl -s -X POST http://localhost:8080/api/v1/tickets/<id>/triage \
      -H 'Content-Type: application/json' -d '{"role": "ready-for-agent"}'

Read a role back:

    curl -s http://localhost:8080/api/v1/tickets/<id>/triage
    curl -s http://localhost:8080/api/v1/triage/roles   # the canonical roles

> Until the label feature is deployed, the `**TRIAGE_STATUS**: <role>` keyword in
> the ticket description remains the authoritative triage marker. The change of
> authority happens at deployment: from then on the label is what counts. See
> `docs/agents/triage-labels.md`.

## Domain docs

Single-context: GLOSSARY.md + docs/adr/ at repo root. See `docs/agents/domain.md`.

## Verification

Full suite `uv run pytest -x`; fast subset `uv run pytest -x tests/unit tests/integration`; base branch main; PRs via gh-axi. See `docs/agents/verification.md`.

