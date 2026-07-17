# Evaluation transcript — module-slice folder

## Inputs

- Skill: `e2e-quality-control` (version 1.1.0)
- Target folder: `evals/fixtures/module-slice/`
- Report language: English
- Apply changes: no
- Rule source: `references/rules-e2e-quality-control.md` only (plus plain-language references for report rewrite)

## Phase 0 — Inputs (pre-supplied for eval)

- Target: entire `module-slice/` folder (3 YAML files)
- Language: `en`
- Apply gate: skipped (`apply changes=no`)

## Phase 1 — Load rules and targets

Read `references/rules-e2e-quality-control.md` in full.

Read each target file:

| File | Contents summary |
|------|------------------|
| `dead_subflow.yaml` | `tapOn` with `id: student_list_tile_primary_alt` |
| `orphan_helper.yaml` | `tapOn: "OK"` |
| `login.flow.yaml` | `runFlow: orphan_helper.yaml`, then `tapOn` with `id: student_list_tile_primary_extra` |

Built checklist for R1–R9 and B1–B3 against target set only.

## Phase 2 — Verify

### R6 — Orphan / dead artifacts

Scanned all files for `runFlow` references:

- `login.flow.yaml` line 3: `runFlow: orphan_helper.yaml` — `orphan_helper.yaml` has a caller.
- No file references `dead_subflow.yaml`.

**Hit:** `dead_subflow.yaml` is an orphan subflow (R6).

### R3 — Semantics identifier uniqueness (19-char prefix)

Collected `id:` values in target set:

- `student_list_tile_primary_alt` (dead_subflow.yaml)
- `student_list_tile_primary_extra` (login.flow.yaml)

Prefix check (first 19 characters):

```
student_list_tile_primary_alt   → student_list_tile_p
student_list_tile_primary_extra → student_list_tile_p
```

**Hit:** prefix collision (R3).

### Other rules — no hits in this set

| Rule | Result |
|------|--------|
| R1 Domain purity | No domain artifacts in folder |
| R2 Env data placement | No inline `env:` blocks |
| R4 Visible text selectors | `orphan_helper.yaml` uses visible text; id selectors in other files have no evident text alternative in the same artifact |
| R5 Priority not lexical | No priority fields |
| R7 Placeholders | No TODO/TBD/stubs |
| R8 Invented data smell | No suspicious invented values |
| R9 Production scope creep | No embedded notes about production changes |

Boundaries B1–B3: no false-positive patterns observed.

## Phase 3 — Report

Rewrote two raw hits using bundled plain-language pass (`plain-language-report-pass.md`, `plain-language-principles.md`, `output-formats.md`).

Saved `report.md` to eval output folder.

## Phase 4 — Apply gate

Skipped per evaluation mode (`apply changes=no`).

## Result

2 findings: 1 orphan subflow, 1 semantics id prefix collision.
