---
date: 2026-07-16
type: plan
status: approved
tags: [plan, implementation, orchestration-quality-control, e2e, openskills, agent-skills, portability]
---

# Implementation Plan — Extract the Portable `orchestration-quality-control` Skill

Governing documents: [[2026-07-15-orchestration-qc-openskills-architecture]] (base design) and [[2026-07-16-adversarial-critique-qc-architecture-feedback]] (binding counterpoint — all six "What this means for orchestrator_qc_plugin" items applied below).

Approved by user 2026-07-16 with four confirmed decisions: 3-agent Claude adapter, core+profile ship together at v1.0.0, old sibling skills deleted after benchmark parity, deterministic scripts in Python 3 stdlib-only.

## Context

This repository holds a partial copy of a quality-control system called `predecessor-skill`, originally built inside the the former product monorepo. The system checks agent-orchestration documents (rules files, workflow files, orchestrator documents, and end-to-end test artifacts) against packaged rule sets, reports problems in plain language, and applies only the fixes a human approves.

Ground truth verified before planning:

- This directory was **not a git repository** at plan time. Nothing was tracked anywhere.
- Present: the shared library `predecessor-skill/` (8 rules files, 4 workflow files, 3 templates, 4 plain-language guides, evaluations with fixtures), the two entry skills `predecessor-validate-command/` and `predecessor-execute-command/` (version 3.0.0, declared "Claude Code only"), and a benchmark workspace (`predecessor-skill-workspace/iteration-1/`) proving the skill scores 100% on its evaluations versus 67% without it.
- Missing: the three Claude subagent definitions (`e2e-qc-orchestrator`, `e2e-qc-validator`, `e2e-qc-formatter`) and the pre-tool hook script that blocks main-session edits during a run. They are referenced everywhere but were never copied. They must be written fresh.
- Contamination: `predecessor-skill/state/` contained a leftover runtime checkpoint and an active-run marker whose paths pointed into the old monorepo by absolute path.

## Target end-state tree

```text
orchestrator_qc_plugin/                       (git repository after Phase 0)
├── orchestration-quality-control/            # the portable skill package
│   ├── SKILL.md                              # entry point; frontmatter: name + description only
│   ├── README.md
│   ├── CHANGELOG.md
│   ├── scripts/                              # deterministic substrate (Python 3, stdlib only)
│   │   ├── qc_lib.py  classify_targets.py  derive_finding_id.py
│   │   ├── checkpoint_state.py  reconcile_decision.py  render_diff.py
│   │   └── tests/                            # unit tests + fixtures, runnable offline
│   ├── references/
│   │   ├── schemas/                          # finding, checkpoint, input, blocked, profile manifest
│   │   ├── rules/  workflows/  templates/  plain-language/
│   ├── profiles/
│   │   └── former-product-profile/                   # profile.json, artifact rules, evals + fixtures
│   ├── adapters/
│   │   └── claude/                           # commands/, agents/ (3), hooks/, README
│   └── evals/
│       └── core/                             # new evaluations with zero the former product content
├── docs/adr/                                 # architecture decision records 0001–0005
├── predecessor-skill-workspace/            # benchmark evidence, kept read-only
└── AI_Codex_OrchestratorQcPlugin/            # vault, untouched by this plan
```

Runtime state (checkpoints written during a run) lives outside the package, in the target workspace at `.orchestration-qc/state/`. The package ships only the schema and lifecycle rules.

## Phase 0 — Baseline: version control, freeze, decontaminate

1. **Commit 1 — freeze.** `git init`, commit the entire current tree verbatim. Message records: copied v3 tree is the freeze baseline, not contamination; the three subagent definitions and hook were never migrated; stale state enters history as archived evidence.
2. **Commit 2 — decontaminate.** `git rm` the two stale state files. Write `docs/adr/0001-freeze-baseline-and-state-decontamination.md`.

## Phase 1 — Contracts and the deterministic substrate

Schemas in `references/schemas/`: `finding.schema.json` (content-anchored id, namespaced `kind`, required verbatim `anchor`, structured `suggested_change`), `checkpoint.schema.json` (schema v2, `pending_approval | consumed | aborted`), `input.schema.json`, `blocked.schema.json` (fixed reason-code list), `profile-manifest.schema.json`, `kinds.md` (namespaced registry).

Finding-id algorithm: `<rule-code>-<kind-shortname>-<hash10>[-<occurrence>]`, hash over normalized path + rule code + kind + normalized anchor text — no line numbers, so ids survive line drift after partial apply. Anchor-not-found is a mechanical injection-containment gate.

Scripts (Python 3 stdlib only, JSON out, exit 2 + `blocked` payload on failure): `qc_lib.py`, `classify_targets.py`, `derive_finding_id.py`, `checkpoint_state.py` (the state machine incl. `is-run-active`), `reconcile_decision.py`, `render_diff.py` (literal unified diffs via `difflib`). Verification: `python3 -m unittest discover` passes offline.

## Phase 2 — Core skill authoring

`SKILL.md` with spec-minimal frontmatter (name + description only); single-agent-with-code-gates as the default execution shape; report generated from structured findings only. `git mv` + rename the generic references (drop the `e2e-` brand, rename Formatter → Remediator), rewrite state-lifecycle wording to the new state machine. Decouple `rules-generator-quality-control.md` from the hardcoded E2E artifact reference via the profile manifest's `artifact_rules` key. Verification: zero E2E vocabulary hits in `references/` and `SKILL.md`.

## Phase 3 — The `former-product-profile` profile

Move the artifact rules file and the evaluations/fixtures into `profiles/former-product-profile/`; write `profile.json`; keep assertions byte-identical (regression contract); delete the emptied `predecessor-skill/` directory.

## Phase 4 — The Claude adapter (authored fresh)

Commands `oqc-validate.md` / `oqc-execute.md` + two compatibility aliases. Three agents: `oqc-orchestrator` (Opus; Agent/Read/Write/Bash-restricted), `oqc-validator` (Sonnet; Read/Grep/Glob/Bash), `oqc-remediator` (Sonnet; Read/Edit). Hook `oqc-block-main-edits.py` keyed on `checkpoint_state.py is-run-active`, no marker file. Verification: scratch-project install, full validate→block→execute→unblock cycle observed.

## Phase 5 — Evaluations and definition of done

New `evals/core/` fixtures with zero the former product vocabulary. Regression run of the profile evals against the `iteration-1` benchmark, parity required. Definition of done: offline unit tests pass; core alone completes a full cycle in a fixture repo with zero the former product files; profile evals at benchmark parity; partial-apply fixture proves id stability.

## Phase 6 — Compatibility, versioning, retirement

Core starts fresh at **1.0.0** (new schema, new id algorithm, new kind namespace — 3.x continuation would misrepresent compatibility). `predecessor-skill` name survives only as adapter command aliases. Delete the old sibling skills after Phase 5's parity gate passes. `CHANGELOG.md`, tag `v1.0.0`.

## Documentation rule for execution

Every human-facing document produced during implementation (READMEs, decision records, profile docs, changelog, migration notes) is written through `agile-workflow:generate-plain-language-documentation`. Dense agent-facing files (rules, workflows, agent definitions, SKILL.md body) stay compressed and imperative — out of that skill's scope by design.

## Critical source files

- `predecessor-skill/README.md` — taxonomy, topology, tool-grant specifications source.
- `predecessor-skill/references/rules/rules-e2e-generator-quality-control.md` — the mixed file whose decoupling defines the profile interface.
- `predecessor-skill/evals/evals.json` — the regression contract.
- `predecessor-validate-command/SKILL.md`, `predecessor-execute-command/SKILL.md` — v3 entry behavior ported forward.
- `predecessor-skill-workspace/iteration-1/benchmark.json` — the parity target.
