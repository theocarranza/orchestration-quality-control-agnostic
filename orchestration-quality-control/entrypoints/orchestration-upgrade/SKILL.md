---
name: orchestration-upgrade
description: >
  Guided modernization of an existing agent orchestration. Uses packaged
  defaults for mechanism path, profile, language, side-by-side output, manifest
  confirm, and auto-approve; applies only after internal QC passes. Use when
  the user asks to upgrade, redesign, version, normalize, or template an
  orchestration mechanism.
license: MIT
---

# Orchestration Upgrade

Explicit host entry for guided-upgrade operations in the sibling
`orchestration-quality-control` skill.

1. Locate the installed skill root. Stop with `adapter_not_installed` if
   unavailable.
2. Follow `references/workflows/workflows-root-session-interview.md`.
3. Resolve inputs with `gate_defaults.py upgrade-fields` unless the invocation
   overrides them. Do not ask manifest confirmation or atomic approval.
4. Delegate prepare then apply with packaged `decision: approve` unless
   `blocked`.
5. Never write targets from the root session.
