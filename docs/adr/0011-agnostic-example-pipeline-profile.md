# ADR 0011 — Product-agnostic core with `example-pipeline` profile

## Status

Accepted, 2026-09-02.

Amends [ADR 0001](0001-freeze-baseline-and-legacy-archival.md) and
[ADR 0005](0005-definition-of-done.md).

## Context

The 1.0.0 extraction kept a generic profile mechanism and shipped one
product-specific profile plus an archived predecessor tree so historical
evals could be cited. That coupling made a portable orchestration tool still
read as a one-product linter.

## Decision

1. Keep the generic profile mechanism (`profiles/<id>/profile.json`).
2. Ship exactly one example profile: `example-pipeline`, a fictional YAML
   pipeline format with rules P1–P6 and four evals.
3. Remove the former product profile, predecessor command aliases, and the
   archived predecessor tree from this repository.
4. Unknown profile ids continue to return `blocked` / `unknown_profile`.
5. Rewrite live docs, ADRs, CHANGELOG, and vault notes so they do not name
   the former product, the predecessor skill, or that product's mobile test
   stack.

ADR 0005 item 3 now means: the `example-pipeline` eval set reaches 100%
with-skill pass rate. Live-model grading remains documented as optional; it
is not a merge gate when offline tests pass.

## Consequences

- Breaking 3.0.0 for callers of the removed profile id or predecessor
  aliases.
- Historical freeze material from ADR 0001 is no longer in-tree; this ADR
  is the record that it was removed on purpose.
