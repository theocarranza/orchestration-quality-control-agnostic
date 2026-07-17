---
description: Discover, validate, and checkpoint a complete orchestration replacement for atomic approval
---

# Workflow: Guided Upgrade — Prepare

## Inputs

- `mechanism_path`, `profile`, `language`, `template_id`, `apply_mode`,
  `documentation_path`; plus `output_root` for side-by-side mode.

## Control

- Primary agent: guided-upgrade Orchestrator.
- Decision model: deterministic discovery/checkpoint rendering; model judgment
  for semantic QC, template gaps, and proposal authorship.
- Delegation: Validator, then Proposal Author. Each exists because read-only
  judgment and artifact authorship require incompatible responsibilities.

## Steps

1. Load the operating contract
   - OBEY @../rules/rules-upgrade-orchestrator.md.
2. Establish the target
   - Confirm no checkpoint is pending.
   - Run `discover_structure.py`; return the manifest to the root for explicit
     confirmation before continuing.
3. Validate the mechanism
   - Delegate the confirmed candidates to Validator using its ordinary QC
     contract plus @../rules/rules-reference-architecture-quality-control.md.
   - Require ordinary findings, template gaps, and a report. Retry malformed
     output once, then stop.
4. Draft the proposal
   - Delegate frozen snapshots, structured results, paths, and selected template
     to Proposal Author under @../rules/rules-proposal-author.md.
   - Require `upgrade-proposal.schema.json`; retry malformed output once.
5. Checkpoint and preview
   - Run `upgrade_state.py create`, which validates paths, hashes, mode rules,
     documentation presence, and literal diffs.
6. Finish
   - Return the report, preview, manifest, and checkpoint path to the root.

## Stop Conditions

- Stop on unconfirmed discovery, ambiguity, path escape, safety cap, collision,
  stale input, malformed output after one retry, or another pending run.
- Never apply or ask for approval in this workflow.
