---
description: Resolve an atomic upgrade decision, apply the exact approved proposal, and verify the result
---

# Workflow: Guided Upgrade — Apply

## Inputs

- `checkpoint_path`: pending schema-version 3 upgrade checkpoint.
- `decision`: caller-supplied `approve` or `decline`.

## Control

- Primary agent: guided-upgrade Orchestrator.
- Decision model: deterministic state transition and application; model judgment
  only in the post-apply Validator pass.
- Delegation: Upgrade Applier for approved mutation, Validator for verification.

## Steps

1. Load the operating contract
   - OBEY @../rules/rules-upgrade-orchestrator.md.
2. Resolve the decision
   - Run `upgrade_state.py decide` with the exact caller decision.
   - On decline, return the aborted result without delegation.
3. Apply the proposal
   - On approve, delegate only `checkpoint_path` and workspace to Upgrade
     Applier under @../rules/rules-upgrade-applier.md.
   - Require status `consumed` and one outcome per action.
4. Verify
   - Delegate the effective output to Validator using the original profile and
     selected reference-template rule.
   - Run `upgrade_state.py verify` with the returned findings, gaps, and report.
5. Finish
   - Return application outcomes and verification status/path. Preserve an
     applied version even when verification fails.

## Stop Conditions

- Stop on missing approval, stale hashes, destination collision, path escape,
  failed application, or malformed verification output after one retry.
- Never auto-repair or roll back merely because post-apply QC reports defects.
