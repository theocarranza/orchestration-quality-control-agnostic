---
name: orchestration-engine
description: >
  Deliver a complete, self-contained client orchestration engine from a
  validated client specification. Use when the requested result must run on
  its own and include an entrypoint, scripts, agents, schemas, templates,
  adapters, a manifest, and a delivery check.
license: MIT
---

# Orchestration Engine Delivery

Use this entrypoint for a runnable client engine. Do not use
`orchestration-author`: it authors process documents and cannot satisfy this
delivery contract.

1. Resolve the installed canonical skill root as
   `../orchestration-quality-control/` relative to this entrypoint. Stop with
   `adapter_not_installed` if the sibling root or its delivery compiler is
   unavailable.
2. Interview the client repository owner before designing anything. Record the
   owner, desired outcome, concrete requirements, constraints, and evidence in
   the client-owned `client-spec.json`. The specification belongs in the intended
   engine root; the compiler may use that one seed file in an otherwise empty
   root. Do not use a plugin profile or encode client requirements in this package.
3. Require that interview-backed client specification, a project-relative engine
   root, and a project-relative artifact root. The engine and artifact roots must
   be siblings or otherwise disjoint; neither may contain the other.
4. Validate the specification with
   `../orchestration-quality-control/scripts/client_spec.py`. The specification
   determines the roles, tool grants, task graph, result shapes, and runtime
   state root. Do not substitute fixed defaults for those decisions.
5. Compile with `../orchestration-quality-control/scripts/compile_delivery.py`.
   Before emitting the runtime package, it produces `IMPLEMENTATION_PLAN.md` in
   the client engine root from the recorded interview and the validated design.
   The compiler then emits the entrypoint, deterministic runtime scripts, agents,
   operations, schemas, templates, adapter, rules, workflows, constants, and
   `manifest.json`.
6. Require `../orchestration-quality-control/scripts/check_delivery.py` to
   pass before treating the package as delivered. Its check covers containment,
   complete file checksums, the client specification and implementation plan,
   task graph integrity, role definitions, content integrity, and independence
   from the authoring plugin.
7. Run the focused generated-engine acceptance test before a live client trial.
   The test must invoke the delivered entrypoint from a temporary workspace
   where the authoring plugin is unavailable.

The runtime state directory may be inside the engine root when the client
requires it. It is operational data, not a shipped engine file; the delivery
checker excludes only that declared runtime-state subtree from the manifest
file set.
