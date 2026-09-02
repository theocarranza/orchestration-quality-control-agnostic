---
name: orchestration-author
description: >
  Greenfield, approval-gated authoring of process documents (workflow,
  rules, optional orchestrator, ARCHITECTURE.md). Audits the workspace,
  interviews only gaps, internally quality-controls the draft, and writes
  nothing until an atomic approve. Use when the user asks to author, write,
  or generate a new agentic process rather than check or upgrade an
  existing one.
license: MIT
---

# Orchestration Author

This is the explicit host entry point for the authoring operations in the
sibling `orchestration-quality-control` skill.

1. Locate the installed `orchestration-quality-control` skill root. Stop
   with `adapter_not_installed` if it is unavailable.
2. Run `discover_workspace.py` then `plan_interview.py`. Ask only the
   planned questions. If the fork is upgrade, stop and run upgrade.
3. Follow `workflows-author-prepare.md` then `workflows-author-apply.md`.
4. The root session owns every UI question and the atomic decision.
5. Never write `output_root` from the root session. Use the installed
   host's guided-upgrade Orchestrator with `author_prepare` /
   `author_apply`.
