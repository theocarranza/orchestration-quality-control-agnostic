# Cursor adapter

This adapter packages the portable `orchestration-quality-control` skill as a
native Cursor plugin. It includes the same nested review topology as the Codex
adapter:

```text
Cursor session
├── oqc_cursor_orchestrator
│   ├── oqc_cursor_validator
│   └── oqc_cursor_remediator
└── oqc_cursor_upgrade_orchestrator
    ├── oqc_cursor_validator
    ├── oqc_cursor_proposal_author
    └── oqc_cursor_upgrade_applier
```

Cursor plugins can bundle skills, custom subagents, and hooks in one plugin
directory. The QC and upgrade roles are distributed inside the plugin; no
separate agent bootstrap or depth setting is required.

Cursor documents named subagents but does not expose a Codex-style configurable
maximum nesting depth. This adapter still requires the orchestrator to spawn
the validator and remediator. If the installed Cursor runtime cannot perform
that nested handoff, the adapter must return `blocked`; it must not silently
fall back to a single-agent run.


For guided upgrade, invoke `/oqc-upgrade`. It bundles the
`oqc-upgrade` skill and delegates to `oqc_cursor_upgrade_orchestrator`.
## Local installation

From the repository root, run the single front-door installer:

```bash
python3 orchestration-quality-control/adapters/cursor/install_cursor.py
```

The installer builds the Cursor plugin and copies it to
`~/.cursor/plugins/local/orchestration-quality-control`. Restart Cursor after
installation, or run **Developer: Reload Window**. Use `--dry-run` to inspect
the plan without changing files, and `--uninstall` to remove an unchanged
managed installation.

Cursor must be allowed to load local plugins. Some managed workspaces require
an administrator to enable local plugin imports.

## Distribution through the Cursor Marketplace

Build the marketplace repository with:

```bash
python3 orchestration-quality-control/adapters/cursor/build_plugin.py
```

The generated `dist/cursor-marketplace/` contains a Cursor marketplace
manifest and the plugin under `plugins/orchestration-quality-control/`. Publish
that repository through Cursor’s plugin submission process. Users can then
install it from the Cursor Marketplace or with `/add-plugin`.

Cursor’s public marketplace uses Git repositories and reviews submissions for
security. For a private team distribution, use the team marketplace facilities
available in the user’s Cursor plan.

## Approval hook

While a checkpoint is waiting for approval, the bundled hook:

- denies shell commands except the deterministic OQC scripts;
- denies edits to protected targets unless the exact approved before/after
  change matches the current checkpoint; and
- allows unrelated file changes and normal operation when no checkpoint is
  pending.

The authorization file is
`.orchestration-qc/state/cursor-authorization-<run_id>.json`. It is temporary
adapter state and is cleared after the decision is consumed or aborted.

The hook proves approval integrity, not agent identity. Cursor’s hook contract
can deny a tool call, but an authorized change could still be submitted by any
actor able to reproduce that exact change. This limitation is disclosed rather
than presented as stronger isolation than Cursor provides.

## Capability matrix

| Guarantee | Cursor adapter | Portable core |
| --- | --- | --- |
| Nested named roles | Three bundled Cursor subagents | Not required |
| Validator cannot write | Cursor `readonly: true` subagent | Prompt-enforced |
| Pending unapproved target edits blocked | Cursor `preToolUse` and `beforeShellExecution` hooks | Not enforced by the host |
| Approved change identity | Checkpoint hash plus literal change hash | Structured finding and rendered diff |
| Checkpoint state and decision reconciliation | Same deterministic core scripts | Same |
| Exact remediator identity | Not mechanically proven | Not applicable |

## References

- [Cursor plugin documentation](https://cursor.com/docs/plugins)
- [Cursor plugin reference](https://cursor.com/docs/reference/plugins)
- [Cursor skills](https://cursor.com/docs/skills)
- [Cursor subagents](https://cursor.com/docs/subagents)
- [Cursor hooks](https://cursor.com/docs/hooks)
