---
name: oqc-author
description: >
  Greenfield, approval-gated authoring of process documents. Audits the
  workspace, interviews only gaps, quality-controls the draft, and writes
  into an empty folder only after atomic approval. Use when the user runs
  `/oqc-author` or asks to author a new workflow, rules file, or
  orchestrator.
license: MIT
---

# oqc-author

This is the Cursor entry point for greenfield authoring. It delegates to
the installed `orchestration-quality-control` skill and the bundled
`oqc_cursor_upgrade_orchestrator` subagent.

1. Locate the installed `orchestration-quality-control` skill root from
   this plugin. Stop with `adapter_not_installed` if it is unavailable.
2. Run `discover_workspace.py` then `plan_interview.py`. Ask only the
   planned questions.
3. Follow `workflows-author-prepare.md` or `workflows-author-apply.md`.
4. The root session owns all UI. Never write `output_root` from the root
   session. Spawn exactly one `oqc_cursor_upgrade_orchestrator`.
