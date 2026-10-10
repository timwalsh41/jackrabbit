# Development guidelines

- When making technical decisions, don't give much weight to development cost
- When doing bug fixes always start by reproducing the bug in an end-to-end test setting as closely aligned with the real user workflow as possible
- Prefer established reputable third party libraries to building functionality from scratch
- Ensure for any new feature or fix that we add appropriate and complementary unit and end-to-end test coverage

# Tools

- Use `uv` to manage Python packages
- Use `gh-axi` (available on system path) to interact with GitHub
- Use `lavish-axi` (available on system path) to create interactive local html samples and prototypes for user feedback
- Use `chrome-devtools-axi` (available on system path) for browser interaction
- Use `treehouse` (available on system path) for worktree management
- Use the `ask_question` tool to ask a multi-option question to the user, particularly when there are a series of questions for the user to provide input on during a multi-turn conversation
- Use the terminal tool to read files outside of the project workspace

# Other

- Do not create a `CLAUDE.md` file

# Agent skills

## Issue tracker

Local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

## Triage labels

Default canonical labels: needs-triage, needs-info, ready-for-agent, ready-for-human, wontfix. See `docs/agents/triage-labels.md`.

## Domain docs

Single-context: GLOSSARY.md + docs/adr/ at repo root. See `docs/agents/domain.md`.

