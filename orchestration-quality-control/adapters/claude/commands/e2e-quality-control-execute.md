---
name: e2e-quality-control-execute
description: >
  Compatibility alias for `oqc-execute`. Kept so a user or automation still
  typing `/e2e-quality-control-execute` from the 3.0.0 command name keeps
  working without relearning a new name. Prefer `/oqc-execute` directly for
  new work; this alias may be retired in a future major version.
license: MIT
model: sonnet
effort: high
compatibility: Claude Code only. See adapters/claude/commands/oqc-execute.md.
---

# e2e-quality-control-execute (compatibility alias)

Run `oqc-execute` exactly as documented in
`adapters/claude/commands/oqc-execute.md`. No behavior differs from the
non-alias command — the checkpoint itself already records which profile
produced its findings, so nothing needs to be preselected here.
