---
name: oqc-author
description: >
  Greenfield orchestration authoring. Audits the workspace, interviews only
  unresolved orchestration choices, drafts process documents, runs internal
  QC, then applies into an empty folder after atomic approval. Use whenever
  the user runs `/oqc-author` or asks to author, write, or generate a new
  workflow, rules file, or orchestrator. Do not use this command to upgrade
  an existing host mechanism — that is `oqc-upgrade`.
license: MIT
model: sonnet
effort: high
compatibility: >
  Claude Code only. Delegates to the oqc-upgrade-orchestrator subagent for
  author_prepare and author_apply. See adapters/claude/README.md.
---

# oqc-author

This skill is the main-session half of greenfield authoring. It never
drafts or writes process documents itself. It audits, asks only the
planned questions, delegates, presents the preview, and records the
atomic approval.

## Steps

1. Run `scripts/discover_workspace.py` with the workspace. On `blocked`,
   stop and show the payload.
2. Run `scripts/plan_interview.py` with that brief JSON.
3. If `fork` is `author_vs_upgrade`, ask via UI: author a new tree, or
   upgrade what is already there. On upgrade, stop and point at
   `/oqc-upgrade`.
4. Ask via UI, one field at a time, every `always_ask` and `ask` field.
   Do not ask `never_ask` fields or skipped fields except as an optional
   final confirmation list of defaults.
5. Delegate prepare to `oqc-upgrade-orchestrator` (`operation:
   author_prepare`) with the brief, interview answers, and `intent:
   author`.
6. Present the report and preview. Ask approve / decline.
7. Delegate apply (`operation: author_apply`) with the checkpoint and
   decision. Present outcomes.

## Operating rules

- Never call `Edit` or `Write` on `output_root` yourself.
- Never ask stack, layout, or whether tests exist — those are in the brief.
- If prepare returns without `checkpoint_path`, stop.
