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
