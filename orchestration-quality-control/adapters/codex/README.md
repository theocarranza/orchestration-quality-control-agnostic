# Codex adapter

This adapter packages the portable `orchestration-quality-control` skill for
Codex and strengthens it with a nested custom-agent topology and a lifecycle
hook. It does not change the canonical Agent Skills package or the Claude
adapter.

## Topology and installation boundary

```text
root Codex session
└── oqc_codex_orchestrator
    ├── oqc_codex_validator
    └── oqc_codex_remediator
```

Codex plugins discover skills and hooks, but custom agent TOML files are
discovered separately under `~/.codex/agents/` or a project's
`.codex/agents/`. The **full Codex adapter** therefore has two explicit steps:
install the plugin, then run the adapter bootstrap. The nested topology
requires `agents.max_depth = 2`.

## Codex installation (required nested adapter)

The Codex adapter has one supported installation path. It installs the plugin,
the three custom agents, `agents.max_depth = 2`, and the approval hook together.
From the repository root (`orchestrator_qc_plugin`):

```bash
cd /path/to/orchestrator_qc_plugin
python3 orchestration-quality-control/adapters/codex/install_codex.py --scope user
```

For this checkout, the equivalent command is:

```bash
cd /home/corporaterick/Documents/Projects/Personal/orchestrator_qc_plugin
python3 orchestration-quality-control/adapters/codex/install_codex.py --scope user
```

The installer also resolves its repository paths from the script location, so
you may invoke it from another directory with its absolute path.

That single command builds the local marketplace, registers it with Codex,
installs the OQC plugin, installs the three custom agents, and verifies
`agents.max_depth = 2`.

Use `--scope project --project /path/to/project` for a project-local
installation. Use `--dry-run` to print the complete plan without changing
anything.

Do not install this adapter with `npx skills add` or by running the lower-level
bootstrap directly. Those paths omit part of the nested-agent contract and are
not valid Codex adapter installations.

Use `--scope project --project /path/to/project` to install the agents and
depth setting only for one trusted project. Both scopes support `--dry-run`.
The bootstrap refuses to overwrite conflicting agent files and refuses a TOML
edit it cannot perform surgically.

Restart Codex or start a new thread after installation. Review the plugin hook
with `/hooks` and explicitly trust it before relying on approval enforcement.

## Release install

Extract `dist/orchestration-quality-control-codex-1.1.0.zip`, then run the
front-door installer from the extracted directory:

```bash
python3 codex-marketplace/install_codex.py --scope user
```

The local and release layouts use the same deterministic builder.

## Updating and uninstalling

Rebuild or extract the new release, then run the same front-door installer
again. Installation is idempotent when its managed files are unchanged.

Remove the managed agent files and restore the bootstrap's exact config edit:

```bash
python3 orchestration-quality-control/adapters/codex/install_codex.py \
  --scope user \
  --uninstall
```

The front-door uninstaller removes the managed agents/config edit and the OQC
plugin. It leaves the local marketplace registration in place so it cannot
remove unrelated plugins.

## Approval hook

While a checkpoint has `status: pending_approval`, the bundled `PreToolUse`
hook:

- blocks patches to checkpoint targets until the orchestrator creates an
  adapter authorization from the approved finding ids;
- permits a protected patch only when its target and literal before/after
  change hash match that authorization and the checkpoint itself has not
  changed;
- blocks shell execution except direct invocations of the packaged
  deterministic scripts; and
- ignores or rejects stale authorization without turning it into a second
  active-run signal.

The authorization file is
`.orchestration-qc/state/codex-authorization-<run_id>.json`. It is ephemeral
adapter state and is cleared after consume or abort. The checkpoint status
remains the only active-run signal.

The hook proves approval integrity, not actor identity. Any agent capable of
submitting the exact authorized patch could submit it; the custom-agent
sandbox and operating instructions provide the role boundary.

## Capability matrix

| Guarantee | Codex adapter | Portable core |
| --- | --- | --- |
| Nested named roles | Three custom agents; requires separate bootstrap and depth 2 | Not required |
| Validator cannot write | `sandbox_mode = "read-only"` | Prompt-enforced |
| Pending unapproved target edits blocked | Plugin `PreToolUse` hook | Not enforced by the host |
| Approved change identity | Checkpoint hash plus literal change hash | Structured finding and rendered diff |
| Checkpoint state and decision reconciliation | Same deterministic core scripts | Same |
| Exact remediator identity | Not mechanically proven | Not applicable |

## Tests

```bash
python3 -m unittest discover \
  -s orchestration-quality-control/adapters/codex/tests \
  -p 'test_*.py'
```
