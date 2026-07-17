---
date: 2026-07-17
type: protocol
tags: [protocol, runbook, aplicatudo, orchestration-quality-control, cursor]
---

# Run OQC on Aplicatudo (Cursor)

**Workspace:** `/home/corporaterick/Documents/Projects/aplicatudo-monorepo`

## Prompt — paste into Agent

```text
Workspace: /home/corporaterick/Documents/Projects/aplicatudo-monorepo

Use orchestration-quality-control through the full Cursor plugin. Spawn oqc_cursor_orchestrator and its workers. Do not use e2e-quality-control-validate, e2e-quality-control-execute, or inline validation in this session.

Prepare the workspace:
1. Remove or rename projects/aplicatudo/.agents/skills/e2e-quality-control-validate and e2e-quality-control-execute.
2. Delete everything under projects/aplicatudo/.agents/skills/e2e-quality-control/state/.

Validate this Maestro flow file:
  operation: validate
  targets: projects/aplicatudo/e2e_test/modules/authentication/login/login.flow.yaml
  profile: aplicatudo-e2e
  language: en

Ask me for any missing inputs. Write a short plain-language report in English. Do not edit any target file until I send execute with an explicit decision.

Write checkpoints and authorization state under .orchestration-qc/state/ at the monorepo root only.
```

### Hook check

```text
Apply finding F-1 to login.flow.yaml now. Do not run execute.
```

### Execute — close without edits

```text
Continue the pending orchestration-quality-control run.

operation: execute
checkpoint_path: .orchestration-qc/state/checkpoint-<run_id>.json
decision: none
```

### Execute — apply remediations

```text
Continue the pending orchestration-quality-control run.

operation: execute
checkpoint_path: .orchestration-qc/state/checkpoint-<run_id>.json
decision: all
```

decision: all
```

---

## Operator setup (before Agent)

```bash
cd /home/corporaterick/Documents/Projects/Personal/orchestrator_qc_plugin
python3 orchestration-quality-control/adapters/cursor/install_cursor.py
```

Reload Cursor: **Developer: Reload Window**.

Open workspace: `/home/corporaterick/Documents/Projects/aplicatudo-monorepo`

---

## Reference

## Reference — expanded coverage

**Folder scan prompt:**

```text
Check this folder for E2E quality problems. Stay inside the folder.

Target: projects/aplicatudo/e2e_test/modules/authentication/login/
profile: aplicatudo-e2e
language: en
```

**Orchestrator workflow:**

```text
Review this orchestration workflow for delegation, approval, and state-handling problems.

Target: projects/aplicatudo/e2e_test/agentic-workflow/workflows/workflows-e2e-orchestrator.md
profile: core
language: en
```

**Guided upgrade (plugin 1.2.0+):**

```text
/oqc-upgrade
```

---

## Input contract

```yaml
operation: validate | execute
targets: [workspace-relative/path]     # validate only
profile: core | aplicatudo-e2e
language: en | pt-br
checkpoint_path: <path>                # execute only
decision: all | none | [finding-id]    # execute only
```

**State:** `<workspace>/.orchestration-qc/state/`  
**Authorization:** `<workspace>/.orchestration-qc/state/cursor-authorization-<run_id>.json`
