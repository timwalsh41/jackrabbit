# implement-spec orchestration for the labels feature

`.agents/skills/implement-spec/orchestrate.js` is a copy of the global skill script
(`~/.pi/agent/skills/implement-spec/orchestrate.js`) with three fixes needed to run it
against this pi-subagents version. The tracked copy of the same file lives here, so the
patch is visible in git; the `.agents/` copy is gitignored but is the one the workflow
runner loads.

## Fixes

1. **Numeric args arrive as strings.** The workflow sandbox stringifies JSON scalars, so
   `args.gateTimeoutMs` is `"900000"`, not `900000`. The strict integer checks in the
   harness (`gate.timeoutMs`, `runs.run timeoutMs`) then reject the gate with
   `gate.timeoutMs must be an integer >= 1`, and every implementer fails before it starts.
   `numArg()` / `boolArg()` coerce the args once, up front.
2. **The captured patch location is now concrete.** The harness captures an implementer's
   uncommitted work as a patch under the child's async run directory
   (`.../async-subagent-runs/<runId>/worktree-diffs/step-0/*.patch`) and keeps the
   worktree on disk. The sandbox has no filesystem access, so `patchLocation()` derives
   those paths from the child result and hands them to the merger and fixer instead of
   leaving them to guess.
3. **The implementer task carries the tracker convention.** The tracker convention docs
   (`docs/agents/`) are gitignored, so they are absent in a managed worktree. The task
   now names the tracker URL, the read/update commands, and the resolve convention
   (check the criteria, append `## Answer`, set `**Status:** resolved`).

## Usage

    subagent({
      workflow: ".agents/skills/implement-spec/orchestrate.js",
      async: true,
      args: {
        specPath: ".scratch/labels/spec.md",
        ticketsRef: "<tracker target>",
        integrationBranch: "labels-integration",
        fullGate: "uv run pytest -x",
        narrowGate: "uv run pytest -x tests/unit tests/integration",
        baseBranch: "main"
      }
    })
