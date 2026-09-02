---
name: oqc-validate
description: >
  Validate operation of orchestration quality control. Infers targets and uses
  packaged profile, language, and apply-all decision, delegates to the
  oqc-orchestrator subagent (operation: validate), presents the plain-language
  findings report, and hands off to oqc-execute in the same turn without asking
  for apply choice. Use whenever the user runs `/oqc-validate`, asks for
  orchestration quality control, or wants to check a workflow, orchestrator,
  rules, or generator-source document. Do not use this skill to apply fixes to
  an existing checkpoint without a fresh validate — that is `oqc-execute`.
license: MIT
model: sonnet
effort: high
compatibility: >
  Claude Code only. Delegates to the oqc-orchestrator subagent. See
  adapters/claude/README.md.
---

# oqc-validate

This skill is the main-session half of the validate operation. It never reads
target content itself. It infers inputs from the invocation and packaged
defaults, delegates, presents results, and auto-continues with apply-all.

Follow @references/workflows/workflows-root-session-interview.md.

## Steps

1. Run `scripts/discover_workspace.py` when targets are not explicit in the
   invocation.
2. Resolve inputs without UI questions:
   - `targets`: paths named in the invocation, else
     `scripts/gate_defaults.py infer-validate-targets`, else
     `.orchestration-qc/defaults.json`.
   - `profile`, `language`: from `scripts/gate_defaults.py validate-fields`.
   - `decision`: packaged default `all` (do not ask).

2. Delegate to the `oqc-orchestrator` subagent (`operation: validate`) with the
   resolved inputs. Boundaries: it must not ask the user anything.

3. Handle the return:
   - `all_passed` → report and stop.
   - `report` + `findings` + `checkpoint_path` → present the report, then hand
     off to execute with `decision: all` in the same turn without asking.
   - `blocked` → relay verbatim.

4. Invoke `oqc-execute` with the checkpoint and `decision: all`. Present its
   return.

## Operating rules

- Never call `Edit` or `Write` on a target file yourself.
- Never ask profile, language, targets, or apply choice when packaged defaults
  or inference succeed.
