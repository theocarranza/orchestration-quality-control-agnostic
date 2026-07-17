# ADR 0007: Native Cursor adapter

- Status: accepted
- Date: 2026-07-17

## Decision

Add Cursor as a host adapter beside the Codex and Claude adapters. The
portable `orchestration-quality-control` package remains the source of truth;
the Cursor build copies it into a native Cursor plugin and injects only a
Cursor-specific execution overlay.

The Cursor plugin uses the same nested roles:

```text
Cursor session
└── oqc_cursor_orchestrator
    ├── oqc_cursor_validator
    └── oqc_cursor_remediator
```

Cursor can distribute skills, custom subagents, and hooks inside one plugin,
so the three agent definitions are bundled under `agents/` and do not require
an external agent bootstrap or a Codex-style depth setting. The validator is a
`readonly: true` subagent. The orchestrator owns routing and deterministic
checkpoint decisions. The remediator applies only approved literal changes.
Cursor does not document a configurable maximum nesting depth, so a runtime
that cannot complete the orchestrator-to-worker handoff must produce `blocked`
instead of falling back to a single agent.

The generated marketplace uses `.cursor-plugin/marketplace.json` at its root
and a `.cursor-plugin/plugin.json` inside the plugin directory. Local testing
copies the plugin to `~/.cursor/plugins/local/orchestration-quality-control`.
Public distribution is through a Git repository submitted to the Cursor
Marketplace; users install it from the Marketplace or with `/add-plugin`.

## Approval boundary

The plugin registers Cursor `preToolUse` and `beforeShellExecution` hooks. The
hook denies pending shell commands except the deterministic OQC script
allowlist and denies protected edits unless the exact target and before/after
change match a current checkpoint authorization. It uses
`$CURSOR_PLUGIN_ROOT` for plugin-relative hook paths and the workspace root
from Cursor's hook payload for checkpoint state.

The hook proves approval integrity, not actor identity. Cursor hook decisions
are an additional host boundary, not proof that a particular named subagent
issued an authorized edit. This limitation is disclosed in the adapter README.

## Consequences

- Cursor users get one native plugin containing the skill, subagents, and hook.
- Local installation is dependency-free Python and fails closed on unmanaged
  destination collisions or later edits to a managed installation.
- Marketplace publication requires a Git repository and Cursor review; local
  ZIP output is for testing and controlled distribution only.
- No Cursor live runtime evaluation is claimed by the offline test suite; the
  generated structure and deterministic hook behavior require verification in
  an installed Cursor version before marketplace submission.
