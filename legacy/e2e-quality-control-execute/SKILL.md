---
name: e2e-quality-control-execute
description: >
  Phase 2 of the isolated E2E quality-control check for Aplicatudo Maestro
  work. Given a checkpoint reference (usually handed off directly from
  e2e-quality-control-validate in the same turn) and an apply decision
  (apply all / apply none / apply some, named), delegates to the
  e2e-qc-orchestrator subagent (execute phase), which resolves the approved
  subset of findings, delegates their application to the e2e-qc-formatter
  subagent, and cleans up the run's checkpoint and marker file. Can also be
  invoked standalone against an existing checkpoint path — e.g. to resume a
  run from an earlier session — in which case it first re-presents the
  checkpoint's report and asks the apply choice itself before delegating.
  Use whenever the user runs `/e2e-quality-control-execute`, says to
  apply/skip previously-found E2E quality-control findings, or references a
  prior E2E quality-control checkpoint file. Do not use this skill to run a
  fresh check — that is `e2e-quality-control-validate`.
license: MIT
model: sonnet
effort: high
compatibility: >
  Claude Code only. Delegates to the e2e-qc-orchestrator subagent
  (.claude/agents/), which itself delegates to e2e-qc-formatter — both
  require the Agent tool and per-subagent tool restriction — not available
  in Cursor.
metadata:
  version: "3.0.0"
  openworld: "false"
---

# e2e-quality-control-execute

This skill is the main-session half of phase 2. It never edits a target file
itself — all of that lives inside the `e2e-qc-orchestrator` subagent and,
beneath it, the `e2e-qc-formatter` subagent. This skill's own job is
resolving the apply decision (asking for it if not already known) and
delegating.

## Steps

1. Determine whether the apply decision is already known:
   - If invoked as a same-turn hand-off from `e2e-quality-control-validate`,
     both `checkpoint_path` and `decision` are already given — skip to
     step 3.
   - If invoked standalone with only a `checkpoint_path` (e.g. resuming a
     run from an earlier session), continue to step 2.

2. Re-present the checkpoint (standalone invocation only):
   - Read the checkpoint file directly (a plain read, not a delegation —
     this skill may read the checkpoint's own bookkeeping content, it just
     never edits a target file). Extract `plain_language_report` and
     `findings`.
   - If the file is missing, malformed, or its `status` is not
     `pending_approval`, stop and report — do not guess at a decision.
   - Present the report in chat. Ask via UI: apply all suggested changes /
     apply none / apply some (I will name which findings).

3. Delegate to the `e2e-qc-orchestrator` subagent (Agent tool,
   `subagent_type: e2e-qc-orchestrator`). State the delegation plainly:
   - Objective: run the execute phase (`phase: execute`) for
     `checkpoint_path` and the resolved `decision`.
   - Output format: the final edit-summary report, plus confirmation the
     checkpoint and marker were removed.
   - Tool guidance: the subagent has `Agent`, `Read`, `Write` only.
   - Boundaries: it may act only on the approved subset of `decision`; it
     must not be asked to decide anything or ask the user anything.

4. Present the final report to the user in chat.

## Operating rules

- Never call `Edit` on a target file yourself; only the Formatter subagent
  does that.
- Never resolve `decision` on your own judgment when invoked standalone;
  always ask the user via UI first.
- If the orchestrator subagent's return doesn't confirm the checkpoint and
  marker were removed, report that discrepancy rather than assuming cleanup
  succeeded.
