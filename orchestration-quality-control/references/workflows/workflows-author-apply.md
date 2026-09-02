---
description: Resolve an atomic authoring decision and write the preview into an empty output_root
---

# Workflow: Greenfield Author — Apply

## Inputs

- `checkpoint_path`: pending schema-version 1 author checkpoint.
- `decision`: caller-supplied `approve` or `decline`.

## Control

- Primary agent: guided-upgrade Orchestrator (authoring reuse).
- Decision model: deterministic state transition and application.
- Delegation: Upgrade Applier for approved writes.

## Steps

1. Load @../rules/rules-upgrade-orchestrator.md.
2. Run `author_state.py decide` with the exact caller decision.
3. On decline, return the aborted result without delegation.
4. On approve, delegate the checkpoint to Upgrade Applier under
   @../rules/rules-upgrade-applier.md.
5. Return application outcomes. Do not invent a post-apply rewrite.

## Stop Conditions

- Stop on missing approval, non-empty `output_root`, path escape, or a
  blocked apply.
- Never write files except through `apply_author.py`.
