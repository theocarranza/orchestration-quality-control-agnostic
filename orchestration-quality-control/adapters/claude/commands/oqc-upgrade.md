---
name: oqc-upgrade
description: >
  Guided orchestration upgrade. Infers mechanism path and packaged profile,
  language, side-by-side paths, and auto-approve decision; delegates to the
  oqc-upgrade-orchestrator subagent for upgrade_prepare then upgrade_apply in
  one turn. Use whenever the user runs `/oqc-upgrade` or asks to upgrade,
  redesign, version, normalize, or template an orchestration mechanism.
license: MIT
model: sonnet
effort: high
compatibility: >
  Claude Code only. Delegates to the oqc-upgrade-orchestrator subagent. See
  adapters/claude/README.md.
---

# oqc-upgrade

This skill is the main-session half of guided-upgrade operations. It never
drafts proposals itself. It resolves packaged defaults, delegates prepare and
apply without manifest or atomic approval questions.

Follow @references/workflows/workflows-root-session-interview.md.

## Steps

1. Run `scripts/discover_workspace.py` when `mechanism_path` is not explicit.
2. Resolve inputs without UI questions via
   `scripts/gate_defaults.py upgrade-fields` unless the invocation names
   overrides. Packaged defaults include side-by-side apply, manifest confirm,
   and `decision: approve`.
3. Run `scripts/discover_structure.py` for visibility; do **not** ask manifest
   confirmation — continue with the discovered manifest.
4. Delegate prepare to `oqc-upgrade-orchestrator` (`operation: upgrade_prepare`).
5. Present report and preview for visibility. Delegate apply with packaged
   `decision: approve` in the same turn unless prepare returned `blocked`.
6. Present application outcomes.

## Operating rules

- Never call `Edit` or `Write` on a target or proposed destination yourself.
- `template_id` remains `isolated-three-agent` and is not asked.
