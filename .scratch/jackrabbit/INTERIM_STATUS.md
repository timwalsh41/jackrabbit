# INTERIM STATUS — implement-spec audit & remediation

_Date: 2026-10-15 · Branch: `jackrabbit-integration` @ `ccd4068` · Written by: session `2026-10-14T23-30-04` (audit of `implement-02`)_

## Where the implement-spec work stands

The implement-02 session implemented tickets 02–12 + 14 with **all work uncommitted
in the main checkout on `main`** (no worktree was ever created). This branch
(`jackrabbit-integration`) now holds that work as a single checkpoint commit,
`ccd4068` — committed from the working tree after lint/test triage.

### Gates at `ccd4068`

- `ruff check .` + `ruff format` — clean (fixed: f-string syntax error at
  `tests/cdx_helper.py:420` — a lone `}` that also **blocked every commit**
  via pre-commit; plus 45 lint errors across 12 files).
- `pytest tests/unit tests/integration` — **256 passed, 0 failed** after the
  fix below (was 255 passed / 1 failed):
  `tests/unit/test_ticket_service.py::TestTicketLookup::test_get_ticket_by_full_id_prefix_is_case_insensitive`
  (assert `None` at line 148). **FIXED 2026-10-15, commit `0181c42`** —
  `get_ticket_by_full_id` now matches the prefix case-insensitively via
  `func.upper(Project.prefix) == arg.upper()` in `jackrabbit/services.py`.
  This bug was inherited from implement-02's inline work and **blocked the
  worktree verification gate** (`pytest -x` runs against integration HEAD),
  which is why fixing it before resuming the workflow mattered.

### Ticket ledger (source of truth: ticket files in `.scratch/jackrabbit/issues/`)

- **01** — resolved, 7/7 acceptance boxes checked, Answer present. The only
  properly closed ticket.
- **02–12, 14** — marked `resolved` with **ZERO acceptance boxes checked and no
  Answer section** → none were verified; resolution claims are unverified.
- **13 (testing infrastructure)** — `ready-for-agent`; its implementer hit the
  30-min foreground timeout twice. Partial artifacts exist
  (`tests/cdx_helper.py`, conftest fixes).
- **15 (E2E)** — `ready-for-agent`; partially done inline (tests/e2e/* exist
  but were orphaned when the session crashed mid-loop).

### Known junk in the working tree (never commit)

`server.log` (2.6 MB), `jackrabbit/templates/ticket_form_partial.html.bak`,
`acceptance-report.json`.

## What this session changed

1. **Commit `ccd4068`** — checkpoint of all implement-02 work on the
   integration branch (see gates above).
2. **`orchestrate.js` rewritten** (`.agents/skills/implement-spec/orchestrate.js`):
   - Sandbox-safe: runs inside the pi workflow sandbox (no fs/require/shell —
     the old script used `require('fs')`/`execSync` and could never have run).
   - Passes `subagent {action:"validate"}` (the old script failed validation:
     nested async at line 274, unknown agent names).
   - **Worktree enforcement**: every implementer runs with
     `worktree: true, baseRef: refs/heads/jackrabbit-integration` — the main
     checkout is never switched (audit finding: implementers mutated the home
     repo on `main`).
   - **Verification gating**: implementer + merger runs carry
     `gate: "pytest -x"`; ticket statuses are re-read from ticket FILES each
     wave; resolution requires a green verified merge.
   - Fixed ticket parser for the real bold format (`**Status:**`,
     `**Blocked by:**`) by delegating discovery to a scout child (validated
     empirically: correct graph for all 15 tickets).
   - Unknown-agent-name spawns fixed (implementer/merger/reviewer-*/pr-writer
     now resolve; defs in `.pi/agents/*.md`).
3. **SKILL.md rewritten** to match: launch via workflow + args, yield and wait
   for the receipt, no inline fallbacks, manual-fallback section preserved.

## Next session: recommended kickoff order

1. ~~Fix the one failing unit test above~~ — DONE (commit `0181c42`, suite fully green).
2. Re-point tickets 02–12+14 through verification: check acceptance boxes
   only where evidence exists (this is audit finding: statuses lie).
3. Resume the frontier (13, 15) via the rewritten workflow:
   `subagent({ workflow: "./.agents/skills/implement-spec/orchestrate.js", async: true })`.
4. Note: `.agents/` and `.pi/` are **gitignored** — the rewritten script,
   SKILL.md and agent defs are local-only. Committing them requires a
   `.gitignore` change (deliberate: repo policy keeps scaffolding out).

## Why implement-02 derailed (one-paragraph recap)

Not context exhaustion (83k→213k of 934k used). Three causes: (a) free-tier
model degradation cascade (`nvidia/nemotron-3-ultra…` → `xiaomi/mimo-v2.6-flash`
→ ~103 duplicate tool calls + upstream 324 Nvidia-overload errors), (b) process
crash at ~23:00 Oct 14 losing uncommitted edits and orphaning 8 pytest
processes, (c) compaction goal-drift — the compressed summary reframed the goal
as "fix E2E test failures". Mitigations now in SKILL.md (yield-and-wait,
resume-not-fallback) plus model discipline (avoid degraded free tiers for
long orchestration sessions).
