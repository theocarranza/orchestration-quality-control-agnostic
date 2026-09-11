---
name: oqc-author
description: >
  Greenfield orchestration authoring. Audits the workspace, asks only for the
  orchestration outcome in the root session, confirms packaged defaults, drafts
  process documents, runs internal QC, then auto-applies into an empty folder.
  Use whenever the user runs `/oqc-author` or asks to author, write, or
  generate a new workflow, rules file, or orchestrator. Do not use this command
  to upgrade an existing host mechanism — that is `oqc-upgrade`.
license: MIT
model: sonnet
effort: high
compatibility: >
  Claude Code only. Delegates to the oqc-upgrade-orchestrator subagent for
  author_prepare and author_apply. See adapters/claude/README.md.
---

# oqc-author

This skill is the main-session half of greenfield authoring. It never drafts or
writes process documents itself. It audits, asks only for **outcome** in the
root session, confirms packaged defaults, delegates, and auto-continues apply.

Follow @references/workflows/workflows-root-session-interview.md.

## Steps

1. Run `scripts/discover_workspace.py` with the workspace. On `blocked`, stop
   and show the payload.
2. Run `scripts/plan_interview.py` with that brief JSON.
3. Ask via UI in the **root session only** (never inside a subagent):
   - `outcome`: what this new orchestration should achieve. This is the only
     field without a packaged default.
4. Run `scripts/gate_defaults.py author-fields` with the brief. Present
   `defaults_confirmation` from the plan or script output. Offer:
   - accept packaged defaults and continue, or
   - update one or more named fields, then continue.
5. Delegate prepare to `oqc-upgrade-orchestrator` (`operation: author_prepare`)
   with `outcome`, merged defaults, and `intent: author`.
6. Present the report and preview for visibility. Do **not** ask approve /
   decline — packaged default is `decision: approve`. Delegate apply
   (`operation: author_apply`) in the same turn unless prepare returned
   `blocked`.
7. Present application outcomes.

## Operating rules

- Never call `Edit` or `Write` on `output_root` yourself.
- Never ask stack, layout, or whether tests exist — those are in the brief.
- Never delegate the outcome question or defaults confirmation to a subagent.
- If prepare returns without `checkpoint_path`, stop.
