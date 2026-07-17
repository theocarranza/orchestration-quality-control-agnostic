# E2E Quality Control Report — module-slice (baseline, no skill)

**Target:** `evals/fixtures/module-slice/`  
**Mode:** Folder scan; English; read-only (no changes applied)  
**Rules:** General knowledge only (no packaged QC rules)  
**Date:** 2026-07-11

## Scope

Three Maestro YAML artifacts in the target folder:

| File | Role |
|------|------|
| `login.flow.yaml` | Entry flow (`.flow.yaml`) |
| `orphan_helper.yaml` | Helper subflow |
| `dead_subflow.yaml` | Helper subflow |

## Summary

| Check | Result |
|-------|--------|
| Orphan helper flows | **1 finding** |
| 19-character screen-id collisions | **1 finding** |

---

## Findings

### 1. Orphan helper flow — `dead_subflow.yaml`

**Severity:** Medium  
**Type:** Unreferenced subflow

`dead_subflow.yaml` is never invoked by any `runFlow` reference within the folder.

**Evidence:**

- `login.flow.yaml` calls only `orphan_helper.yaml`:
  ```yaml
  - runFlow: orphan_helper.yaml
  ```
- No file references `dead_subflow.yaml`.

**Suggested change:** Either wire `dead_subflow.yaml` into an entry flow (e.g. add `- runFlow: dead_subflow.yaml` where appropriate) or remove the file if it is obsolete.

---

### 2. Screen-id collision (first 19 characters)

**Severity:** High  
**Type:** Ambiguous selector / runtime mis-tap risk

Two distinct `id` values share the same 19-character prefix. On Android, resource identifiers are truncated to 19 characters at runtime, so Maestro may match the wrong widget.

| Full id | First 19 chars |
|---------|----------------|
| `student_list_tile_primary_alt` (`dead_subflow.yaml`) | `student_list_tile_p` |
| `student_list_tile_primary_extra` (`login.flow.yaml`) | `student_list_tile_p` |

**Suggested change:** Rename one or both ids so their first 19 characters differ (e.g. shorten or restructure suffixes: `student_list_tile_alt` vs `student_list_tile_xtra`).

---

## Files with no issues (this scan)

- **`orphan_helper.yaml`** — Referenced by `login.flow.yaml`; not orphaned despite its filename.
- **`login.flow.yaml`** — Valid entry flow; references `orphan_helper.yaml`.

## Checks performed

1. Listed all `.yaml` files in the folder.
2. Built a call graph from `runFlow:` references (intra-folder only).
3. Classified non-`.flow.yaml` files as helper/subflow candidates.
4. Collected all `tapOn.id` (and `id:` under tap steps) values.
5. Grouped ids by their first 19 characters and flagged groups with more than one member.

## Out of scope

- Content outside `module-slice/`
- Packaged E2E QC rules from the skill package
- Structural/schema validation beyond the two requested checks
