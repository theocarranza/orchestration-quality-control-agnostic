---
description: Quality-control rules for finished E2E artifacts (domain, test plan, blueprint, flow, subflow, data, fingerprint)
globs:
  - "**/modules/**/*.domain.md"
  - "**/modules/**/*.test_plan.md"
  - "**/modules/**/*.blueprint.md"
  - "**/modules/**/*.flow.yaml"
  - "**/modules/**/*.data.yaml"
alwaysApply: false
---

# Rule: E2E Artifact Quality Control

Apply this rule when validating a finished E2E artifact — domain, test plan,
blueprint, flow, subflow, data, or fingerprint file — for structural and
content quality. This rule belongs to the `aplicatudo-e2e` profile; it is
loaded only when that profile is selected, via its `profile.json` manifest's
`artifact_rules`.

## Scope

- Applies to finished artifacts: domain, test-plan, blueprint, flow, subflow,
  data, fingerprint, and quality-control report files. Check their structure
  and contents directly against the requirements below.
- Does not apply to generator sources that produce these artifacts (see the
  core's `rules-generator-quality-control.md`, which consumes this file via
  the profile manifest), to a rules file's own authoring form (see the
  core's `rules-rules-authoring-quality-control.md`), or to workflow or
  orchestrator documents.

## Required Context

- Read the target artifact in full before judging it.
- Judge only from the target's own contents; do not open seed stores, sibling
  artifacts outside the selection, or prior conversation memory to confirm a
  finding.

## Requirements

### R1 — Domain purity

Flag `{m}.domain.md` (or equivalent domain artifacts) that mix business rules
with credentials, Firestore field mappings, Semantics identifiers,
snackbar/timing values, or test strategy.

### R2 — Env data placement

Reject env values hardcoded inside a flow's own `env:` block. Env data must
live in a dedicated data file (e.g. `{f}.data.yaml` / `common.data.yaml`)
referenced by the flow. When the target set includes both the flow and its
data files, verify the reference points at a data file in the set; when only
the flow is present, flag inline `env:` values as violations.

### R3 — Semantics identifier uniqueness (19-char prefix)

Within the target set, every Semantics identifier must be unique within its
first **19 characters** (Android truncates beyond that length).

### R4 — Prefer visible text selectors

Prefer visible on-screen text for user-facing selectors over `id:` / Semantics
identifiers. Treat identifier-first selection as a project-level decision, not
official Maestro guidance. Flag identifier-first patterns when a visible-text
alternative is evident in the same artifact.

### R5 — Priority not lexical

Flag scenario priority that appears rederived purely from lexical keyword
counting (e.g. scoring by counting words like "critical"/"login" with no
human-stated priority).

### R6 — Orphan / dead artifacts (within target set)

- Flag ids that appear to encode a person's name (e.g. `student_tile`) with no
  consuming test in the target set as orphaned/dead.
- Flag orphan subflows with no `runFlow` reference anywhere in the target set.
- Flag dead test labels/selectors that are defined but never referenced in the
  target set.

### R7 — Placeholders and contract shape

Flag residual placeholders (`TODO`, `TBD`, `FIXME`, empty required sections,
obvious template stubs) and sections that look out-of-contract for the artifact
type suggested by the filename/extension.

### R8 — Invented data smell

Flag values that look invented rather than adapted from seed evidence when the
artifact itself gives no provenance (no seed citation, no data-file reference,
no comment tying the value to known fixture data). Do not open seed stores to
confirm — judge only from the target contents.

### R9 — Production-code scope creep

Escalate as a violation if the target (or an embedded note in it) records that
an earlier stage changed production code for anything other than
coordinator-approved `Semantics(identifier:)` additions.

## Boundaries

- Do not flag "wait then tap" as a violation when the tapped element is
  described as populated by a Firestore-backed / async list.
- Do not justify a selector finding by citing "id first" as upstream fact.
- Do not attribute dead selectors or orphan artifacts to an automated pipeline
  unless the target itself contains direct evidence a stage generated them;
  otherwise report them as manual-authoring defects.

## Output

- Produce one finding per violation, each naming what is wrong, which rule it
  breaks in plain words, where it is (path plus line or section), and a
  concrete change.
- Include a clear statement when no problems are found.
- Omit internal rule numbers from the reader-facing report; keep them in
  private notes only.

## Verification

- Walk R1–R9 against the target, quoting a snippet and location per finding.
- Report any requirement skipped because the target set lacks the evidence to
  judge it, stated as "not verifiable from selected targets".

## References

@../../../references/templates/rules-template.md
@../../../references/rules/rules-generator-quality-control.md
@../../../references/schemas/profile-manifest.schema.json
