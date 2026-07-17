---
description: Resolve a checkpointed run's approved findings and delegate their application to the Remediator
---

# Workflow: QC Orchestrator — Execute Operation

Use this workflow to read an existing checkpoint, resolve the caller-supplied
apply decision against it, delegate approved findings to the Remediator, and
close the run's state.

## Inputs

- `checkpoint_path`: path to an existing checkpoint file; required
- `decision`: the caller-resolved apply decision — `all`, `none`, or a named
  list of finding ids; required, never solicited by this workflow itself

## Control

- Primary agent: this subagent owns reading the checkpoint, resolving the
  approved subset, delegating to the Remediator, and closing the run; it
  asks the user nothing and edits no target file itself.
- Decision model: deterministic — the approved subset is mechanically
  derived from `decision` via `scripts/reconcile_decision.py`.
- Delegation: `oqc-remediator`, via the Agent tool (only when the
  resolved subset is non-empty).

## Steps

1. Load the operating contract
   - OBEY the orchestrator behavior rules before any other workflow action:
   @../rules/rules-qc-orchestrator.md

2. Establish the target
   - Read `checkpoint_path`. Stop and report if it is missing, malformed,
     or its `status` is not `pending_approval` (`scripts/checkpoint_state.py
     status` reports this).

3. Gather required context
   - Resolve `decision` against the checkpoint's `findings` by calling
     `scripts/reconcile_decision.py approved-set --checkpoint
     <checkpoint_path> --decision <decision>`: `all` → every finding;
     `none` → an empty set; a named list → exactly those ids. An unknown
     named id blocks (`unknown_finding_id`) rather than being silently
     ignored.

4. Execute the work
   - If the resolved subset is empty: skip directly to closing the run in
     step 6.
   - Otherwise, delegate to the Remediator: objective — apply exactly the
     approved findings; output format — outcomes shaped for
     `scripts/reconcile_decision.py finalize`'s `--outcomes-json` input
     (`{finding_id, outcome, reason?, applied_path?}` per entry); tool
     guidance — Remediator has Read, Edit only; boundaries — Remediator may
     edit only files in the checkpoint's `targets`, and only the approved
     findings.
   - Call `scripts/reconcile_decision.py finalize --checkpoint
     <checkpoint_path> --approved-ids <approved-ids> --outcomes-json
     <remediator-outcomes>`. This call blocks if any approved finding has no
     reported outcome, if any outcome names an edit outside the checkpoint's
     `targets` (`target_outside_approved_set`), or if a skip carries no
     reason. On a block that names a missing outcome, re-delegate once to the
     Remediator naming the missing finding id(s); if it is still unaccounted
     for after the retry, report it as a gate failure — do not silently drop
     it.

5. Assemble the result
   - Build the final report: what was checked, what was found, what was
     applied, what was skipped (with reason), and what was declined.

6. Finish
   - Call `scripts/checkpoint_state.py consume` with the finalized
     resolution — the true end of the whole two-operation run. There is no
     marker file to remove separately; `is-run-active` stops reporting this
     run the moment `consume` writes `status: consumed`.
   - Return the final report to the caller.

## Stop Conditions

- Stop and report if the checkpoint is missing, malformed, or already
  consumed.
- Never delegate to the Remediator when `decision` resolves to an empty set.
- Never apply a finding outside the resolved subset.
- Never leave a checkpoint in `pending_approval` once this operation
  completes, whether findings were applied or declined.
