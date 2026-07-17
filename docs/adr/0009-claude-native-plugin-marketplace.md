# ADR 0009 — Native Claude Code plugin marketplace

## Status

Accepted, 2026-07-17.

## Context

The Claude adapter (`orchestration-quality-control/adapters/claude/`) already
had full content — six subagent definitions, five slash commands, and a
`PreToolUse` hook — but no build, no plugin manifest, and no marketplace. Its
documented install path was a manual three-step copy of files plus a hand-edit
of the target project's `.claude/settings.json`. Codex and Cursor, by
contrast, each have a `build_plugin.py` producing a reproducible marketplace
under `dist/<host>-marketplace/` with a `BUILD-MANIFEST.json` and a versioned
release zip (ADR 0007 for the Cursor precedent).

Separately, the 2026-07-17 standards report
(`AI_Codex_OrchestratorQcPlugin/Agent_Reports/2026-07-17-agent-skills-standards-analysis.md`)
fixed a product-wide rule: **full-plugin distribution only**. A skill-only
install (via OpenSkills or Claude's native `npx skills add`-equivalent
skill-directory install) would ship instructions without the nested subagent
tool boundaries and the hook-enforced approval gate — the primary anti-drift
mechanism this product exists to provide. The Codex adapter already disclosed
this for `npx skills add`; the same disclosure was missing for Claude's own
skill-only install path (`npx openskills install` or a bare `.claude/skills/`
copy).

## Decision

Add `orchestration-quality-control/adapters/claude/build_plugin.py`, mirroring
the Cursor build (`adapters/cursor/build_plugin.py`) with Claude Code's native
manifest shape:

```text
dist/claude-marketplace/
├── .claude-plugin/marketplace.json
├── plugins/orchestration-quality-control/
│   ├── .claude-plugin/plugin.json
│   ├── agents/            (6 oqc-* subagent definitions)
│   ├── commands/           (5 slash commands, incl. e2e-* compat aliases)
│   ├── hooks/hooks.json + oqc-block-main-edits.py
│   └── skills/
│       ├── orchestration-quality-control/  (canonical package + Claude overlay)
│       └── orchestration-upgrade/
├── BUILD-MANIFEST.json
└── README.md
```

`.claude-plugin/marketplace.json` and `.claude-plugin/plugin.json` use the
same `owner`/`plugins[]`/`interface` shape already used by every marketplace
installed in this environment (verified against
`~/.claude/plugins/marketplaces/*/.claude-plugin/`), so no new schema is
invented here.

Unlike Codex and Cursor, this adapter ships **no separate Python installer**.
Claude Code has a native marketplace install flow
(`/plugin marketplace add <path-or-git-url>` then `/plugin install
<name>@<marketplace>`) that registers commands, agents, and hooks
automatically on install — a bespoke installer would duplicate host
functionality the other two hosts lack.

The plugin-shipped `hooks/hooks.json` uses `${CLAUDE_PLUGIN_ROOT}` for the
hook command path, replacing the manual `settings.json` edit previously
documented as the only install path. That manual edit remains documented as a
fallback for hosts that cannot install a plugin from a marketplace.

The Claude adapter's README documents three tiers explicitly:

1. Marketplace install (supported, full enforcement).
2. Manual copy fallback (supported, same enforcement, more setup).
3. OpenSkills / skill-only install (documented, unsupported — reduced
   enforcement, no hook, no subagent tool boundaries), matching the existing
   Codex disclosure pattern.

## Consequences

- Claude reaches build/test/distribution parity with the Codex and Cursor
  adapters: a reproducible `build_plugin.py`, a hashed `BUILD-MANIFEST.json`,
  a versioned release zip, and a test suite
  (`adapters/claude/tests/test_build_plugin.py`) wired into CI.
- `orchestration-quality-control/adapters/claude/skill-overlay.md` is
  injected into a copy of the canonical `SKILL.md` at build time (same
  overlay-injection pattern as Codex/Cursor); the canonical package source is
  never mutated by the build.
- No Claude-specific installer script exists or is needed; `/plugin
  marketplace add` / `/plugin install` are the supported commands, documented
  in the adapter README rather than wrapped in project code.
- Users who install via OpenSkills or a bare skill-directory copy get a
  working but weaker single-agent pipeline; the README states this plainly
  rather than implying parity with the plugin install.
- `plugin.template.json` version bumps must stay in lockstep across all three
  adapters (Claude, Codex, Cursor) and the canonical `CHANGELOG.md`.
