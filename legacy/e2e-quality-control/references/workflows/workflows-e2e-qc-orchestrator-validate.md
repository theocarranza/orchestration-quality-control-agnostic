---
description: Delegate a quality-control check to the Validator and hand back a report plus a checkpoint reference for approval
---

# Workflow: E2E QC Orchestrator — Validate Phase

Use this workflow to delegate a quality-control check to the Validator
subagent and return either an "all passed" verdict or a plain-language
report plus a durable checkpoint the caller can act on later.

## Inputs

- `targets`: one or more file paths, a folder, or a multi-select set;
  required — stop and report if absent
- `language`: report language, `en` (default) or `pt-br`; optional

## Control

- Primary agent: this subagent owns delegating to the Validator and
  persisting the checkpoint; it applies no changes and asks the user
  nothing.
- Decision model: deterministic — always delegate to the Validator; always
  checkpoint when the return contains any findings.
- Delegation: `e2e-qc-validator`, via the Agent tool.

## Steps

1. Load the operating contract
   - OBEY the orchestrator behavior rules before any other workflow action:
   @../rules/rules-e2e-qc-orchestrator.md

2. Establish the target
   - Confirm `targets` is non-empty. The caller is responsible for having
     already collected it from the user; this workflow stops and reports
     rather than asking.

3. Gather required context
   - None beyond `targets` and `language`; this subagent never reads target
     content itself.

4. Execute the work
   - Delegate to the Validator: objective — classify and verify every
     target in `targets` against the packaged rule sets in
     `references/rules/`; output format — structured findings list `{
     violation, rule, location, suggested_change, kind }` plus a
     plain-language report string; tool guidance — Validator has Read,
     Grep, Glob only; boundaries — Validator may read only `targets` and
     the packaged rule files.
   - Validate the return is structurally complete (every finding carries
     all four fields). If malformed, re-delegate once to the Validator
     with corrective guidance naming the missing field(s); if the retry
     is still malformed, stop and report.

5. Assemble the result
   - If the Validator returned zero findings: no checkpoint is written;
     the result is "all passed".
   - If the Validator returned one or more findings: create the marker
     file, then immediately write the checkpoint (schema: `schema_version`,
     `run_id`, `created_at`, `targets`, `language`, `findings`,
     `plain_language_report`, `status: "pending_approval"`) before any
     further step.

6. Finish
   - Return to the caller: the plain-language report, the structured
     findings list, and the checkpoint path — or "all passed" with no
     checkpoint.

## Stop Conditions

- Stop and report if `targets` is empty or unreadable.
- Never ask the user anything from within this workflow.
- Never proceed to a Formatter delegation; that belongs only to the execute
  workflow.
