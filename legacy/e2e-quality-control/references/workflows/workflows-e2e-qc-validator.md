---
description: Classify and verify E2E quality-control targets, returning structured findings and a plain-language report
---

# Workflow: E2E QC Validator

Use this workflow to classify one or more selected target files and verify
them against the packaged E2E quality-control rule sets, producing structured
findings and a plain-language report.

## Inputs

- `targets`: one or more file paths to classify and verify; required
- `language`: report language, `en` (default) or `pt-br`; optional

## Control

- Primary agent: this subagent owns classification and verification; it
  applies no changes.
- Decision model: deterministic classification by path/shape signals; LLM
  judgment reserved for whether a specific passage violates a specific rule.
- Delegation: none.

## Steps

1. Load the operating contract
   - OBEY the validator behavior rules before any other workflow action:
   @../rules/rules-e2e-qc-validator.md

2. Establish the target
   - Read every path in `targets` in full.
   - If a target is unreadable, note it and continue with the remaining
     targets.

3. Gather required context
   - Classify each target: finished artifact, generator source, workflow
     document, or orchestrator document (a target may carry more than one
     class).
   - Load only the packaged rule file(s) in `references/rules/` whose class
     matches at least one target present.

4. Execute the work
   - Walk every requirement in every loaded rule file against the matching
     targets, quoting evidence and a location per finding.
   - Respect each loaded rule file's own Boundaries to avoid false positives.
   - Record each finding as `{ violation, rule, location, suggested_change,
     kind }`.
   - Mark any requirement not verifiable from the target set as such, rather
     than fetching a missing file.

5. Assemble the result
   - Rewrite the raw findings into a plain-language report following the
     bundled plain-language files under `references/plain-language/`, in
     `language`.
   - Include a clear statement when no problems were found.

6. Finish
   - Confirm every applicable requirement was walked and every finding is
     complete (rule, location, suggested change, kind).
   - Return the structured findings list and the plain-language report text
     to the caller.

## Stop Conditions

- Stop and report if no target path is readable.
- Do not open any file outside the given target set to compensate for missing
  evidence.
- Do not decide whether to apply any suggested change; that decision belongs
  to the caller.
