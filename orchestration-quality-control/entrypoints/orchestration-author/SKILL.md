---
name: orchestration-author
description: >
  Greenfield authoring of process documents (workflow, rules, optional
  orchestrator, ARCHITECTURE.md). Audits the workspace, asks only for outcome
  in the root session, confirms packaged defaults, internally quality-controls
  the draft, and auto-applies into an empty folder. Use when the user asks to
  author, write, or generate a new agentic process rather than check or
  upgrade an existing one.
license: MIT
---

# Orchestration Author

Explicit host entry for authoring operations in the sibling
`orchestration-quality-control` skill.

1. Locate the installed skill root. Stop with `adapter_not_installed` if
   unavailable.
2. Follow `references/workflows/workflows-root-session-interview.md`.
3. Run `discover_workspace.py` then `plan_interview.py`.
4. Ask **outcome** only in the root session. Confirm packaged defaults (accept
   or update), then delegate prepare/apply with packaged `decision: approve`.
5. Never write `output_root` from the root session.
