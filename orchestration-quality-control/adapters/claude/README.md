# Claude adapter

This adapter mechanizes the portable core's rules into three separate
subagents with distinct tool grants, matching the benchmarked design of the
retired `e2e-quality-control` skill (see
`legacy/e2e-quality-control-workspace/iteration-1/benchmark.json`: 100% pass
rate with the skill enabled). It is one way to run this package, not the
only way — see the core `README.md` for the single-agent default every host
can fall back to.

## What this adapter adds beyond the portable core

| Piece | What it does |
| --- | --- |
| `commands/oqc-validate.md` | Main-session entry point for the validate operation: collects target/profile/language, delegates, presents the report, asks the apply decision. |
| `commands/oqc-execute.md` | Main-session entry point for the execute operation: resolves the apply decision, delegates, presents the final report. |
| `commands/oqc-upgrade.md` | Main-session entry point for guided orchestration upgrade: confirms discovery, delegates prepare/apply, records atomic approval. |
| `commands/e2e-quality-control-validate.md`, `commands/e2e-quality-control-execute.md` | Compatibility aliases for the retired 3.0.0 command names — see the migration table in `profiles/aplicatudo-e2e/README.md`. |
| `agents/oqc-orchestrator.md` | Opus, tools `Agent, Read, Write, Bash` (Bash restricted to `scripts/`). Owns routing, checkpoint bookkeeping, and gate validation. Never reads or edits target content. |
| `agents/oqc-validator.md` | Sonnet, tools `Read, Grep, Glob, Bash` (Bash restricted to `scripts/classify_targets.py` and `scripts/derive_finding_id.py`). Mechanically read-only — this subagent has no tool capable of writing a file. |
| `agents/oqc-remediator.md` | Sonnet, tools `Read, Edit, Bash` (Bash restricted to `scripts/render_diff.py`). Applies only findings the orchestrator hands it, only inside the checkpoint's target set. |
| `agents/oqc-upgrade-orchestrator.md` | Opus, tools `Agent, Read, Write, Bash` (Bash restricted to `discover_structure.py` and `upgrade_state.py`). Coordinates upgrade prepare/apply. |
| `agents/oqc-proposal-author.md` | Sonnet, tools `Read, Grep, Glob`. Drafts one atomic upgrade proposal; never writes targets. |
| `agents/oqc-upgrade-applier.md` | Sonnet, tools `Read, Bash` (Bash restricted to `scripts/apply_upgrade.py`). Applies one approved upgrade checkpoint. |
| `hooks/oqc-block-main-edits.py` | A `PreToolUse` hook that blocks the main session's own `Edit`/`Write` on any path listed in an active checkpoint's `targets`, so a user cannot bypass the approval gate by editing the file directly while a review is pending. |

## Installation

1. Copy `agents/*.md` into the target project's `.claude/agents/`.
2. Copy `commands/*.md` into the target project's `.claude/commands/`.
3. Register the hook in the target project's `.claude/settings.json`:

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Edit|Write",
           "hooks": [
             {
               "type": "command",
               "command": "python3 <path-to-package>/orchestration-quality-control/adapters/claude/hooks/oqc-block-main-edits.py"
             }
           ]
         }
       ]
     }
   }
   ```

4. Ensure `python3` is on the host's `PATH` — every script this adapter
   calls, including the hook, is stdlib-only and needs no package
   installation.

## Capability matrix

| Guarantee | Claude adapter | A host with no subagent isolation |
| --- | --- | --- |
| Validator cannot write a file | Mechanical — the subagent's tool grant excludes every write-capable tool | Not enforced by the host; the core's rules ask a single agent not to write during validation, but nothing prevents it if the agent disregards the instruction |
| Direct edits blocked while a run is pending | Mechanical — the `PreToolUse` hook intercepts every `Edit`/`Write` call | Not enforced; disclose this explicitly rather than implying parity |
| Checkpoint state transitions are legal | Enforced by `scripts/checkpoint_state.py` on every host, including this one | Same — this guarantee does not depend on subagent isolation |
| Finding identity survives partial apply | Enforced by `scripts/derive_finding_id.py` on every host | Same |
| Report built only from structured findings, never raw target text | An instruction every agent (orchestrator, single-agent core, or otherwise) must follow; not currently mechanically enforced on any host | Same |

A host adapter without subagent isolation must state plainly, wherever it
documents itself, that tool-boundary enforcement is prompt-based rather than
mechanical — it must never claim Claude-level guarantees it cannot back with
a tool grant or a hook.
