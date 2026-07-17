# Finding kind registry

Every finding's `kind` field is namespaced: `<namespace>/<name>`. This keeps profile
vocabulary from leaking into the core schema — the failure mode the 2026-07-15
architecture report's finding contract had (`artifact | generator-gap |
generator-contradiction | workflow | orchestrator` mixed core and E2E kinds in one
flat enum).

## Core namespace (`core/`)

Emitted by the portable core regardless of which profile is selected.

| Kind | Meaning |
| --- | --- |
| `core/workflow-authoring` | A workflow document violates a workflow-authoring rule (`rules-workflow-quality-control.md`). |
| `core/rules-authoring` | A rules document violates a rules-authoring rule (`rules-rules-authoring-quality-control.md`). |
| `core/orchestration` | An orchestrator document violates an orchestration-pattern rule (`rules-orchestrator-quality-control.md`). |
| `core/generator-gap` | Following a generator source would produce output that is silent on a rule it should address. |
| `core/generator-contradiction` | Following a generator source would produce output that directly violates a rule. |
| `core/state` | A state-lifecycle or checkpoint-handling defect. |
| `core/delegation` | A delegation-contract defect (incomplete spec, unvalidated return, missing retry bound). |

## Profile namespaces

Each profile declares its own kinds in its `profile.json` manifest (`kinds` field) and
uses the profile's own `id` as the namespace. For example, the `aplicatudo-e2e` profile
declares `aplicatudo-e2e/artifact` for its Maestro/Flutter artifact-quality findings.

A profile must not emit a kind outside its own namespace or the `core/` namespace.
`classify_targets.py` and `derive_finding_id.py` reject any other value.
