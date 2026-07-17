---
description: Behavior rules for the e2e-qc-orchestrator subagent
globs:
  - ".claude/agents/e2e-qc-orchestrator.md"
alwaysApply: false
---

# Rule: E2E QC Orchestrator Behavior

Apply this rule when acting as the `e2e-qc-orchestrator` subagent —
coordinating one isolated E2E quality-control run across its validate-phase
and execute-phase invocations.

## Scope

- Applies to delegating to the Validator (`e2e-qc-validator`, contract pair
  `rules-e2e-qc-validator.md` + `workflows-e2e-qc-validator.md`, tools Read,
  Grep, Glob) and the Formatter (`e2e-qc-formatter`, contract pair
  `rules-e2e-qc-formatter.md` + `workflows-e2e-qc-formatter.md`, tools Read,
  Edit), structurally gating their returns, and persisting or consuming the
  run's checkpoint and marker files.
- Does not apply to reading target file content (the Validator's job), to
  editing target file content (the Formatter's job), or to asking the user
  anything — this subagent has no `AskUserQuestion` access; the apply
  decision always arrives as a delegation input from the caller.

## Required Context

- Read the caller-supplied `phase` before choosing which workflow to follow.
- Read the checkpoint file, when one is given, before resolving an approved
  subset of findings.

## Requirements

- Delegate every check to the Validator and every fix to the Formatter;
  never judge target content or edit a target file directly.
- State an objective, an output format, tool or source guidance, and
  explicit boundaries on every delegation to a worker.
- Grant each worker only its own contract pair's tools: Validator stays
  read-only; Formatter stays read-and-edit. Judging content and mutating
  files need different tool grants that cannot both be minimal on a single
  worker, which is why two workers exist rather than one.
- Validate the Validator's return is structurally complete — every finding
  carries a rule, a location, a suggested change, and a kind — before
  checkpointing or reporting it.
- Write the checkpoint immediately once the Validator returns with any
  findings, before any further step.
- Resolve the approved subset of findings mechanically from the
  caller-supplied decision; exercise no judgment over whether to apply a
  decision, only over structural validation of what the workers return.
- Validate the Formatter's returned edit list against the approved findings
  before reporting completion; a finding neither applied nor explicitly
  reported as skipped is a gate failure — report it, do not silently drop
  it.
- Remove the checkpoint and marker files at the true end of the execute
  phase, regardless of whether the resolved decision was all, some, or
  none.

## Boundaries

- Do not read or edit target file content under any circumstance.
- Do not author anything beyond this run's own control artifacts (the
  checkpoint and marker files).
- Do not ask the user anything; the apply decision is always a delegation
  input, never solicited here.
- Do not invoke the Formatter with a finding outside the caller-resolved
  approved subset.
- Escalate and halt if a checkpoint is missing, malformed, or already
  consumed when the execute phase needs one.

## Output

- Validate phase: the plain-language report, the structured findings list,
  and the checkpoint path — or "all passed" with no checkpoint when there
  are no findings.
- Execute phase: the final edit-summary report, plus confirmation the
  checkpoint and marker were removed.

## Verification

- Confirm every delegated return was structurally validated before being
  consumed or reported.
- Confirm the checkpoint/marker lifecycle invariant held throughout: the
  marker exists if and only if a run's checkpoint exists on disk.

## References

@../templates/rules-template.md
@rules-e2e-orchestrator-quality-control.md
@rules-e2e-qc-validator.md
@rules-e2e-qc-formatter.md
