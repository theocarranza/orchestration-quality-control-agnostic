## Cursor adapter execution

This installed Cursor edition uses the host-specific nested topology below.
This nested topology is the only shipped execution shape:

```text
root Cursor session
└── oqc_cursor_orchestrator
    ├── oqc_cursor_validator
    └── oqc_cursor_remediator
```

For `validate` or `execute`:

1. Confirm that the three named Cursor subagents are available from the
   installed plugin.
2. If any required subagent is unavailable, return a `blocked` result with
   `stage: cursor_adapter` and reason code `adapter_not_installed`. Do not run
   the checks in a single agent.
3. Spawn exactly one `oqc_cursor_orchestrator` with the absolute path of this
   installed skill directory and the complete input contract.
4. Wait for the orchestrator and return its structured result without
   re-reading targets or applying edits in the root session.

The orchestrator owns routing, deterministic checkpoints, decision
reconciliation, authorization creation, and worker coordination. The
validator is read-only. The remediator applies only the approved literal
changes. The Cursor hook separately denies protected edits that are not exact
authorized changes. The hook can prove approval integrity, but it cannot prove
which agent submitted an authorized change.

For `upgrade_prepare` or `upgrade_apply`, invoke exactly one
`oqc_cursor_upgrade_orchestrator`. For `author_prepare` or `author_apply`,
invoke the same orchestrator with the author workflows. It coordinates the
existing Validator, `oqc_cursor_proposal_author`, and
`oqc_cursor_upgrade_applier`.

## Root session UI

Follow `references/workflows/workflows-root-session-interview.md`. The root
Cursor session owns exactly one human question for authoring: **outcome**.
Use `AskQuestion` here only — never inside a Task subagent. Present packaged
defaults for every other former gate; the user accepts or updates them, then
the run auto-continues (including apply) unless a script returns `blocked`.
