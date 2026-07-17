---
description: Apply caller-approved quality-control findings to their target files
---

# Workflow: QC Remediator

Use this workflow to apply a caller-approved subset of quality-control
findings to their target files.

## Inputs

- `approved_findings`: the subset of findings the caller approved for
  application, each conforming to `references/schemas/finding.schema.json`;
  required
- `targets`: the file path(s) the approved findings apply to; required

## Control

- Primary agent: this subagent owns applying the approved findings; it makes
  no approval decisions.
- Decision model: deterministic — apply exactly what was approved, at the
  stated location.
- Delegation: none.

## Steps

1. Load the operating contract
   - OBEY the remediator behavior rules before any other workflow action:
   @../rules/rules-qc-remediator.md

2. Establish the target
   - Identify, for each approved finding, the specific file in `targets` it
     applies to.
   - Respect the boundary that no file outside `targets` may be touched.

3. Gather required context
   - Read each affected target file in full before editing it.
   - Keep each finding's `suggested_change` (`{before, after}`) available for
     the edit step.

4. Execute the work
   - For each approved finding, render its change with
     `scripts/render_diff.py --workspace <dir> --path <target> --before
     <before-file> --after <after-file>` and apply exactly that literal diff.
   - Preserve every part of the file not covered by an approved finding.
   - If `render_diff.py` blocks (`anchor_not_found` or `missing_target`), skip
     the finding and record the reason instead of guessing.

5. Assemble the result
   - Produce a list of edits made, one line per applied finding, naming the
     file and what changed.
   - Include any skipped findings with the reason they were skipped, shaped
     for `scripts/reconcile_decision.py finalize`'s `--outcomes-json` input.

6. Finish
   - Confirm every approved finding was either applied or explicitly recorded
     as skipped.
   - Return the edit list to the caller.

## Stop Conditions

- Stop and report if an approved finding's target file is not in `targets`.
- Do not touch any file outside `targets`.
- Do not apply a finding that was not in `approved_findings`.
