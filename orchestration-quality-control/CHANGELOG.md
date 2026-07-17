## 2.0.0 — 2026-07-17

- **Breaking:** removed the `portable-single-agent` execution shape and
  reference template. This skill now ships and documents exactly one
  execution shape — the isolated three-agent topology (Orchestrator,
  Validator, Remediator) — across the core `SKILL.md`, the guided-upgrade
  `template_id` input (now fixed to `isolated-three-agent`), and every host
  adapter. A host that cannot complete the nested handoff returns `blocked`
  instead of silently running the checks in a single agent. See ADR 0010,
  which supersedes ADR 0003.
- **Breaking:** removed the `isolation_reason` field entirely — from
  `upgrade-input.schema.json`, `upgrade-checkpoint.schema.json`,
  `render_upgrade.py`, `upgrade_state.py`, `apply_upgrade.py`, the
  `workflows-upgrade-prepare.md` inputs, rule T10, and the `/oqc-upgrade`
  command/skill UI on every adapter. Selecting the isolated three-agent
  topology no longer requires a justification.
- Added a native Claude Code distribution adapter: `adapters/claude/build_plugin.py`
  produces a reproducible `dist/claude-marketplace/` with a
  `.claude-plugin/marketplace.json`, a bundled plugin manifest, the existing
  six subagents and five slash commands, and a plugin-shipped `PreToolUse`
  hook using `${CLAUDE_PLUGIN_ROOT}` — reaching build/test/distribution
  parity with the Codex and Cursor adapters. See ADR 0009.
- Installing the Claude plugin from a marketplace now auto-registers the hook
  and components; the previous manual `.claude/agents/`/`.claude/commands/`
  copy plus hand-edited `settings.json` remains documented as a fallback.
- Documented OpenSkills / skill-only install of the canonical package as an
  unsupported path for Claude Code: without the bundled subagents it must
  return `blocked` rather than run a reduced pipeline, matching the existing
  Codex `npx skills add` disclosure.
- Bumped `plugin.template.json`/`build_plugin.py` `VERSION` to `2.0.0` across
  the Claude, Codex, and Cursor adapters to keep them in lockstep.

## 1.2.0 — 2026-07-17

- Added guided orchestration upgrade operations (`upgrade_prepare`,
  `upgrade_apply`) with portable reference templates, deterministic
  discovery/render/state/apply scripts, and schema-version 3 upgrade
  checkpoints plus verification records.
- Added Proposal Author, Upgrade Orchestrator, and Upgrade Applier roles
  across Claude (`/oqc-upgrade`), Cursor (`/oqc-upgrade`), and Codex
  (`orchestration-upgrade`) adapters while reusing the existing Validator for
  semantic QC at nesting depth 2.
- Extended Codex/Cursor hook deterministic-script allowlists and packaging
  tests; added focused offline tests for upgrade path containment, template
  selection, stale hashes, collisions, atomic apply/rollback, shared
  active-run exclusion, and verification persistence.

# Changelog

## 1.1.0 — 2026-07-17

- Added a Codex distribution adapter without changing the portable package
  boundary: a reproducible local marketplace and ZIP, a generated
  Codex-specific skill entry overlay, and a bundled `PreToolUse` hook.
- Added the explicitly selected nested Codex topology
  (`oqc_codex_orchestrator` → Validator/Remediator) plus an idempotent,
  reversible bootstrap for custom-agent discovery and `agents.max_depth = 2`.
- Added checkpoint-bound approval authorization so pending target patches must
  exactly match an approved finding's literal change; shell execution is
  restricted to the deterministic package scripts while approval is pending.
- Added offline regression suites for packaging, bootstrap/config preservation,
  authorization lifecycle, and hook enforcement.
- Added a native Cursor distribution adapter with bundled nested subagents,
  Cursor plugin and marketplace manifests, a local-plugin installer, and
  checkpoint-bound `preToolUse`/`beforeShellExecution` enforcement.

## 1.0.0 — 2026-07-16

First release of the portable core, extracted from the Aplicatudo-specific
`e2e-quality-control` skill (version 3.0.0). Starts at 1.0.0 rather than
continuing the 3.x line, because continuing it would misrepresent this as a
drop-in replacement: the checkpoint schema, finding-id algorithm, and finding
`kind` namespace all changed.

- New public identity: `orchestration-quality-control`. `e2e-quality-control`
  is no longer a skill name — see `profiles/aplicatudo-e2e/README.md` for
  its migration table, and `adapters/claude/commands/` for the compatibility
  command aliases.
- Generic orchestration checks (workflow authoring, rules authoring,
  orchestrator authoring, generator-source coverage, validator/remediator/
  orchestrator subagent behavior) are now the reusable core; Aplicatudo/
  Maestro/Flutter checks moved to the optional `aplicatudo-e2e` profile.
- Checkpoint `schema_version` is now `2`. Findings carry content-anchored
  ids (stable across a partial-apply edit that shifts line numbers) instead
  of whatever identity scheme, if any, a given run happened to produce.
  Finding `kind` values are namespaced (`core/...` or `<profile-id>/...`)
  instead of one flat, profile-coupled enum.
- The active-run signal is a checkpoint's own `status` field
  (`pending_approval | consumed | aborted`) — there is no marker file.
- Every stage the skill claims is deterministic (classification, finding
  identity, checkpoint transitions, decision reconciliation, diff
  rendering) is now enforced by dependency-free Python under `scripts/`,
  with its own offline test suite, rather than described in prose alone.
- The Claude adapter's three-subagent topology (Orchestrator, Validator,
  Remediator) is preserved from the 3.0.0 design, but is now explicitly one
  adapter's enforcement choice, not the core's required shape — the core's
  documented default is a single agent running the same rules with the same
  script-enforced gates.
