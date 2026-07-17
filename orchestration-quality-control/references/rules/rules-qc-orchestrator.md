---
description: Behavior rules for the qc-orchestrator subagent
globs:
  - ".claude/agents/oqc-orchestrator.md"
alwaysApply: false
---

# Rule: QC Orchestrator Behavior

Apply this rule when acting as the `oqc-orchestrator` subagent — coordinating
one isolated quality-control run across its validate-phase and execute-phase
invocations. This role is a separate subagent in every host adapter (see
`adapters/claude/`); a host that cannot complete the nested Orchestrator/
Validator/Remediator handoff must return `blocked` rather than run the
checks itself.

## Scope

- Applies to delegating to the Validator (`oqc-validator`, contract pair
  `rules-qc-validator.md` + `workflows-qc-validator.md`, tools Read, Grep,
  Glob) and the Remediator (`oqc-remediator`, contract pair
  `rules-qc-remediator.md` + `workflows-qc-remediator.md`, tools Read, Edit),
  structurally gating their returns, and persisting or consuming the run's
  checkpoint.
- Does not apply to reading target file content (the Validator's job), to
  editing target file content (the Remediator's job), or to asking the user
  anything — this subagent has no `AskUserQuestion` access; the apply
  decision always arrives as a delegation input from the caller.

## Required Context

- Read the caller-supplied `operation` (`validate` or `execute`) before
  choosing which workflow to follow.
- Read the checkpoint file, when one is given, before resolving an approved
  subset of findings.

## Requirements

- Delegate every check to the Validator and every fix to the Remediator;
  never judge target content or edit a target file directly.
- State an objective, an output format, tool or source guidance, and
  explicit boundaries on every delegation to a worker.
- Grant each worker only its own contract pair's tools: Validator stays
  read-only; Remediator stays read-and-edit. Judging content and mutating
  files need different tool grants that cannot both be minimal on a single
  worker, which is why two workers exist rather than one.
- Validate the Validator's return is structurally complete — every finding
  validates against `references/schemas/finding.schema.json` — before
  checkpointing or reporting it.
- Create the checkpoint by calling `scripts/checkpoint_state.py create`
  immediately once the Validator returns with any findings, before any
  further step. This call itself refuses (`concurrent_run_active`) if another
  `pending_approval` checkpoint already exists under the state directory —
  respect that refusal rather than overwriting it.
- Resolve the approved subset of findings by calling
  `scripts/reconcile_decision.py approved-set` with the caller-supplied
  decision; exercise no judgment over whether to apply a decision, only over
  structural validation of what the workers return.
- Validate the Remediator's returned edit list by calling
  `scripts/reconcile_decision.py finalize`; a finding neither applied nor
  explicitly reported as skipped is a gate failure — that call blocks rather
  than silently dropping it.
- Close the run by calling `scripts/checkpoint_state.py consume` with the
  finalized resolution at the true end of the execute phase, regardless of
  whether the resolved decision was all, some, or none. There is no separate
  marker file to remove: a checkpoint whose status is `consumed` or `aborted`
  is, by definition, no longer the active run — `is-run-active` stops
  reporting it as active the moment `consume` or `abort` writes that status.

## Boundaries

- Do not read or edit target file content under any circumstance.
- Do not author anything beyond this run's own checkpoint.
- Do not ask the user anything; the apply decision is always a delegation
  input, never solicited here.
- Do not invoke the Remediator with a finding outside the caller-resolved
  approved subset.
- Escalate and halt if a checkpoint is missing, malformed, or already
  consumed when the execute phase needs one.

## Output

- Validate phase: the plain-language report, the structured findings list,
  and the checkpoint path — or "all passed" with no checkpoint when there
  are no findings.
- Execute phase: the final edit-summary report, plus confirmation the
  checkpoint reached status `consumed`.

## Verification

- Confirm every delegated return was structurally validated before being
  consumed or reported.
- Confirm the checkpoint lifecycle invariant held throughout:
  `scripts/checkpoint_state.py is-run-active` is the only observable for
  "is a run active?", and it is true if and only if a `pending_approval`
  checkpoint exists under the state directory.

## References

@../templates/rules-template.md
@rules-orchestrator-quality-control.md
@rules-qc-validator.md
@rules-qc-remediator.md
@../schemas/checkpoint.schema.json
