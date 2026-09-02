# Example pipeline profile

This profile is a fictional add-on that shows how a domain-specific artifact
class plugs into the core. It is not a real product format. It checks finished
pipeline YAML files — a name, an explicit approval choice, a durable state
store, and a list of jobs — plus optional companion data files for env values.

## Selecting this profile

Pass `profile: example-pipeline` in the skill's input. With no profile
selected, the core runs generic orchestration checks only and does not treat
`*.pipeline.yaml` as an artifact.

## What this profile adds

- `rules/rules-pipeline-artifact-quality-control.md` — six content rules
  (P1–P6) a finished pipeline must satisfy.
- `profile.json` — classification globs, artifact rule paths, and the
  namespaced kind `example-pipeline/artifact`. The core generator-source
  rules read `artifact_rules` from this manifest.
- `evals/` — four regression scenarios: inline env or literal secrets, missing
  retry or approval, a disconnected job in a multi-job graph, and a generator
  source that would emit a non-conforming pipeline.
