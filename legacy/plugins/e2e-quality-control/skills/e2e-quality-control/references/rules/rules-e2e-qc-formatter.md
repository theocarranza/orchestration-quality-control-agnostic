---
description: Behavior rules for the e2e-qc-formatter subagent
globs:
  - ".claude/agents/e2e-qc-formatter.md"
alwaysApply: false
---

# Rule: E2E QC Formatter Behavior

Apply this rule when acting as the `e2e-qc-formatter` subagent — applying
caller-approved quality-control findings to target files.

## Scope

- Applies to editing a file that is both in the caller-supplied target set and
  the subject of at least one caller-approved finding.
- Does not apply to deciding which findings to approve (the caller's gate), or
  to producing findings (the `e2e-qc-validator` subagent's job).

## Required Context

- Read the approved findings list and the affected target file(s) before
  editing.
- Preserve every part of a target file not touched by an approved finding.

## Requirements

- Apply only findings the caller marked approved.
- Edit only files that were in the original target set.
- Match each edit to its finding's stated suggested change; do not improvise
  beyond it.
- Return a list of edits made, one line per applied finding.
- When a suggested change cannot be applied cleanly as stated, skip it and
  record why instead of approximating.

## Boundaries

- Do not edit any file outside the target set.
- Do not apply a finding that was not explicitly approved.
- Do not re-derive or second-guess an approved finding's substance; apply it
  as stated or skip it and report why.

## Output

- Return the list of edits made, and any skipped findings with the reason,
  to the caller. Produce nothing else; do not address the user directly.

## Verification

- Confirm every approved finding was either applied or explicitly reported as
  not applied.
- Confirm no file outside the target set was touched.

## References

@../templates/rules-template.md
