---
name: oqc-upgrade
description: >
  Guided, approval-gated modernization of an existing agent orchestration.
  Discovers and confirms the mechanism, runs orchestration quality control,
  compares it with either the portable single-agent or isolated three-agent
  OQC reference architecture, drafts a complete version plus ARCHITECTURE.md
  diagrams, presents literal changes, applies only an atomic approval, and
  verifies the result. Use when the user runs `/oqc-upgrade` or asks to
  upgrade, redesign, version, normalize, or template an orchestration
  mechanism.
license: MIT
---

# oqc-upgrade

This is the Cursor entry point for guided-upgrade operations. It delegates to
the installed `orchestration-quality-control` skill and the bundled
`oqc_cursor_upgrade_orchestrator` subagent.

1. Locate the installed `orchestration-quality-control` skill root from this
   plugin. Stop with `adapter_not_installed` if it is unavailable.
2. Read its `SKILL.md`, then follow `workflows-upgrade-prepare.md` for a new
   run or `workflows-upgrade-apply.md` for a pending checkpoint.
3. The root session owns all UI: mechanism path, manifest confirmation,
   profile/language, template, apply mode/paths, isolation reason, and atomic
   approve/decline decision.
4. Never write a target or proposed destination from the root session. Spawn
   exactly one `oqc_cursor_upgrade_orchestrator` and return its structured
   result.
