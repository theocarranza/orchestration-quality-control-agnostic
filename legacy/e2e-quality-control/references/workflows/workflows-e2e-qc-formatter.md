---
description: Apply caller-approved E2E quality-control findings to their target files
---

# Workflow: E2E QC Formatter

Use this workflow to apply a caller-approved subset of quality-control
findings to their target files.

## Inputs

- `approved_findings`: the subset of findings the caller approved for
  application, each `{ violation, rule, location, suggested_change, kind }`;
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
   - OBEY the formatter behavior rules before any other workflow action:
   @../rules/rules-e2e-qc-formatter.md

2. Establish the target
   - Identify, for each approved finding, the specific file in `targets` it
     applies to.
   - Respect the boundary that no file outside `targets` may be touched.

3. Gather required context
   - Read each affected target file in full before editing it.
   - Keep each finding's stated location and suggested change available for
     the edit step.

4. Execute the work
   - For each approved finding, apply its suggested change at its stated
     location.
   - Preserve every part of the file not covered by an approved finding.
   - If a suggested change cannot be applied cleanly as stated, skip it and
     record the reason instead of guessing.

5. Assemble the result
   - Produce a list of edits made, one line per applied finding, naming the
     file and what changed.
   - Include any skipped findings with the reason they were skipped.

6. Finish
   - Confirm every approved finding was either applied or explicitly recorded
     as skipped.
   - Return the edit list to the caller.

## Stop Conditions

- Stop and report if an approved finding's target file is not in `targets`.
- Do not touch any file outside `targets`.
- Do not apply a finding that was not in `approved_findings`.
