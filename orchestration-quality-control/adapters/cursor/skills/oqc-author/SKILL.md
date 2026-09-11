---
name: oqc-author
description: >
  Greenfield authoring of process documents. Audits the workspace, asks only
  for orchestration outcome in the root Cursor session, confirms packaged
  defaults, quality-controls the draft, and auto-applies into an empty folder.
  Use when the user runs `/oqc-author` or asks to author a new workflow,
  rules file, or orchestrator.
license: MIT
---

# oqc-author

Cursor entry point for greenfield authoring. Follow
`references/workflows/workflows-root-session-interview.md` in the installed
skill root.

1. Locate the installed `orchestration-quality-control` skill root. Stop with
   `adapter_not_installed` if unavailable.
2. Run `discover_workspace.py` then `plan_interview.py`.
3. In the **root Cursor session only**, use `AskQuestion` for `outcome` — the
   only field without a packaged default. Never spawn a subagent before this
   answer exists; nested Task chats cannot surface questions to the parent.
4. Run `gate_defaults.py author-fields`. Present `defaults_confirmation`. Offer
   accept packaged defaults or update named fields.
5. Spawn exactly one `oqc_cursor_upgrade_orchestrator` with merged inputs and
   packaged `decision: approve` for apply. Do not ask approve/decline.
6. Never write `output_root` from the root session.
