---
name: oqc-upgrade
description: >
  Guided modernization of an existing agent orchestration. Uses packaged
  defaults for paths, profile, language, manifest confirm, and auto-approve;
  delegates to the upgrade orchestrator for prepare then apply in one turn.
  Use when the user runs `/oqc-upgrade` or asks to upgrade, redesign, version,
  normalize, or template an orchestration mechanism.
license: MIT
---

# oqc-upgrade

Cursor entry point for guided-upgrade operations. Follow
`references/workflows/workflows-root-session-interview.md` in the installed
skill root.

1. Locate the installed `orchestration-quality-control` skill root. Stop with
   `adapter_not_installed` if unavailable.
2. Resolve inputs with `gate_defaults.py upgrade-fields` unless the invocation
   names overrides. Do not ask manifest confirmation or atomic approval.
3. Spawn exactly one `oqc_cursor_upgrade_orchestrator` for prepare, then apply
   with packaged `decision: approve` in the same turn unless `blocked`.
4. Never write a target or proposed destination from the root session.
