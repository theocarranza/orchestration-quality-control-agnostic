---
description: Delegate a quality-control check to the Validator and hand back a report plus a checkpoint reference for approval
---

# Workflow: QC Orchestrator — Validate Operation

Use this workflow to delegate a quality-control check to the Validator
subagent and return either an "all passed" verdict or a plain-language
report plus a durable checkpoint the caller can act on later.

## Inputs

- `targets`: one or more file paths, a folder, or a multi-select set;
  required — stop and report if absent
- `profile`: selected rule profile, `core` (default) or a profile id; optional
- `language`: report language, `en` (default) or `pt-br`; optional

## Control

- Primary agent: this subagent owns delegating to the Validator and
  persisting the checkpoint; it applies no changes and asks the user
  nothing.
- Decision model: deterministic — always delegate to the Validator; always
  checkpoint when the return contains any findings.
- Delegation: `oqc-validator`, via the Agent tool.

## Steps

1. Load the operating contract
   - OBEY the orchestrator behavior rules before any other workflow action:
   @../rules/rules-qc-orchestrator.md

2. Establish the target
   - Confirm `targets` is non-empty. The caller is responsible for having
     already collected it from the user; this workflow stops and reports
     rather than asking.
   - Confirm `scripts/checkpoint_state.py is-run-active` reports `false`
     before starting; if it reports `true`, stop and report the existing
     run's `run_id` instead of starting a second one.

3. Gather required context
   - None beyond `targets`, `profile`, and `language`; this subagent never
     reads target content itself.

4. Execute the work
   - Delegate to the Validator: objective — classify and verify every
     target in `targets` against the packaged rule sets in
     `references/rules/`, plus the selected profile's rule sets; output
     format — structured findings list conforming to
     `references/schemas/finding.schema.json`, plus a plain-language report
     string; tool guidance — Validator has Read, Grep, Glob, and Bash
     restricted to `scripts/classify_targets.py` and
     `scripts/derive_finding_id.py`; boundaries — Validator may read only
     `targets` and the packaged rule files.
   - Validate the return is structurally complete (every finding validates
     against `references/schemas/finding.schema.json`). If malformed,
     re-delegate once to the Validator with corrective guidance naming the
     missing field(s); if the retry is still malformed, stop and report.

5. Assemble the result
   - If the Validator returned zero findings: no checkpoint is written;
     the result is "all passed".
   - If the Validator returned one or more findings: call
     `scripts/checkpoint_state.py create` with the targets, profile,
     language, findings, and report. This call refuses
     (`concurrent_run_active`) if another `pending_approval` checkpoint
     already exists — respect that refusal.

6. Finish
   - Return to the caller: the plain-language report, the structured
     findings list, and the checkpoint path — or "all passed" with no
     checkpoint.

## Stop Conditions

- Stop and report if `targets` is empty or unreadable.
- Stop and report if a run is already active (`is-run-active` reports
  `true`) rather than starting a concurrent one.
- Never ask the user anything from within this workflow.
- Never proceed to a Remediator delegation; that belongs only to the execute
  workflow.
