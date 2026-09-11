# Antigravity (AGY) adapter execution

This installed Antigravity (AGY) edition uses the host-specific nested topology below.
This nested topology is the only shipped execution shape:

```text
root AGY session
└── oqc_agy_orchestrator
    ├── oqc_agy_validator
    └── oqc_agy_remediator
```

For `validate` or `execute`:

1. Confirm that the required AGY subagents or skill entrypoints are available from the
   installed plugin.
2. If any required subagent is unavailable, return a `blocked` result with
   `stage: agy_adapter` and reason code `adapter_not_installed`. Do not run
   the checks in a single agent.
3. Spawn exactly one `oqc_agy_orchestrator` (using `invoke_subagent` or `define_subagent`)
   with the absolute path of this installed skill directory and the complete input contract.
4. Wait for the orchestrator and return its structured result without
   re-reading targets or applying edits in the root session.

The orchestrator owns routing, deterministic checkpoints, decision
reconciliation, authorization creation, and worker coordination. The
validator is strictly read-only (`enable_write_tools: false`). The remediator applies
only the approved literal changes (`replace_file_content`). The Antigravity lifecycle
hook (`PreToolUse`) separately denies protected edits that are not exact
authorized changes.

For `upgrade_prepare` or `upgrade_apply`, invoke exactly one
`oqc_agy_upgrade_orchestrator`. For `author_prepare` or `author_apply`,
invoke the same orchestrator with the author workflows. It coordinates the
existing Validator, `oqc_agy_proposal_author`, and
`oqc_agy_upgrade_applier`.

## Root session UI

Follow `references/workflows/workflows-root-session-interview.md`. The root
AGY session owns the human interview: **outcome**, targets, profile, language, and apply decision.
Use `ask_question` in the root session only — never inside a nested subagent. Present packaged
defaults for every former gate; the user accepts or updates them, then
the run auto-continues (including apply) unless a script returns `blocked`.
