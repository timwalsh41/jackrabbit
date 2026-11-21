# Development guidelines

- When making technical decisions, don't give much weight to development cost
- When doing bug fixes always start by reproducing the bug in an end-to-end test setting as closely aligned with the real user workflow as possible
- Prefer established reputable third party libraries to building functionality from scratch
- Ensure for any new feature or fix that we add appropriate and complementary unit and end-to-end test coverage
- Fast-forward merges only, no merge commits
- Use "Conventional Commit" style messages for commits and PR titles
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

The five canonical triage labels — `triage:needs-triage`, `triage:needs-info`,
`triage:ready-for-agent`, `triage:ready-for-human`, `triage:wontfix` — are an
mp-skills label-name convention over Jackrabbit's generic labels feature, not a
Jackrabbit construct (ADR-0027). Record a role by attaching the label and read it
back from the ticket's labels; never as a keyword in the ticket description.

Record a role (the label is created on demand):

    curl -s -X POST http://localhost:8080/api/v1/tickets/<id>/labels \
      -H 'Content-Type: application/json' -d '{"name": "triage:ready-for-agent"}'

Read a ticket's labels (the ticket payload's `labels` field carries them too):

    curl -s http://localhost:8080/api/v1/tickets/<id>/labels

> At-most-one-role is an mp-skills convention that the plain labels API does not
> enforce: when replacing a role, detach the old `triage:*` label. See
> `docs/agents/triage-labels.md`.

## Domain docs

Single-context: GLOSSARY.md + docs/adr/ at repo root. See `docs/agents/domain.md`.

## Verification

Full suite `uv run pytest -x`; fast subset `uv run pytest -x tests/unit tests/integration`; base branch main; PRs via gh-axi. See `docs/agents/verification.md`.

