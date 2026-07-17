---
name: orchestration-upgrade
description: >
  Guided, approval-gated modernization of an existing agent orchestration.
  Discovers and confirms the mechanism, runs orchestration quality control,
  compares it with either the portable single-agent or isolated three-agent
  OQC reference architecture, drafts a complete version plus ARCHITECTURE.md
  diagrams, presents literal changes, applies only an atomic approval, and
  verifies the result. Use when the user asks to upgrade, redesign, version,
  normalize, or template an orchestration mechanism.
license: MIT
---

# Orchestration Upgrade

This is the explicit host entry point for the guided-upgrade operations in the
sibling `orchestration-quality-control` skill.

1. Locate the installed `orchestration-quality-control` skill root. Stop with
   `adapter_not_installed` if it is unavailable.
2. Read its `SKILL.md`, then follow `workflows-upgrade-prepare.md` for a new
   run or `workflows-upgrade-apply.md` for a pending checkpoint.
3. The root session owns all UI: mechanism path, manifest confirmation,
   profile/language, template, apply mode/paths, isolation reason, and atomic
   approve/decline decision.
4. Never write a target or proposed destination from the root session. Use the
   installed host's guided-upgrade Orchestrator and return its structured
   result.
