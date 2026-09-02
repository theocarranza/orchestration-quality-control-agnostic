---
description: Audit, interview gaps, draft process documents, and checkpoint after internal QC
---

# Workflow: Greenfield Author — Prepare

## Inputs

- Complete interview answers: `outcome`, `output_root`, and any fields
  `plan_interview.py` listed under `ask`. Skipped fields arrive as the
  brief defaults. `intent` must be `author` when a fork was offered.

## Control

- Primary agent: guided-upgrade Orchestrator (authoring reuse).
- Decision model: deterministic audit/interview plan/checkpoint; model
  judgment for drafting and internal QC.
- Delegation: Proposal Author, then Validator. One Author rewrite on QC
  failure.

## Steps

1. Load @../rules/rules-upgrade-orchestrator.md.
2. Confirm no checkpoint is pending (`checkpoint_state.py is-run-active`).
3. Re-run `discover_workspace.py` and `plan_interview.py`. If the caller
   asked a field listed in `never_ask` or a skipped field except via the
   confirmation list, stop with `blocked`.
4. If `intent` is `upgrade`, stop and tell the root to run upgrade.
5. Confirm `output_root` is missing or empty.
6. Delegate outcome, brief, skipped defaults, and remaining answers to
   Proposal Author under @../rules/rules-proposal-author.md. Require
   `author-proposal.schema.json`. Retry malformed output once.
7. Materialize `files` under `.orchestration-qc/preview/<run_id>/`.
8. Delegate those paths to Validator with the selected `profile`. Require
   `all_passed`. On findings, return them to Proposal Author once. A
   second failure is `blocked`.
9. Run `author_state.py create` with the brief, empty findings, preview
   directory, and report.
10. Return the report, preview, and checkpoint path. Do not apply.

## Stop Conditions

- Stop on audit failure, non-empty `output_root`, concurrent run, upgrade
  intent, or QC failure after one rewrite.
- Never write `output_root` in this workflow.
