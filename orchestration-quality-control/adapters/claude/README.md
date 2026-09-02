# Claude adapter

This adapter mechanizes the portable core's rules into three separate
subagents with distinct tool grants. This isolated three-agent topology is
the only execution shape this package ships; see the core `README.md` for
the shared Orchestrator/Validator/Remediator contracts every host adapter
mechanizes.

## What this adapter adds beyond the portable core

| Piece | What it does |
| --- | --- |
| `commands/oqc-validate.md` | Main-session entry point for the validate operation: collects target/profile/language, delegates, presents the report, asks the apply decision. |
| `commands/oqc-execute.md` | Main-session entry point for the execute operation: resolves the apply decision, delegates, presents the final report. |
| `commands/oqc-upgrade.md` | Main-session entry point for guided orchestration upgrade: confirms discovery, delegates prepare/apply, records atomic approval. |
| `agents/oqc-orchestrator.md` | Opus, tools `Agent, Read, Write, Bash` (Bash restricted to `scripts/`). Owns routing, checkpoint bookkeeping, and gate validation. Never reads or edits target content. |
| `agents/oqc-validator.md` | Sonnet, tools `Read, Grep, Glob, Bash` (Bash restricted to `scripts/classify_targets.py` and `scripts/derive_finding_id.py`). Mechanically read-only — this subagent has no tool capable of writing a file. |
| `agents/oqc-remediator.md` | Sonnet, tools `Read, Edit, Bash` (Bash restricted to `scripts/render_diff.py`). Applies only findings the orchestrator hands it, only inside the checkpoint's target set. |
| `agents/oqc-upgrade-orchestrator.md` | Opus, tools `Agent, Read, Write, Bash` (Bash restricted to `discover_structure.py` and `upgrade_state.py`). Coordinates upgrade prepare/apply. |
| `agents/oqc-proposal-author.md` | Sonnet, tools `Read, Grep, Glob`. Drafts one atomic upgrade proposal; never writes targets. |
| `agents/oqc-upgrade-applier.md` | Sonnet, tools `Read, Bash` (Bash restricted to `scripts/apply_upgrade.py`). Applies one approved upgrade checkpoint. |
| `hooks/oqc-block-main-edits.py` | A `PreToolUse` hook that blocks the main session's own `Edit`/`Write` on any path listed in an active checkpoint's `targets`, so a user cannot bypass the approval gate by editing the file directly while a review is pending. |

## Installation

### Marketplace (recommended)

Build the marketplace repository with:

```bash
python3 orchestration-quality-control/adapters/claude/build_plugin.py
```

The generated `dist/claude-marketplace/` contains a Claude Code plugin
marketplace manifest (`.claude-plugin/marketplace.json`) and the plugin under
`plugins/orchestration-quality-control/` — agents, commands, hooks, and the
canonical skill plus the `orchestration-upgrade` skill, all in one bundle.

Add and install it from a Claude Code session:

```text
/plugin marketplace add /absolute/path/to/dist/claude-marketplace
/plugin install orchestration-quality-control@orchestration-qc-local
```

(Or point `/plugin marketplace add` at a Git repository built from this
output for team/public distribution.) Installing the plugin registers the
`agents/*.md` subagents, the `commands/*.md` slash commands, and the
`PreToolUse` hook automatically — no manual `settings.json` edit or file
copying is required. Use `/plugin` to inspect installed components or
uninstall.

### Manual copy (fallback)

If a host cannot install a plugin from a marketplace:

1. Copy `agents/*.md` into the target project's `.claude/agents/`.
2. Copy `commands/*.md` into the target project's `.claude/commands/`.
3. Register the hook in the target project's `.claude/settings.json`:

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Edit|Write",
           "hooks": [
             {
               "type": "command",
               "command": "python3 <path-to-package>/orchestration-quality-control/adapters/claude/hooks/oqc-block-main-edits.py"
             }
           ]
         }
       ]
     }
   }
   ```

4. Ensure `python3` is on the host's `PATH` — every script this adapter
   calls, including the hook, is stdlib-only and needs no package
   installation.

### OpenSkills / skill-only install (unsupported)

`npx openskills install` can fetch the canonical `orchestration-quality-control/`
package by itself (it is a spec-compliant `SKILL.md` package). Doing so
installs the rules, workflows, and scripts but none of the `agents/*.md`
subagents or the `PreToolUse` hook, since OpenSkills installs a skill
directory, not a plugin. Without the Orchestrator/Validator/Remediator
subagents available, the skill must return `blocked` with reason code
`adapter_not_installed` rather than run the checks itself — this is the same
reduced-enforcement tradeoff already documented for the Codex adapter's
`npx skills add` path (see `adapters/codex/README.md`) and for the
product-wide full-plugin-only decision in ADR 0009. Prefer the marketplace
install above whenever the host is Claude Code.

## Capability matrix

| Guarantee | Claude adapter (plugin install) | Skill-only install, no subagents |
| --- | --- | --- |
| Validator cannot write a file | Mechanical — the subagent's tool grant excludes every write-capable tool | Not applicable — the skill returns `blocked` instead of running |
| Direct edits blocked while a run is pending | Mechanical — the `PreToolUse` hook intercepts every `Edit`/`Write` call | Not applicable — no hook is installed |
| Checkpoint state transitions are legal | Enforced by `scripts/checkpoint_state.py` | Not applicable — the skill returns `blocked` instead of running |
| Finding identity survives partial apply | Enforced by `scripts/derive_finding_id.py` | Not applicable — the skill returns `blocked` instead of running |
| Report built only from structured findings, never raw target text | An instruction every subagent must follow; not currently mechanically enforced | Not applicable — the skill returns `blocked` instead of running |

A skill-only install without the nested subagents must state plainly that it
cannot run the checks at all — it must never claim Claude-level guarantees,
and it must never silently substitute a single unrestricted agent for the
Orchestrator/Validator/Remediator topology.
