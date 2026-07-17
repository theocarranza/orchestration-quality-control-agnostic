---
description: Resolve a checkpointed run's approved findings and delegate their application to the Formatter
---

# Workflow: E2E QC Orchestrator — Execute Phase

Use this workflow to read an existing checkpoint, resolve the caller-supplied
apply decision against it, delegate approved findings to the Formatter, and
clean up the run's state.

## Inputs

- `checkpoint_path`: path to an existing checkpoint file; required
- `decision`: the caller-resolved apply decision — `all`, `none`, or a named
  list of finding ids; required, never solicited by this workflow itself

## Control

- Primary agent: this subagent owns reading the checkpoint, resolving the
  approved subset, delegating to the Formatter, and cleanup; it asks the
  user nothing and edits no target file itself.
- Decision model: deterministic — the approved subset is mechanically
  derived from `decision`.
- Delegation: `e2e-qc-formatter`, via the Agent tool (only when the
  resolved subset is non-empty).

## Steps

1. Load the operating contract
   - OBEY the orchestrator behavior rules before any other workflow action:
   @../rules/rules-e2e-qc-orchestrator.md

2. Establish the target
   - Read `checkpoint_path`. Stop and report if it is missing, malformed,
     or its `status` is not `pending_approval`.

3. Gather required context
   - Resolve `decision` against the checkpoint's `findings`: `all` → every
     finding; `none` → an empty set; a named list → exactly those ids.

4. Execute the work
   - If the resolved subset is empty: skip directly to cleanup in step 6.
   - Otherwise, delegate to the Formatter: objective — apply exactly the
     approved findings; output format — list of edits made, and any
     skipped with reason; tool guidance — Formatter has Read, Edit only;
     boundaries — Formatter may edit only files in the checkpoint's
     `targets`, and only the approved findings.
   - Validate the Formatter's returned edit list against the approved
     findings. A finding neither applied nor explicitly reported as
     skipped triggers one re-delegation to the Formatter naming the
     missing finding id(s); if it is still unaccounted for after the
     retry, report it as a gate failure — do not silently drop it.

5. Assemble the result
   - Build the final report: what was checked, what was found, what was
     applied, what was skipped (with reason), and what was declined.

6. Finish
   - Delete the checkpoint file and remove the marker file — the true end
     of the whole two-phase run.
   - Return the final report to the caller.

## Stop Conditions

- Stop and report if the checkpoint is missing, malformed, or already
  consumed.
- Never delegate to the Formatter when `decision` resolves to an empty set.
- Never apply a finding outside the resolved subset.
- Never leave the checkpoint or marker file behind once this phase
  completes, whether findings were applied or declined.
