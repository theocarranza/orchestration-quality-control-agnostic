"""client_spec.py -- the decision surface that drives a generated client engine.

Why this module exists. `compile_workflow.py`'s own docstring records that four
fields on every generated `AgentSpec` -- `tools`, `output_schema`, `model_tier`,
`reasoning_effort` -- were fixed module constants applied identically to every
role, "not generated from `decisions` at all", because "nothing in the current
decision surface could drive any of the four". That was an accurate description
of a real gap, and the honest response was to leave the placeholders rather than
invent a decision nobody had made.

This module is that missing decision surface. A client specification names the
engine's roles, what each role is for, which abstract tool tokens it may use,
which it is explicitly denied, how much model capability it needs, and what
result shape it returns; plus the operations the engine offers and the task graph
each one runs. With a spec in hand, `compile_workflow` generates all four fields
per role instead of stamping one constant across every role, and the placeholders
are gone from that path.

Two properties this is built to guarantee, both of which the plan requires be
demonstrable rather than asserted:

  * **A relevant spec change changes the compiled process.** Roles, capabilities,
    tools, model tiers, result schemas and the task graph are all read from the
    spec. Nothing about the Maestro engine is hardcoded here, so compiling a
    different spec produces a different engine, not the same one with a new name.
  * **Tool grants are vendor-neutral.** `tools` are abstract lowercase tokens
    (`read`, `grep`, `edit`, `bash`), never host tool names. `adapters/` maps
    them to whatever the host calls them. A spec never names a model id either --
    only a tier, which the host resolves.

`denied_tools` is deliberately separate from simply omitting a tool. An omission
is silence; a denial is a statement. The generated role document renders denials
explicitly so a reader can tell "this role was never granted shell access" from
"this role must never be granted shell access", and `check_delivery` can see the
difference too.
"""

import json

import qc_lib
from qc_lib import Blocked

STAGE = "client_spec"

SCHEMA_VERSION = 1

MODEL_TIERS = ("low", "medium", "high")
REASONING_EFFORTS = ("low", "medium", "high")

#: Abstract, vendor-neutral capability tokens a role may be granted. Hosts map
#: these to their own tool names in adapters/; a spec never names a host tool.
KNOWN_TOOLS = ("read", "grep", "glob", "write", "edit", "bash", "delegate")

#: Tokens that let a role change the world. A role holding any of these is a
#: writing role, and the generated engine's rules treat it as such.
WRITING_TOOLS = frozenset({"write", "edit", "bash"})

_ROLE_REQUIRED = (
    "responsibilities",
    "capabilities",
    "tools",
    "model_tier",
    "reasoning_effort",
    "output_schema",
)

#: Client facts a generated engine must carry into its own documents: the
#: layout it writes into, how a flow file starts, how elements are selected, and
#: which host commands are known to be unsafe here. These live in the
#: specification rather than in compile_delivery, because they are statements
#: about one client's test tree, not about how engines are built. A generator
#: that hardcoded them would produce the same engine for every client.
_CONVENTION_FIELDS = (
    "config_file",
    "flow_glob",
    "flow_header",
    "runner_commands",
    "environment_variables",
    "layout",
    "selector_preference",
    "unsafe_commands",
)

_SPEC_REQUIRED = (
    "schema_version",
    "engine_id",
    "artifact_root",
    "state_root",
    "coordinator",
    "roles",
    "operations",
)


def _require_str(value, field):
    if not isinstance(value, str) or not value.strip():
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"'{field}' must be a non-empty string, got {value!r}",
            recovery_action=f"set '{field}' to a non-empty string",
        )
    return value


def _require_token_list(value, field, *, allowed=None, allow_empty=True):
    if not isinstance(value, list):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"'{field}' must be an array, got {type(value).__name__}",
            recovery_action=f"set '{field}' to an array of lowercase tokens",
        )
    if not value and not allow_empty:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"'{field}' must not be empty",
            recovery_action=f"name at least one token in '{field}'",
        )
    seen = set()
    for item in value:
        if not isinstance(item, str) or not item:
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"'{field}' contains a non-string entry {item!r}",
                recovery_action=f"use lowercase string tokens in '{field}'",
            )
        if item in seen:
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"'{field}' repeats the token '{item}'",
                recovery_action=f"list each token once in '{field}'",
            )
        seen.add(item)
        if allowed is not None and item not in allowed:
            raise Blocked(
                stage=STAGE,
                reason_code="capability_insufficient",
                detail=(
                    f"'{field}' names '{item}', which is not a known abstract tool token; "
                    f"known tokens are {', '.join(allowed)}"
                ),
                recovery_action=(
                    "use an abstract token, never a host tool name; hosts map tokens in adapters/"
                ),
            )
    return list(value)


def _validate_role(role_id, role):
    if not isinstance(role, dict):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"role '{role_id}' must be an object, got {type(role).__name__}",
            recovery_action="describe each role as an object",
        )
    qc_lib.require_fields(role, _ROLE_REQUIRED, stage=STAGE)
    _require_str(role["responsibilities"], f"roles['{role_id}'].responsibilities")
    _require_str(role["output_schema"], f"roles['{role_id}'].output_schema")
    qc_lib.require_enum(
        role["model_tier"], MODEL_TIERS, f"roles['{role_id}'].model_tier", stage=STAGE
    )
    qc_lib.require_enum(
        role["reasoning_effort"],
        REASONING_EFFORTS,
        f"roles['{role_id}'].reasoning_effort",
        stage=STAGE,
    )
    _require_token_list(
        role["capabilities"], f"roles['{role_id}'].capabilities", allow_empty=False
    )
    tools = _require_token_list(role["tools"], f"roles['{role_id}'].tools", allowed=KNOWN_TOOLS)
    denied = _require_token_list(
        role.get("denied_tools", []), f"roles['{role_id}'].denied_tools", allowed=KNOWN_TOOLS
    )
    overlap = sorted(set(tools) & set(denied))
    if overlap:
        raise Blocked(
            stage=STAGE,
            reason_code="capability_insufficient",
            detail=(
                f"role '{role_id}' both grants and denies {', '.join(overlap)}; "
                "a grant and a denial of the same token cannot both hold"
            ),
            recovery_action="remove the token from either tools or denied_tools",
        )
    return role


def _validate_operations(operations, role_ids):
    if not isinstance(operations, dict) or not operations:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail="'operations' must be a non-empty object of operation id -> task list",
            recovery_action="declare at least one operation",
        )
    used_roles = set()
    for operation_id, tasks in sorted(operations.items()):
        if not isinstance(tasks, list) or not tasks:
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"operation '{operation_id}' declares no tasks",
                recovery_action="give every operation at least one task",
            )
        task_ids = []
        for task in tasks:
            if not isinstance(task, dict):
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=f"operation '{operation_id}' has a task that is not an object",
                    recovery_action="describe each task as an object",
                )
            qc_lib.require_fields(task, ("task_id", "role"), stage=STAGE)
            task_id = _require_str(task["task_id"], f"{operation_id}.task_id")
            role = _require_str(task["role"], f"{operation_id}.{task_id}.role")
            if task_id in task_ids:
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=f"operation '{operation_id}' repeats task id '{task_id}'",
                    recovery_action="give each task in an operation a unique id",
                )
            task_ids.append(task_id)
            if role not in role_ids:
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=(
                        f"operation '{operation_id}' task '{task_id}' names role '{role}', "
                        "which this specification does not declare"
                    ),
                    recovery_action="declare the role, or point the task at a declared one",
                )
            used_roles.add(role)
        _require_acyclic(operation_id, tasks, task_ids)

    unused = sorted(set(role_ids) - used_roles)
    if unused:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=(
                f"role(s) {', '.join(unused)} are declared but no operation uses them; "
                "an engine should not ship a role nothing can reach"
            ),
            recovery_action="use the role in an operation, or remove it",
        )
    return operations


def _require_acyclic(operation_id, tasks, task_ids):
    edges = {}
    for task in tasks:
        depends_on = task.get("depends_on", [])
        if not isinstance(depends_on, list):
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"operation '{operation_id}' task '{task['task_id']}' has a non-array depends_on",
                recovery_action="set depends_on to an array of task ids",
            )
        for dependency in depends_on:
            if dependency not in task_ids:
                raise Blocked(
                    stage=STAGE,
                    reason_code="malformed_checkpoint",
                    detail=(
                        f"operation '{operation_id}' task '{task['task_id']}' depends on "
                        f"'{dependency}', which this operation does not declare"
                    ),
                    recovery_action="depend only on task ids declared in the same operation",
                )
        edges[task["task_id"]] = list(depends_on)

    visiting, done = set(), set()

    def walk(node, trail):
        if node in done:
            return
        if node in visiting:
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=(
                    f"operation '{operation_id}' has a dependency cycle: "
                    f"{' -> '.join(trail + [node])}"
                ),
                recovery_action="remove one edge so the task graph is acyclic",
            )
        visiting.add(node)
        for dependency in edges.get(node, []):
            walk(dependency, trail + [node])
        visiting.discard(node)
        done.add(node)

    for task_id in task_ids:
        walk(task_id, [])


def validate(spec):
    """Validate a client specification, returning it unchanged. Raises Blocked on any problem."""
    if not isinstance(spec, dict):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"client specification must be an object, got {type(spec).__name__}",
            recovery_action="pass a client specification object",
        )
    qc_lib.require_fields(spec, _SPEC_REQUIRED, stage=STAGE)
    if spec["schema_version"] != SCHEMA_VERSION:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"schema_version must be {SCHEMA_VERSION}, got {spec['schema_version']!r}",
            recovery_action=f"set schema_version to {SCHEMA_VERSION}",
        )
    _require_str(spec["engine_id"], "engine_id")
    qc_lib.normalize_path(_require_str(spec["artifact_root"], "artifact_root"), stage=STAGE)
    qc_lib.normalize_path(_require_str(spec["state_root"], "state_root"), stage=STAGE)

    roles = spec["roles"]
    if not isinstance(roles, dict) or not roles:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail="'roles' must be a non-empty object of role id -> role",
            recovery_action="declare at least one role",
        )
    for role_id, role in sorted(roles.items()):
        _validate_role(role_id, role)

    _validate_role("coordinator", spec["coordinator"])
    if "delegate" not in spec["coordinator"]["tools"]:
        raise Blocked(
            stage=STAGE,
            reason_code="capability_insufficient",
            detail="the coordinator must hold the 'delegate' token; coordinating is delegating",
            recovery_action="grant 'delegate' to the coordinator",
        )
    coordinator_writes = sorted(WRITING_TOOLS & set(spec["coordinator"]["tools"]))
    if coordinator_writes:
        raise Blocked(
            stage=STAGE,
            reason_code="capability_insufficient",
            detail=(
                f"the coordinator holds writing token(s) {', '.join(coordinator_writes)}; "
                "a coordinator that can author target content can substitute its own work "
                "for a worker's"
            ),
            recovery_action="move writing tokens to a worker role and let the coordinator delegate",
        )

    _validate_operations(spec["operations"], set(roles))
    _validate_conventions(spec.get("conventions"))
    return spec


def _validate_conventions(conventions):
    """Validate the optional conventions block.

    Optional because not every client has an established tree to conform to. But
    when a client does have one, silence here would mean the generated engine
    invents its own layout beside the real one -- which is exactly the "second
    stack" outcome this whole delivery is meant to avoid.
    """
    if conventions is None:
        return None
    if not isinstance(conventions, dict):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"'conventions' must be an object, got {type(conventions).__name__}",
            recovery_action="describe conventions as an object, or omit the block entirely",
        )
    for field in sorted(set(conventions) - set(_CONVENTION_FIELDS)):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"'conventions' has unknown field '{field}'",
            recovery_action=f"use only: {', '.join(_CONVENTION_FIELDS)}",
        )
    for field in ("config_file", "flow_glob", "flow_header", "selector_preference"):
        if field in conventions:
            _require_str(conventions[field], f"conventions.{field}")
    for field in ("runner_commands", "environment_variables"):
        if field in conventions and not isinstance(conventions[field], list):
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"'conventions.{field}' must be an array",
                recovery_action=f"set conventions.{field} to an array of strings",
            )
    layout = conventions.get("layout")
    if layout is not None and not isinstance(layout, dict):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail="'conventions.layout' must be an object of level -> expected files",
            recovery_action="describe the layout as an object",
        )
    for index, unsafe in enumerate(conventions.get("unsafe_commands", []) or []):
        if not isinstance(unsafe, dict):
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"conventions.unsafe_commands[{index}] must be an object",
                recovery_action="describe each unsafe command as an object",
            )
        qc_lib.require_fields(unsafe, ("command", "effect", "instead"), stage=STAGE)
        for field in ("command", "effect", "instead"):
            _require_str(unsafe[field], f"conventions.unsafe_commands[{index}].{field}")
    return conventions


def writing_roles(spec):
    """Role ids holding any writing token. The engine's rules constrain exactly these."""
    return sorted(
        role_id
        for role_id, role in spec["roles"].items()
        if WRITING_TOOLS & set(role["tools"])
    )


def load(path):
    """Read and validate a client specification from a JSON file."""
    return validate(qc_lib.load_json_file(path, stage=STAGE))


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate a client engine specification.")
    parser.add_argument("--spec", required=True)
    args = parser.parse_args()

    def body():
        spec = load(args.spec)
        return {
            "status": "valid",
            "engine_id": spec["engine_id"],
            "roles": sorted(spec["roles"]),
            "operations": sorted(spec["operations"]),
            "writing_roles": writing_roles(spec),
        }

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
