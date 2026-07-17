# Aplicatudo E2E profile

This profile adds the Aplicatudo-specific checks that used to be the whole
point of the `e2e-quality-control` skill: whether a finished Maestro test
artifact — a domain description, test plan, blueprint, flow, subflow, or
data file — is well-formed and free of the mistakes that keep recurring in
that project's end-to-end suite (credentials or Firestore field names
leaking into a domain file, environment values hardcoded into a flow instead
of a data file, screen identifiers that collide once Android truncates them,
and so on).

This profile **supersedes `e2e-quality-control` version 3.0.0**. Everything
that profile checked about Aplicatudo artifacts still applies; what changed
is packaging and identity, not the checks themselves.

## Selecting this profile

Pass `profile: aplicatudo-e2e` in the skill's input, alongside the generic
`operation`, `targets`, and `language` fields the core `SKILL.md` documents.
With no profile selected, the core runs the generic orchestration checks
only and knows nothing about Maestro, Aplicatudo, or Flutter.

## What this profile adds

- `rules/rules-e2e-artifact-quality-control.md` — the nine content and
  structure rules (R1–R9) a finished artifact must satisfy.
- `profile.json` — the manifest the core reads to know which file paths
  belong to this profile's artifact class, and which rule file to load for
  them. The core's `rules-generator-quality-control.md` (in
  `references/rules/`) reads this same manifest's `artifact_rules` key to
  judge whether a rules file, workflow file, or prompt that generates
  Aplicatudo artifacts would produce output that breaks these nine rules.
- `evals/` — the four regression scenarios this profile must keep passing:
  an inline-environment-value flow, a domain file mixing concerns, a folder
  with an orphaned helper flow and colliding screen identifiers, and a rules
  file written with forbidden rationale clauses.

## Migrating from `e2e-quality-control`

| Old (3.0.0) | New |
| --- | --- |
| `kind: artifact \| generator-gap \| generator-contradiction` | `kind: aplicatudo-e2e/artifact` (or a `core/generator-gap` / `core/generator-contradiction` finding from the core, when the generator source is judged against this profile's rules) |
| Finding `id` derived by hand or left implicit | Finding `id` derived by `scripts/derive_finding_id.py`, content-anchored — see the core `README.md` |
| A marker file tracked whether a run was active | A checkpoint's `status` field is the only active-run signal — see `references/schemas/checkpoint.schema.json` |
| Skill invoked as `e2e-quality-control-validate` / `-execute` | Skill invoked as `orchestration-quality-control` with `operation: validate` / `execute` and `profile: aplicatudo-e2e`; the old command names remain available as compatibility aliases in the Claude adapter |
