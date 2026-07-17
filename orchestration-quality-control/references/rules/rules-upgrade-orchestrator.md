---
description: Behavior rules for the guided-upgrade orchestrator
alwaysApply: false
---

# Rule: Guided Upgrade Orchestrator Behavior

## Requirements

- Accept only complete `upgrade_prepare` or `upgrade_apply` inputs.
- Never ask the user; the root command owns every UI question and decision.
- Never read or edit target content directly.
- Use deterministic scripts for discovery, proposal validation, checkpoint
  transitions, exact application, and verification persistence.
- Delegate target judgment to Validator, proposal authorship to Proposal Author,
  and approved application to Upgrade Applier.
- Validate each worker return and retry malformed output at most once.
- Keep the selected template, manifest hashes, findings, gaps, proposal, and
  literal preview in the checkpoint before returning for approval.
- After application, delegate the same QC and template checks against the
  effective output; preserve failures in a verification record.

## Boundaries

- Do not choose a template, output path, or apply mode.
- Do not continue from prepare to apply without a caller-supplied decision.
- Do not request a silent repair or rollback after post-apply QC.

## Output

- Prepare: confirmed manifest, report, literal preview, and checkpoint path.
- Apply: declined result, or application outcomes plus verification result.
