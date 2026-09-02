---
description: Behavior rules for applying one approved guided-upgrade proposal
alwaysApply: false
---

# Rule: Guided Upgrade Applier Behavior

## Requirements

- Accept only a pending upgrade checkpoint (schema-version 3) or author
  checkpoint (schema-version 1) with an explicit `approve` decision.
- Invoke `scripts/apply_upgrade.py` once for upgrade, or
  `scripts/apply_author.py` once for author; never edit a target directly.
- Return the script's structured result unchanged.

## Boundaries

- Do not author, reinterpret, subset, or expand the proposal.
- Do not use any shell command other than the deterministic apply script.
- Do not retry a blocked application without returning control to Orchestrator.
