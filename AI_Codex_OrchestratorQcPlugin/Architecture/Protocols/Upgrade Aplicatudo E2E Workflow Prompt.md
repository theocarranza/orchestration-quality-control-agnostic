---
date: 2026-07-17
type: protocol
tags: [protocol, prompt, aplicatudo, oqc-upgrade, isolated-three-agent]
---

# Upgrade Aplicatudo E2E Workflow Prompt

Paste into Cursor Agent with workspace root
`/home/corporaterick/Documents/Projects/aplicatudo-monorepo`.

```text
Workspace: /home/corporaterick/Documents/Projects/aplicatudo-monorepo

Modernize the Aplicatudo end-to-end agent orchestration with the installed
orchestration-quality-control plugin upgrade flow (/oqc-upgrade).

Use the full Cursor plugin only. Spawn oqc_cursor_upgrade_orchestrator and its
workers. Do not use e2e-quality-control-validate, e2e-quality-control-execute,
or ordinary validate/execute for this run.

Prepare first:
1. Remove or rename projects/aplicatudo/.agents/skills/e2e-quality-control-validate
   and e2e-quality-control-execute so they are not discovered.
2. Delete anything under projects/aplicatudo/.agents/skills/e2e-quality-control/state/.

Upgrade inputs:
  operation: upgrade_prepare
  mechanism_path: projects/aplicatudo/e2e_test/agentic-workflow
  profile: core
  language: en
  template_id: isolated-three-agent
  apply_mode: in-place
  documentation_path: projects/aplicatudo/e2e_test/agentic-workflow/ARCHITECTURE.md

Ask me only for missing required inputs, discovery confirmation, and the final
approve or decline of the complete proposal. Present a short plain-language
report and the literal preview before any apply.

Do not edit target files from the root session. After I approve or decline,
run upgrade_apply with that exact decision. Write checkpoints and authorization
state under .orchestration-qc/state/ at the monorepo root only.
```
