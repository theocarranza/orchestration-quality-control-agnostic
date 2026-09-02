---
description: Root-session UI for the one remaining human gate and packaged defaults confirmation
---

# Workflow: Root session interview

## Scope

This workflow applies to every host adapter whose **root session** invokes
orchestration-quality-control. Nested subagents (`oqc_cursor_orchestrator`,
`oqc_cursor_upgrade_orchestrator`, validators, remediators, proposal authors)
must **never** call a question UI. They receive complete inputs only.

## The one kept gate

| Gate id | Field | Where asked |
| --- | --- | --- |
| `author-outcome` | What this new orchestration should achieve | Root session only, before any subagent spawn |

Use the host question UI (`AskQuestion` on Cursor) in the **root** chat. Do not
delegate this question to a Task subagent — Cursor does not bubble subagent
questions to the parent.

## Author operation sequence

1. Run `discover_workspace.py`.
2. Run `plan_interview.py`. Expect `always_ask: ["outcome"]` only.
3. Ask **outcome** in the root session (required; no packaged default).
4. Run `gate_defaults.py author-fields` (or merge in-session) to build packaged
   defaults from the brief.
5. Present `defaults_confirmation` from the plan. Offer:
   - **Accept packaged defaults and continue** — proceed with listed values.
   - **Update defaults** — collect overrides for named fields only, then merge.
6. Spawn exactly one upgrade orchestrator with `author_prepare` and the merged
   input. Pass `decision: approve` for apply — the write gate is auto-continue.
7. Do not re-ask apply in the root unless a `blocked` payload names an
   unforeseen serious event.

## Validate operation sequence

1. Infer targets with `gate_defaults.py infer-validate-targets` from invocation
   paths, `.orchestration-qc/defaults.json`, or `brief.existing_orchestration`.
2. Use packaged profile, language, and `decision: all`. Do not stop for apply.
3. Delegate validate then execute in one turn with the packaged decision.

## Upgrade operation sequence

1. Infer or read `mechanism_path` from invocation or brief; use packaged
   profile, language, side-by-side paths, manifest confirm, and
   `decision: approve`.
2. Do not stop for manifest confirmation or atomic apply unless `blocked`.

## Execute resume

When resuming a pending checkpoint without a known decision, use packaged
`decision: all`. Re-present the report for visibility; do not wait for a new
apply choice unless the host detects an extraordinary conflict.

## Stop only for the extraordinary

After defaults are accepted, the run continues without further questions unless:

- A deterministic script returns `blocked`.
- Targets or paths cannot be inferred safely.
- A concurrent `pending_approval` checkpoint exists.
- The user explicitly interrupts.
