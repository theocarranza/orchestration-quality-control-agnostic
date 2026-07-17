# Evaluation Transcript — module-slice (baseline, no skill)

**Started:** 2026-07-11  
**Evaluator:** Baseline agent (no skill file loaded)  
**Target:** `projects/aplicatudo/.agents/skills/e2e-quality-control/evals/fixtures/module-slice/`

---

## Step 1 — Inventory

Listed all files in the target folder:

```
dead_subflow.yaml
orphan_helper.yaml
login.flow.yaml
```

No subdirectories. Scope limited to these three files per instructions.

---

## Step 2 — Read artifacts

### `login.flow.yaml`

```yaml
appId: br.com.aplicatudo
---
- runFlow: orphan_helper.yaml
- tapOn:
    id: student_list_tile_primary_extra
```

### `orphan_helper.yaml`

```yaml
appId: br.com.aplicatudo
---
- tapOn: "OK"
```

### `dead_subflow.yaml`

```yaml
appId: br.com.aplicatudo
---
- tapOn:
    id: student_list_tile_primary_alt
```

---

## Step 3 — Orphan helper flow analysis

**Method:** Treat every `.yaml` file that is not a `*.flow.yaml` entry flow as a helper/subflow candidate. Mark as orphan if no other file in the folder contains `runFlow: <filename>`.

| Helper file | Referenced by |
|-------------|---------------|
| `orphan_helper.yaml` | `login.flow.yaml` (`runFlow: orphan_helper.yaml`) |
| `dead_subflow.yaml` | *(none)* |

**Result:** `dead_subflow.yaml` is an unreferenced helper subflow.

Note: `orphan_helper.yaml` is **not** orphaned — only its filename suggests otherwise.

---

## Step 4 — Screen-id collision analysis (19-char prefix)

**Method:** Extract widget `id` values from `tapOn` steps; group by `id[:19]`; flag groups with count > 1.

| id | source file | prefix (19) |
|----|-------------|-------------|
| `student_list_tile_primary_extra` | `login.flow.yaml` | `student_list_tile_p` |
| `student_list_tile_primary_alt` | `dead_subflow.yaml` | `student_list_tile_p` |

Verified programmatically:

```
'student_list_tile_primary_alt' -> first 19: 'student_list_tile_p'
'student_list_tile_primary_extra' -> first 19: 'student_list_tile_p'
COLLISION prefix 'student_list_tile_p': ['student_list_tile_primary_alt', 'student_list_tile_primary_extra']
```

**Result:** One collision group affecting two ids across two files.

---

## Step 5 — Output

Wrote:

- `report.md` — structured findings
- `transcript.md` — this file

**Changes applied:** None (evaluation mode: apply changes = no).

---

## Conclusion

Two quality issues in a three-file slice:

1. One orphan helper (`dead_subflow.yaml`).
2. One 19-character screen-id collision pair (`student_list_tile_primary_alt` / `student_list_tile_primary_extra`).
