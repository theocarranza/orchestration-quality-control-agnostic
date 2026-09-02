## Claude Code adapter execution

This installed Claude Code edition uses the host-specific nested topology
below. This nested topology is the only shipped execution shape:

```text
root Claude session
└── oqc-orchestrator
    ├── oqc-validator
    └── oqc-remediator
```

For `validate` or `execute`:

1. Confirm the subagents `oqc-orchestrator`, `oqc-validator`, and
   `oqc-remediator` are available from the installed plugin's `agents/`.
2. If any required subagent is unavailable, return a `blocked` result with
   `stage: claude_adapter` and reason code `adapter_not_installed`. Do not
   run the checks in a single agent.
3. Spawn exactly one `oqc-orchestrator` (Agent tool, `subagent_type:
   oqc-orchestrator`) with the absolute path of this installed skill
   directory and the complete input contract.
4. Wait for the orchestrator and return its structured result without
   re-reading targets or applying edits in the root session.

The orchestrator owns routing, deterministic checkpoints, decision
reconciliation, and worker coordination. The validator's tool grant excludes
every write-capable tool. The remediator applies only the approved findings
the orchestrator hands it, inside the checkpoint's target set. The plugin's
`PreToolUse` hook separately blocks the root session's own `Edit`/`Write` on
any path listed in an active checkpoint's `targets`.

For `upgrade_prepare` or `upgrade_apply`, invoke `/oqc-upgrade`. For
`author_prepare` or `author_apply`, invoke `/oqc-author`. Both delegate to
exactly one `oqc-upgrade-orchestrator`. It coordinates the existing
validator, `oqc-proposal-author`, and `oqc-upgrade-applier`. The root
session owns every question and the atomic approval decision.
