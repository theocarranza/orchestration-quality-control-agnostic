---
name: oqc-execute
description: >
  Execute operation of orchestration quality control. Given a checkpoint
  reference, uses packaged apply-all when no decision was supplied, delegates
  to the oqc-orchestrator subagent (operation: execute), and closes the run.
  Use whenever the user runs `/oqc-execute` or references a prior checkpoint.
  Do not use this skill to run a fresh check — that is `oqc-validate`.
license: MIT
model: sonnet
effort: high
compatibility: >
  Claude Code only. Delegates to the oqc-orchestrator subagent. See
  adapters/claude/README.md.
---

# oqc-execute

This skill is the main-session half of the execute operation. It never edits
targets itself. When `decision` is omitted, it uses the packaged default
`all` after re-presenting the checkpoint report for visibility.

Follow @references/workflows/workflows-root-session-interview.md.

## Steps

1. If `decision` is already given (e.g. hand-off from `oqc-validate`), skip to
   step 3.
2. Standalone invocation:
   - Read the checkpoint and verify `pending_approval`.
   - Present `plain_language_report` for visibility.
   - Set `decision` to packaged default `all`. Do **not** ask apply choice.

3. Delegate to `oqc-orchestrator` (`operation: execute`) with `checkpoint_path`
   and `decision`.

4. Present the final report.

## Operating rules

- Never call `Edit` on a target file yourself.
- Never ask apply choice when resuming unless the user explicitly overrides the
  packaged default in the invocation.
