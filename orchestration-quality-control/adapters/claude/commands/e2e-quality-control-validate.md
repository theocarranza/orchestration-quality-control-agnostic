---
name: e2e-quality-control-validate
description: >
  Compatibility alias for `oqc-validate` with `profile: aplicatudo-e2e`
  preselected. Kept so a user or automation still typing
  `/e2e-quality-control-validate` from the 3.0.0 command name keeps working
  without relearning a new name. Prefer `/oqc-validate` directly for new
  work; this alias may be retired in a future major version.
license: MIT
model: sonnet
effort: high
compatibility: Claude Code only. See adapters/claude/commands/oqc-validate.md.
---

# e2e-quality-control-validate (compatibility alias)

Run `oqc-validate` exactly as documented in
`adapters/claude/commands/oqc-validate.md`, with one difference: preselect
`profile: aplicatudo-e2e` instead of asking for a profile, matching the
behavior of the retired `e2e-quality-control-validate` 3.0.0 skill. Every
other step, delegation, and operating rule is unchanged.
