---
description: Classify and verify quality-control targets, returning structured findings and a plain-language report
---

# Workflow: QC Validator

Use this workflow to classify one or more selected target files and verify
them against the packaged orchestration quality-control rule sets — plus any
selected profile's rule sets — producing structured findings and a
plain-language report.

## Inputs

- `targets`: one or more file paths to classify and verify; required
- `profile`: selected rule profile, `core` (default) or a profile id; optional
- `language`: report language, `en` (default) or `pt-br`; optional

## Control

- Primary agent: this subagent owns classification and verification; it
  applies no changes.
- Decision model: deterministic classification via `scripts/classify_targets.py`;
  LLM judgment reserved for whether a specific passage violates a specific
  rule.
- Delegation: none.

## Steps

1. Load the operating contract
   - OBEY the validator behavior rules before any other workflow action:
   @../rules/rules-qc-validator.md

2. Establish the target
   - Read every path in `targets` in full.
   - If a target is unreadable, note it and continue with the remaining
     targets.

3. Gather required context
   - Classify each target by running `scripts/classify_targets.py --workspace
     <dir> [--profile <profile.json>] <targets...>`: rules-file, workflow,
     orchestrator, generator-source, or a profile-defined class (a target may
     carry more than one class).
   - Load only the packaged rule file(s) in `references/rules/` whose class
     matches at least one target present, plus the selected profile's rule
     files when `profile` is not `core`.

4. Execute the work
   - Walk every requirement in every loaded rule file against the matching
     targets, quoting evidence and a location per finding.
   - Respect each loaded rule file's own Boundaries to avoid false positives.
   - For each violation, derive its id with `scripts/derive_finding_id.py
     derive`, passing the rule code, kind, target path, and a verbatim anchor
     excerpt. A finding whose anchor is rejected (`anchor_not_found`) is
     re-derived from the actual file content, not reported as-is.
   - Record each finding conforming to `references/schemas/finding.schema.json`:
     `id, kind, rule, location, anchor, violation, suggested_change,
     confidence`.
   - Mark any requirement not verifiable from the target set as such, rather
     than fetching a missing file.

5. Assemble the result
   - Rewrite the raw findings into a plain-language report following the
     bundled plain-language files under `references/plain-language/`, in
     `language`. Build the report only from the structured findings, never by
     re-reading raw target content.
   - Include a clear statement when no problems were found.

6. Finish
   - Confirm every applicable requirement was walked and every finding
     validates against `references/schemas/finding.schema.json`.
   - Return the structured findings list and the plain-language report text
     to the caller.

## Stop Conditions

- Stop and report if no target path is readable.
- Do not open any file outside the given target set to compensate for missing
  evidence.
- Do not decide whether to apply any suggested change; that decision belongs
  to the caller.
