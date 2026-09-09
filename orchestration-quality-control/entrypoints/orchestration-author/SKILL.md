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

1. Resolve the installed canonical skill root as
   `../orchestration-quality-control/` relative to this entrypoint's installed
   directory. Use that sibling root for all packaged workflows, rules, schemas,
   and scripts; do not resolve them from this entrypoint's own directory. Stop with
   `adapter_not_installed` if the sibling root or its required files are
   unavailable.
2. Follow `../orchestration-quality-control/references/workflows/workflows-root-session-interview.md`.
3. Run `../orchestration-quality-control/scripts/discover_workspace.py` then
   `../orchestration-quality-control/scripts/plan_interview.py`.
4. Ask **outcome** only in the root session. Confirm packaged defaults (accept
   or update), then delegate prepare/apply with packaged `decision: approve`.
5. Never write `output_root` from the root session.
