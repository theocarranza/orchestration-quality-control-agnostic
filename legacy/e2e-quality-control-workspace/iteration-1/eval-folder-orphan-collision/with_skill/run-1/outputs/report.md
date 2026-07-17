# End-to-end quality report

## What was checked

The folder `evals/fixtures/module-slice/` containing three Maestro flow files:

- `dead_subflow.yaml`
- `orphan_helper.yaml`
- `login.flow.yaml`

## Summary

Two problems were found. One helper subflow is never called by any flow in this set. Two screen identifiers share the same first nineteen characters, which can cause taps to hit the wrong element on Android.

## Findings

### Finding 1. Unused helper subflow

What is wrong: `dead_subflow.yaml` is a subflow file, but no other file in this folder calls it with `runFlow`. It is dead code in this slice.

Rule: Orphan and dead artifacts must not remain in the test set without a caller.

Where: `dead_subflow.yaml` (entire file); no `runFlow` reference to this file appears in `login.flow.yaml` or `orphan_helper.yaml`.

Suggested change: Either add a `runFlow: dead_subflow.yaml` step to a flow that should use it, or remove `dead_subflow.yaml` from this folder if it is no longer needed.

### Finding 2. Screen identifiers collide on nineteen-character prefix

What is wrong: Two different screen identifiers start with the same nineteen characters (`student_list_tile_p`). On Android, semantics identifiers longer than nineteen characters are truncated, so `student_list_tile_primary_alt` and `student_list_tile_primary_extra` can be treated as the same id.

Rule: Every semantics identifier in the target set must be unique within its first nineteen characters.

Where:
- `dead_subflow.yaml`, line 4: `id: student_list_tile_primary_alt`
- `login.flow.yaml`, line 5: `id: student_list_tile_primary_extra`

Suggested change: Rename one or both identifiers so their first nineteen characters differ. For example, shorten or reword the prefix segment (such as `student_tile_alt` versus `student_tile_extra`) while keeping names meaningful in the app.
