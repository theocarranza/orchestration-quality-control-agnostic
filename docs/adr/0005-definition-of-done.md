# ADR 0005 — Definition of done for the extraction

## Status

Accepted, 2026-07-16. Item 3 below is open — see Consequences.

## Context

The architecture report's "Decisions, assumptions, and out of scope" section
named a missing definition of done for the extraction as a gap the
adversarial critique's item 8 also flagged. This package needs an explicit,
checkable answer to "when is the extraction actually finished?" rather than
an implied one.

## Decision

The extraction is done when all four of the following hold:

1. **The deterministic substrate's own tests pass offline.**
   `python3 -m unittest discover` under both `scripts/tests/` and
   `adapters/claude/hooks/tests/` passes with no model call anywhere in the
   run. Verified repeatedly through Phases 1–4 of this build (61 tests
   total: 53 script tests, 8 hook tests).

2. **The portable core completes a full cycle on a fixture repository with
   zero Aplicatudo, Maestro, or Flutter content.** Demonstrated during
   Phase 4 with a full simulated run through the real scripts and hook:
   classify a generic workflow fixture, derive a finding id, create a
   `pending_approval` checkpoint, confirm the hook blocks a direct edit to
   the checked-out target, resolve a decision, render and apply a diff,
   finalize outcomes, consume the checkpoint, confirm the hook then allows
   the same edit. `evals/core/fixtures/` (added in Phase 5) gives this a
   permanent, named fixture set — a generic orchestrator missing a bounded
   retry and durable state, a rules file with rationale clauses, a workflow
   with an incomplete delegation spec, and one fully compliant workflow —
   with `evals/core/evals.json` recording the expected findings and report
   properties for each.

3. **Profile evaluations pass at benchmark parity.** The
   `aplicatudo-e2e` profile's `evals/evals.json` (four cases, byte-identical
   assertions to the retired `e2e-quality-control` 3.0.0 evaluations) must
   reproduce the `100%` with-skill pass rate recorded in
   `legacy/e2e-quality-control-workspace/iteration-1/benchmark.json`.

4. **The partial-apply conformance fixture proves finding-id stability.**
   `scripts/tests/fixtures/partial-apply/` plus
   `PartialApplyConformanceTest` in `scripts/tests/test_finding_id.py`
   verify a finding's id is unchanged when an unrelated edit shifts every
   line after it. Passing since Phase 1.

## Consequences

Item 3 requires running the eval prompts in `evals/core/evals.json` and
`profiles/aplicatudo-e2e/evals/evals.json` against a live model inside an
actual Claude Code (or other host) session and grading the resulting
transcripts against each eval's `assertions` — the same kind of harness that
produced `legacy/e2e-quality-control-workspace/iteration-1/`. That harness
is external to this package and was not itself part of what was extracted;
no equivalent grading script exists in this repository. This step could not
be executed as part of this implementation pass, which had no access to a
live model to run the evals against.

This is recorded as open, not silently skipped. Before this package is
treated as fully validated, someone with access to run the actual
Claude Code skill (or the eval harness used to produce
`iteration-1/benchmark.json`) needs to execute both eval sets and confirm
parity, then update this ADR's status accordingly.
