---
date: 2026-07-17
type: report
tags: [report, deployment, aplicatudo, orchestration-quality-control, cursor, aplicatudo-e2e]
---

# First deployment plan — OQC full plugin on Aplicatudo monorepo

## Objective

Validate the extracted Orchestration Quality Control plugin in a real workspace: the Aplicatudo monorepo, using Cursor, the `aplicatudo-e2e` profile, and the full nested adapter (orchestrator, validator, remediator, approval hook).

This closes the live-session portion of definition-of-done work — exercising validate → approval gate → execute against production-adjacent artifacts, not fixtures alone.

## Target environment

| Item | Value |
| --- | --- |
| Repository | `/home/corporaterick/Documents/Projects/aplicatudo-monorepo` |
| Host | Cursor with local plugins enabled |
| Install scope | User-level plugin at `~/.cursor/plugins/local/orchestration-quality-control` |
| First artifact | `projects/aplicatudo/e2e_test/modules/authentication/login/login.flow.yaml` |
| First profile | `aplicatudo-e2e` |

## Context — what is being replaced

The monorepo still carries the retired v3 skill split:

- `projects/aplicatudo/.agents/skills/e2e-quality-control/` — shared library, no invocable `SKILL.md`
- `e2e-quality-control-validate/` and `e2e-quality-control-execute/` — separate entry points

That design runs validation inside the root session with no hook shield. Runtime state from that era remains at `projects/aplicatudo/.agents/skills/e2e-quality-control/state/` (including a checkpoint from 2026-07-15). OQC uses a separate state root: `<workspace>/.orchestration-qc/state/`.

The OQC plugin introduces nested delegation and hook enforcement:

```text
Cursor root session
└── oqc_cursor_orchestrator
    ├── oqc_cursor_validator   (readonly)
    └── oqc_cursor_remediator  (literal approved changes only)
```

Full-plugin install is mandatory for this deployment. Skill-only distribution would omit the topology and hook layer that the deployment is meant to prove.

## Prerequisites

1. **Plugin build current** — marketplace version 1.2.0+ (older 1.1.0 installs lack `oqc-upgrade` and upgrade orchestrator agents).
2. **Legacy skills retired** — remove or rename `e2e-quality-control-validate` and `e2e-quality-control-execute` from skill discovery so the agent does not invoke the old path.
3. **Stale state cleared** — archive or delete legacy checkpoint files under the old skill tree.
4. **Workspace root** — open the monorepo root, not a subdirectory, so hooks resolve checkpoints correctly.

## Scope

### In scope

- Install or refresh the Cursor plugin from `orchestrator_qc_plugin`
- Validate a single Maestro flow file (`login.flow.yaml`) with `aplicatudo-e2e`
- Confirm the hook denies unapproved edits during `pending_approval`
- Execute with `decision: none`, then with a real approval subset
- Expand to folder scan and orchestrator workflow review after first success

### Out of scope (this deployment)

- Codex adapter installation
- Guided upgrade (`/oqc-upgrade`) unless explicitly scheduled after core validate/execute succeeds
- Removing the legacy `e2e-quality-control/` reference library (optional cleanup)

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Stale 1.1.0 plugin install | Re-run `install_cursor.py`; verify manifest version and subagent files |
| Agent invokes legacy validate skill | Retire legacy skill directories before first prompt |
| Legacy checkpoint confuses operators | Delete old state under `e2e-quality-control/state/` |
| Root session edits target inline | Restate prompt; confirm skill overlay spawns orchestrator |
| Hook not loaded | Reload Cursor window after install |

## Success criteria

| # | Criterion |
| --- | --- |
| 1 | Plugin 1.2.0+ installed; three QC subagents discoverable |
| 2 | `validate` on `login.flow.yaml` produces structured findings and plain report |
| 3 | Hook blocks unapproved target edits while checkpoint is pending |
| 4 | `execute` with `decision: none` closes checkpoint without file mutation |
| 5 | `execute` with approved subset applies only literal authorized diffs |
| 6 | Legacy validate/execute skills no longer in discovery path |
| 7 | Folder scan and orchestrator workflow validate complete (stretch) |

## Execution

- Validate / execute runbook: `Architecture/Protocols/Run OQC on Aplicatudo Cursor.md`
- Guided upgrade prompt (isolated three-agent, in-place): `Architecture/Protocols/Upgrade Aplicatudo E2E Workflow Prompt.md`

## Related work

- Standards and packaging analysis: `Agent_Reports/2026-07-17-agent-skills-standards-analysis.md`
- Eval benchmark parity (automated): `Agent_Reports/2026-07-17-eval-parity-next-step.md`
- Definition of done: `docs/adr/0005-definition-of-done.md`
