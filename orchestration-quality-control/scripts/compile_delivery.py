"""compile_delivery.py -- emit a complete, self-contained client engine package.

This is the step the 2026-09-09 authoring path never had. That path produced a
map of Markdown file contents, which satisfied
references/schemas/author-proposal.schema.json completely and delivered nothing
anyone could run. This module emits the whole package the client actually
receives: an entry point, a deterministic run spine, role documents, operation
task graphs, result definitions, templates, constants, a host adapter, and a
manifest that fingerprints every shipped file.

Everything is generated from a `client_spec.py` specification. Nothing about any
one client is hardcoded here -- change the specification's roles, tools, tiers or
task graph and the emitted package changes with it. `tests/test_compile_delivery.py`
pins that: two different specifications must not produce the same engine.

The emitted engine is independent by construction. Its Python imports nothing but
the standard library -- never `qc_lib`, never any other module of this plugin --
because a delivered engine that needs its author's checkout is not delivered.
`check_delivery.py` enforces exactly that, and `compile_delivery` runs it over its
own output before returning, so this module cannot emit a package that its own
checker would reject.
"""

import argparse
import hashlib
import json
from pathlib import Path

import check_delivery
import client_spec as client_spec_module
import qc_lib
from qc_lib import Blocked

STAGE = "compile_delivery"

#: How abstract capability tokens map onto hosts' tool names. Kept in the
#: emitted adapter, never in the specification: a specification that named
#: "Read" instead of "read" would be describing one vendor's product.
HOST_TOOL_MAPS = {
    "claude": {
        "read": "Read",
        "grep": "Grep",
        "glob": "Glob",
        "write": "Write",
        "edit": "Edit",
        "bash": "Bash",
        "delegate": "Agent",
    },
    "agy": {
        "read": "view_file",
        "grep": "grep_search",
        "glob": "find_by_name",
        "write": "write_to_file",
        "edit": "replace_file_content",
        "bash": "run_command",
        "delegate": "invoke_subagent",
    },
    "cursor": {
        "read": "read_file",
        "grep": "grep_search",
        "glob": "file_search",
        "write": "write_file",
        "edit": "edit_file",
        "bash": "run_terminal_command",
        "delegate": "delegate_task",
    },
    "codex": {
        "read": "read_file",
        "grep": "grep",
        "glob": "find_files",
        "write": "write_file",
        "edit": "edit_file",
        "bash": "bash",
        "delegate": "spawn_agent",
    },
}
CLAUDE_TOOL_MAP = HOST_TOOL_MAPS["claude"]

RESULT_SCHEMA_NAMES = (
    "request",
    "worker-result",
    "finding",
    "proposed-change",
    "approval",
    "run-state",
    "final-report",
)


def _sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# -- generated file bodies ----------------------------------------------------


def _constants(spec):
    return json.dumps(
        {
            "engine_id": spec["engine_id"],
            "artifact_root": spec["artifact_root"],
            "state_root": spec["state_root"],
            "operations": sorted(spec["operations"]),
            "max_attempts": spec.get("max_attempts", 3),
            "roles": sorted(spec["roles"]),
            "writing_roles": client_spec_module.writing_roles(spec),
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def _client_specification(spec):
    """Return the validated client-owned decision record shipped with its engine."""
    return json.dumps(spec, indent=2, sort_keys=True) + "\n"


def _markdown_list(items):
    return "\n".join(f"- {item.strip()}" for item in items)


def _implementation_plan(spec, *, source_revision, engine_root_rel):
    """Turn the owner interview and accepted design into the client plan of record."""
    interview = spec["interview"]
    operations = "\n".join(
        f"- `{operation_id}`: "
        + " -> ".join(task["task_id"] for task in tasks)
        for operation_id, tasks in sorted(spec["operations"].items())
    )
    roles = "\n".join(
        f"- `{role_id}`: {role['responsibilities'].strip()}"
        for role_id, role in sorted(spec["roles"].items())
    )
    return f"""# Implementation plan: {spec['engine_id']}

## Client interview

- Repository owner: {interview['owner'].strip()}
- Desired outcome: {interview['outcome'].strip()}
- Source revision assessed: `{source_revision}`
- Engine location: `{engine_root_rel}`

## Requirements

{_markdown_list(interview['requirements'])}

## Constraints

{_markdown_list(interview['constraints'])}

## Evidence reviewed

{_markdown_list(interview['evidence'])}

## Implementation steps

1. Keep the client specification and this plan under `{engine_root_rel}/`.
2. Use the generated coordinator and role contracts; do not add client policy to the authoring plugin.
3. Run the declared operations against `{spec['artifact_root']}/` and record runtime state only under `{spec['state_root']}/`.
4. Apply artifact changes only after the engine's check and approval gates pass.

## Engine design

### Roles

{roles}

### Operations

{operations}

## Validation

1. Validate `client-spec.json` before compilation.
2. Run `check_delivery.py` after emission; it must pass.
3. Run the generated-engine acceptance test without access to the authoring plugin.
4. Before a live client run, confirm the plan still matches the assessed source revision.
"""


def _role_document(role_id, role, spec, *, is_coordinator=False):
    granted = ", ".join(role["tools"]) or "none"
    denied = ", ".join(role.get("denied_tools", [])) or "none"
    title = "Coordinator" if is_coordinator else role_id.replace("-", " ").title()
    lines = [
        f"# {title}",
        "",
        "## Responsibilities",
        "",
        role["responsibilities"].strip(),
        "",
        "## Model",
        "",
        f"model_tier: {role['model_tier']}",
        f"reasoning_effort: {role['reasoning_effort']}",
        "",
        "## Tools",
        "",
        f"tools: {granted}",
        f"denied_tools: {denied}",
        "",
        "These are abstract tokens. `adapters/claude/README.md` maps them to the",
        "host's own tool names. A denial is a statement, not an omission: a role",
        "listed as denying a token must never be granted it by any host.",
        "",
        "## Output",
        "",
        f"Returns a result matching `{role['output_schema']}`.",
        "",
    ]
    if is_coordinator:
        lines += [
            "## Boundaries",
            "",
            "- Delegates every unit of work. Never authors or edits target content itself.",
            "- Never substitutes its own summary for a worker's returned result.",
            f"- Writes run records only under `{spec['state_root']}/`.",
            "- Never writes under the artifact folder; only a writing role does that,",
            "  and only after approval.",
            "",
        ]
    else:
        writes = client_spec_module.WRITING_TOOLS & set(role["tools"])
        lines += ["## Boundaries", ""]
        if writes:
            lines += [
                f"- May write, and only under `{spec['artifact_root']}/`.",
                "- Applies only the exact approved change set. Selects nothing itself.",
                "- Holds no approval authority.",
                "",
            ]
        else:
            lines += [
                "- Returns findings or drafts. Writes nothing to the artifact folder.",
                "- Returns results to the coordinator; never delegates to another worker.",
                "",
            ]
    return "\n".join(lines)


def _architecture(spec):
    role_rows = "\n".join(
        f"| {role_id} | {', '.join(role['tools']) or 'none'} | "
        f"{', '.join(role.get('denied_tools', [])) or 'none'} | {role['model_tier']} |"
        for role_id, role in sorted(spec["roles"].items())
    )
    operation_rows = "\n".join(
        f"| {operation_id} | " + " -> ".join(task["task_id"] for task in tasks) + " |"
        for operation_id, tasks in sorted(spec["operations"].items())
    )
    return f"""# Architecture

The `{spec['engine_id']}` engine. One coordinator delegates to isolated roles;
roles return results to the coordinator and never to one another.

## Roles

| Role | Tools | Denied | Model |
|---|---|---|---|
{role_rows}

## Operations

| Operation | Task order |
|---|---|
{operation_rows}

## Approval and state

Every run keeps a durable record under `{spec['state_root']}/`. The record
carries the run identifier, the operation, the current phase, every accepted
worker result, and the digest of the change set put forward for approval.

Approval authorises writing content that has already passed checking. It can
never substitute for checking, and it binds to a digest: if the change set moves
after approval, the digest no longer matches and application refuses.

Artifact writes are confined to `{spec['artifact_root']}/`. Run records are
confined to `{spec['state_root']}/`. No other path is writable by any role.

## Independence

This engine depends on the standard library and its host. It imports nothing
from the tool that generated it, and it can be copied to a machine where that
tool is absent.
"""


def _readme(spec):
    operations = "\n".join(f"- `{name}`" for name in sorted(spec["operations"]))
    return f"""# {spec['engine_id']}

Generated engine. Plans, drafts, checks, and applies changes under
`{spec['artifact_root']}/`.

## Operations

{operations}

## Commands

```bash
python3 scripts/run.py start --operation <name> --run-id <id>
python3 scripts/run.py status --run-id <id>
python3 scripts/run.py resume --run-id <id>
```

`start` opens a run record. `status` reports the phase and what the run is
waiting for. `resume` continues an approved run.

## Layout

- `IMPLEMENTATION_PLAN.md` — the client owner's interview-backed plan of record.
- `client-spec.json` — the validated client decisions that generated this engine.
- `agents/` — what each role is for, and what it may and may not use.
- `operations/` — the task graph each operation runs.
- `schemas/` — the shape of every request, result, and record.
- `templates/` — starting points for generated artifacts.
- `rules/`, `workflows/` — the behaviour rules and the ordered procedure.
- `constants.json` — shared paths and limits.
- `manifest.json` — the delivery record, with a fingerprint per shipped file.

## Requirements

Python 3.12 and the host named in `adapters/`. Nothing else.
"""


def _skill(spec):
    return f"""# {spec['engine_id']}

Use this engine to plan, draft, check, and apply changes under
`{spec['artifact_root']}/`.

Start with `README.md` for the commands, `ARCHITECTURE.md` for the roles and the
approval rules, and `workflows/` for the ordered procedure. Read the role
document in `agents/` before acting as that role.

Never write outside `{spec['artifact_root']}/` and `{spec['state_root']}/`.
"""


def _adapter(spec, host="claude"):
    tool_map = HOST_TOOL_MAPS.get(host, CLAUDE_TOOL_MAP)
    rows = "\n".join(
        f"| `{token}` | `{name}` |" for token, name in sorted(tool_map.items())
    )
    grants = "\n".join(
        f"| {role_id} | {', '.join(tool_map[t] for t in role['tools']) or 'none'} |"
        for role_id, role in sorted(spec["roles"].items())
    )
    title = host.capitalize() if host != "agy" else "Antigravity (AGY)"
    return f"""# {title} adapter

Maps this engine's abstract tokens to the host's tool names. The engine's own
documents never name a host tool; this file is the only place the two meet.

## Token map

| Token | Host tool |
|---|---|
{rows}

## Resulting grants

| Role | Host tools |
|---|---|
{grants}

## Disclosed limit

These grants are configuration the host enforces. This file records what each
role should hold; it cannot itself prevent a host from granting more. Treat a
denial as a requirement on whoever configures the host, and verify it there.
"""


def _operation_file(operation_id, tasks):
    return json.dumps(
        {
            "operation_id": operation_id,
            "tasks": [
                {
                    "task_id": task["task_id"],
                    "worker": task["role"],
                    "depends_on": list(task.get("depends_on", [])),
                }
                for task in tasks
            ],
        },
        indent=2,
        sort_keys=True,
    ) + "\n"


def _schema_file(name, spec):
    common = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": f"https://{spec['engine_id']}/schemas/{name}.schema.json",
        "type": "object",
    }
    if name == "worker-result":
        common.update(
            {
                "title": "Worker result",
                "required": ["task_id", "role", "outcome"],
                "additionalProperties": False,
                "properties": {
                    "task_id": {"type": "string", "minLength": 1},
                    "role": {"type": "string", "minLength": 1},
                    "outcome": {"enum": ["passed", "failed"]},
                    "inspected_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "findings": {"type": "array", "items": {"$ref": "finding.schema.json"}},
                    "proposed_changes": {
                        "type": "array",
                        "items": {"$ref": "proposed-change.schema.json"},
                    },
                    "applied_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["path", "action"],
                            "additionalProperties": True,
                            "properties": {
                                "path": {"type": "string", "minLength": 1},
                                "action": {"enum": ["create", "update"]},
                            },
                        },
                    },
                    "skipped_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["path", "reason"],
                            "additionalProperties": True,
                            "properties": {
                                "path": {"type": "string", "minLength": 1},
                                "reason": {"type": "string", "minLength": 1},
                            },
                        },
                    },
                    "limitations": {"type": "string"},
                },
            }
        )
    elif name == "finding":
        common.update(
            {
                "title": "Finding",
                "required": ["id", "severity", "summary", "location"],
                "additionalProperties": True,
                "properties": {
                    "id": {"type": "string", "minLength": 1},
                    "severity": {"enum": ["low", "medium", "high"]},
                    "summary": {"type": "string", "minLength": 1},
                    "location": {
                        "type": "object",
                        "required": ["path"],
                        "additionalProperties": True,
                        "properties": {"path": {"type": "string", "minLength": 1}},
                    },
                },
            }
        )
    elif name == "proposed-change":
        common.update(
            {
                "title": "Proposed change",
                "description": "A literal change, never a description of one.",
                "required": ["path", "action", "after"],
                "additionalProperties": False,
                "properties": {
                    "path": {"type": "string", "minLength": 1},
                    "action": {"enum": ["create", "update"]},
                    "before": {"type": "string"},
                    "after": {"type": "string"},
                },
            }
        )
    elif name == "approval":
        common.update(
            {
                "title": "Approval",
                "required": ["decision", "approved_digest", "decided_at"],
                "additionalProperties": False,
                "properties": {
                    "decision": {"enum": ["approve", "decline"]},
                    "approved_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
                    "decided_at": {"type": "string", "minLength": 1},
                },
            }
        )
    elif name == "run-state":
        common.update(
            {
                "title": "Run state",
                "required": ["run_id", "operation", "phase", "created_at"],
                "additionalProperties": True,
                "properties": {
                    "run_id": {"type": "string", "minLength": 1},
                    "operation": {"type": "string", "minLength": 1},
                    "phase": {
                        "enum": [
                            "planning",
                            "drafting",
                            "checking",
                            "awaiting_approval",
                            "applying",
                            "completed",
                            "stopped",
                        ]
                    },
                    "created_at": {"type": "string", "minLength": 1},
                    "results": {"type": "array", "items": {"$ref": "worker-result.schema.json"}},
                    "approval": {"$ref": "approval.schema.json"},
                    "proposed_digest": {"type": "string"},
                },
            }
        )
    elif name == "request":
        common.update(
            {
                "title": "Request",
                "required": ["run_id", "task_id", "role"],
                "additionalProperties": True,
                "properties": {
                    "run_id": {"type": "string", "minLength": 1},
                    "task_id": {"type": "string", "minLength": 1},
                    "role": {"type": "string", "minLength": 1},
                    "inputs": {"type": "object"},
                },
            }
        )
    else:  # final-report
        common.update(
            {
                "title": "Final report",
                "required": ["run_id", "operation", "outcome", "applied", "skipped"],
                "additionalProperties": True,
                "properties": {
                    "run_id": {"type": "string", "minLength": 1},
                    "operation": {"type": "string", "minLength": 1},
                    "outcome": {"enum": ["completed", "stopped"]},
                    "applied": {"type": "array"},
                    "skipped": {"type": "array"},
                },
            }
        )
    return json.dumps(common, indent=2, sort_keys=True) + "\n"


def _load_template(filename: str) -> str:
    candidates = [
        Path(__file__).resolve().parent / "templates" / filename,
        Path(__file__).resolve().parents[1] / "entrypoints" / "orchestration-engine" / "templates" / filename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Delivery template not found: {filename}")


_ENGINE_LIB = _load_template("engine_lib.py")
_RUN_PY = _load_template("run.py")


def _rules(spec):
    writing = client_spec_module.writing_roles(spec) or ["none"]
    return f"""# Rules

- Artifact writes happen only under `{spec['artifact_root']}/`, only from
  {', '.join(writing)}, and only after an approval that names the change set's
  digest.
- Run records are written only under `{spec['state_root']}/`. This is an
  explicit allowance, not an exception someone has to argue for.
- Every worker result is checked against its declared result shape before the
  coordinator uses it. An unusable result is a failed attempt, not a silent pass.
- Every accepted result and report is saved as soon as it is accepted, so an
  interruption loses nothing.
- The coordinator delegates. It never authors target content and never replaces
  a worker's returned result with its own account of it.
- A checking role is given the material it needs to judge. Missing material is a
  blocked check, never a pass.
- Every proposed item ends applied or skipped with a stated reason. An
  unresolved item is never reported as done.
- At most {spec.get('max_attempts', 3)} attempts per task, including corrections
  for an unusable response. The producing role makes its own corrections.
"""


def _workflows(spec):
    steps = []
    for operation_id, tasks in sorted(spec["operations"].items()):
        steps.append(f"## {operation_id}")
        steps.append("")
        for index, task in enumerate(tasks, start=1):
            depends = ", ".join(task.get("depends_on", [])) or "nothing"
            steps.append(
                f"{index}. `{task['task_id']}` — delegate to `{task['role']}`. "
                f"Waits on: {depends}."
            )
            steps.append(
                f"   Gate the returned result against `{spec['roles'][task['role']]['output_schema']}` "
                "before the next step reads it, then persist it."
            )
        steps.append("")
        steps.append(
            "Then put the change set forward for approval, apply it once approved, "
            "and write the final report."
        )
        steps.append("")
    return "# Workflows\n\n" + "\n".join(steps)


def _templates(spec):
    return {
        "test-plan.md": (
            "# Test plan\n\n"
            "## Scope\n\nWhat this covers, in one paragraph.\n\n"
            "## Steps\n\n1. First observable step.\n\n"
            "## Expected\n\nWhat proves it worked.\n"
        ),
        "flow.md": (
            "# Flow\n\n"
            "One scenario per file. Prefer stable identifiers over visible text when\n"
            "selecting elements. Record any host command known to be unsafe here.\n"
        ),
        "report.md": (
            "# Report\n\n"
            "## What ran\n\n## What passed\n\n## What did not\n\n## What was skipped, and why\n"
        ),
    }


# -- assembly -----------------------------------------------------------------


def build_files(spec, *, source_revision, engine_root_rel):
    """Return the complete engine as a map of engine-relative path -> contents."""
    spec = client_spec_module.validate(spec)
    target_host = spec.get("target_host") or spec.get("host") or "claude"
    adapter_rel = f"adapters/{target_host}/README.md"
    files = {
        "README.md": _readme(spec),
        "SKILL.md": _skill(spec),
        "ARCHITECTURE.md": _architecture(spec),
        "IMPLEMENTATION_PLAN.md": _implementation_plan(
            spec, source_revision=source_revision, engine_root_rel=engine_root_rel
        ),
        "client-spec.json": _client_specification(spec),
        "constants.json": _constants(spec),
        "scripts/run.py": _RUN_PY,
        "scripts/engine_lib.py": _ENGINE_LIB,
        "agents/coordinator.md": _role_document(
            "coordinator", spec["coordinator"], spec, is_coordinator=True
        ),
        adapter_rel: _adapter(spec, host=target_host),
        "rules/rules-engine.md": _rules(spec),
        "workflows/workflows-engine.md": _workflows(spec),
    }
    for role_id, role in sorted(spec["roles"].items()):
        files[f"agents/{role_id}.md"] = _role_document(role_id, role, spec)
    for operation_id, tasks in sorted(spec["operations"].items()):
        files[f"operations/{operation_id}.json"] = _operation_file(operation_id, tasks)
    for name in RESULT_SCHEMA_NAMES:
        files[f"schemas/{name}.schema.json"] = _schema_file(name, spec)
    for name, body in _templates(spec).items():
        files[f"templates/{name}"] = body

    files["manifest.json"] = _manifest(
        spec, files, source_revision=source_revision, engine_root_rel=engine_root_rel
    )
    return files


def _manifest(spec, files, *, source_revision, engine_root_rel):
    target_host = spec.get("target_host") or spec.get("host") or "claude"
    dep_host = f"{target_host}-code" if target_host == "claude" else target_host
    manifest = {
        "schema_version": 1,
        "engine_id": spec["engine_id"],
        "source_revision": source_revision,
        "engine_root": engine_root_rel,
        "artifact_root": spec["artifact_root"],
        "state_root": spec["state_root"],
        "client_specification": "client-spec.json",
        "implementation_plan": "IMPLEMENTATION_PLAN.md",
        "entrypoint": "scripts/run.py",
        "constants": "constants.json",
        "operations": {
            operation_id: f"operations/{operation_id}.json"
            for operation_id in sorted(spec["operations"])
        },
        "coordinator": "agents/coordinator.md",
        "workers": [
            {
                "id": role_id,
                "definition": f"agents/{role_id}.md",
                "input_schema": "schemas/request.schema.json",
                "output_schema": role["output_schema"],
                "capabilities": list(role["capabilities"]),
            }
            for role_id, role in sorted(spec["roles"].items())
        ],
        "schemas": {
            name.replace("-", "_"): f"schemas/{name}.schema.json" for name in RESULT_SCHEMA_NAMES
        },
        "templates": {
            name.rsplit(".", 1)[0].replace("-", "_"): f"templates/{name}"
            for name in sorted(_templates(spec))
        },
        "adapters": {target_host: f"adapters/{target_host}/README.md"},
        "dependencies": ["python>=3.12", dep_host],
        "files": {path: _sha256_text(body) for path, body in sorted(files.items())},
    }
    return json.dumps(manifest, indent=2, sort_keys=True) + "\n"


def _is_seed_specification(engine_root, specification_path):
    """True only for the single interview record permitted before compilation."""
    if specification_path is None or not engine_root.exists():
        return False
    candidate = Path(specification_path).resolve()
    expected = (engine_root / "client-spec.json").resolve()
    return (
        candidate == expected
        and candidate.is_file()
        and not candidate.is_symlink()
        and [entry.resolve() for entry in engine_root.iterdir()] == [candidate]
    )


def emit(spec, *, engine_root, project_root, source_revision, specification_path=None):
    """Write the engine to disk, then check it with check_delivery before returning."""
    engine_root = Path(engine_root)
    project_root = Path(project_root).resolve()
    if engine_root.exists() and any(engine_root.rglob("*")) and not _is_seed_specification(
        engine_root, specification_path
    ):
        raise Blocked(
            stage=STAGE,
            reason_code="destination_exists",
            detail=f"engine root is not empty: {engine_root}",
            recovery_action=(
                "choose a missing or empty engine root, or retain only the interview-backed "
                "client-spec.json in that root"
            ),
        )
    try:
        engine_root_rel = engine_root.resolve().relative_to(project_root).as_posix()
    except ValueError as exc:
        raise Blocked(
            stage=STAGE,
            reason_code="unsafe_path",
            detail=f"engine root '{engine_root}' is not inside '{project_root}'",
            recovery_action="emit the engine inside the client project",
        ) from exc

    files = build_files(spec, source_revision=source_revision, engine_root_rel=engine_root_rel)
    for relative, body in sorted(files.items()):
        target = engine_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")

    verdict = check_delivery.check_delivery(engine_root=engine_root, project_root=project_root)
    if verdict["status"] != "passed":
        raise Blocked(
            stage=STAGE,
            reason_code="invalid_proposal",
            detail=(
                "the emitted engine does not satisfy the delivery contract: "
                + "; ".join(f"{p['code']} {p['detail']}" for p in verdict["problems"][:5])
            ),
            recovery_action="fix the generator; a package its own checker rejects is not deliverable",
        )
    return {
        "status": "emitted",
        "engine_root": engine_root_rel,
        "file_count": len(files),
        "delivery_check": verdict["status"],
    }


def main():
    parser = argparse.ArgumentParser(description="Compile a client engine package from a specification.")
    parser.add_argument("--spec", required=True)
    parser.add_argument("--engine-root", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()

    def body():
        return emit(
            client_spec_module.load(args.spec),
            engine_root=args.engine_root,
            project_root=args.project_root,
            source_revision=args.source_revision,
            specification_path=args.spec,
        )

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
