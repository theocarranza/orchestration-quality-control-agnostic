# Orchestration Quality Control

This repository contains the reusable `orchestration-quality-control` skill,
its host adapters, the evaluation harness used to verify behavior, and the
release bundles built from the source tree.

If you only want the reusable package, start with:

- `orchestration-quality-control/SKILL.md`
- `orchestration-quality-control/README.md`

If you want the Codex-specific install path, use:

- `orchestration-quality-control/adapters/codex/README.md`

## Repository layout

- `orchestration-quality-control/` — portable skill package: rules, schemas,
  scripts, profiles, and adapters.
- `eval-harness/` — benchmark conversion and integrity checks.
- `docs/adr/` — architecture decisions.
- `dist/` — release bundles generated from the source tree.
- `legacy/` — archived prior material kept for reference.
- `AI_Codex_OrchestratorQcPlugin/` — local Obsidian vault and working notes.

## Working with the repo

Run the test suites directly with Python:

```bash
python3 -m unittest discover -s orchestration-quality-control/scripts/tests -p 'test_*.py'
python3 -m unittest discover -s orchestration-quality-control/adapters/codex/tests -p 'test_*.py'
python3 -m unittest discover -s eval-harness/tests -p 'test_*.py'
```

## Publishing notes

- Keep generated workspaces and runtime state out of commits.
- Keep machine-local editor and adapter settings out of commits.
- Update `orchestration-quality-control/CHANGELOG.md` when public behavior
  changes.
- Prefer small, reviewable diffs over broad rewrites.

