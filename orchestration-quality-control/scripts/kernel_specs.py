"""Vendor-neutral kernel records: RunSpec, AgentSpec and Envelope.

This is the Outcome 2 Task 1 slice of
AI_Codex/Architecture/ADR/0014-generated-workflow-deterministic-kernel.md:
the three core records the deterministic kernel exchanges, with explicit
validation and stable serialisation, and nothing else. No mailbox, reducer
or router lives here — those are later tasks in the same outcome.

Every record is vendor-neutral by construction: fields carry abstract
capability tokens and model/reasoning *tiers*, never a host name, a model
id, or any other vendor vocabulary. Adapters (a later outcome) are the only
place a provider identifier may appear.

`schemas/envelope.schema.json` is the authoritative Envelope contract.
`Envelope.from_dict` validates against that file directly, so the schema and
the Python validation cannot drift apart the way two hand-maintained field
lists could.
"""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from qc_lib import Blocked, freeze, load_json_file, require_enum, require_fields, thaw

SCRIPTS_DIR = Path(__file__).resolve().parent
SCHEMA_DIR = SCRIPTS_DIR.parent / "schemas"
ENVELOPE_SCHEMA_PATH = SCHEMA_DIR / "envelope.schema.json"

SCHEMA_VERSION = 1

MODEL_TIERS = ("low", "medium", "high")
REASONING_EFFORTS = ("low", "medium", "high")

_IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")
_TOKEN_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

_JSON_SCHEMA_TYPES = {
    "object": dict,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "array": (list, tuple),
    "null": type(None),
}


# ---------------------------------------------------------------------------
# Field-level validation helpers. Each raises qc_lib.Blocked naming the exact
# field, so "each required field's absence is rejected with a named error"
# holds for value shape, not only for key presence (require_fields covers
# key presence already).
# ---------------------------------------------------------------------------


def _require_str(value, field_name, *, stage):
    if not isinstance(value, str) or not value.strip():
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' must be a non-empty string, got {value!r}",
            recovery_action=f"set '{field_name}' to a non-empty string",
        )


def _require_identifier(value, field_name, *, stage):
    _require_str(value, field_name, stage=stage)
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' must match {_IDENTIFIER_PATTERN.pattern}, got {value!r}",
            recovery_action=f"set '{field_name}' to a lowercase identifier (letters, digits, '-', '_')",
        )


def _require_const_int(value, expected, field_name, *, stage):
    if value != expected or isinstance(value, bool):
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' must equal {expected}, got {value!r}",
            recovery_action=f"set '{field_name}' to {expected}",
        )


def _require_token_tuple(value, field_name, *, stage, allow_empty=False):
    if not isinstance(value, (list, tuple)):
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' must be an array, got {value!r}",
            recovery_action=f"set '{field_name}' to an array of lowercase tokens",
        )
    if not allow_empty and len(value) == 0:
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' must contain at least one item",
            recovery_action=f"add at least one token to '{field_name}'",
        )
    for item in value:
        if not isinstance(item, str) or not _TOKEN_PATTERN.fullmatch(item):
            raise Blocked(
                stage=stage,
                reason_code="malformed_checkpoint",
                detail=f"field '{field_name}' contains an invalid token {item!r}",
                recovery_action=f"use lowercase tokens matching {_TOKEN_PATTERN.pattern} in '{field_name}'",
            )
    return tuple(value)


_DATETIME_PATTERN = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"T(?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:\.\d+)?"
    r"(?P<offset>Z|[+-]\d{2}:\d{2})"
)


def _require_iso_datetime(value, field_name, *, stage):
    """Validate an RFC 3339 date-time with the same verdict on every
    supported interpreter.

    datetime.fromisoformat's accepted grammar is not stable across Python
    versions -- 3.11 started accepting a trailing 'Z' and other forms 3.10
    rejects -- so delegating the pass/fail verdict to it would make replay
    non-deterministic across machines running different 3.x releases. This
    validates against a fixed grammar with `re` instead (a 'T' time
    component and an explicit 'Z' or '+HH:MM'/'-HH:MM' offset are mandatory,
    so a bare date is rejected), then checks the calendar fields with the
    plain `datetime(year, month, day, hour, minute, second)` constructor,
    whose range validation has always been the same across Python 3.x
    because it does no string parsing at all.
    """
    _require_str(value, field_name, stage=stage)
    match = _DATETIME_PATTERN.fullmatch(value)
    if match is None:
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=(
                f"field '{field_name}' must be an RFC 3339 date-time with a 'T' "
                f"time component and a 'Z' or '+HH:MM'/'-HH:MM' offset, got {value!r}"
            ),
            recovery_action=f"set '{field_name}' to e.g. '2026-09-04T12:00:00Z'",
        )
    offset = match.group("offset")
    if offset != "Z" and (int(offset[1:3]) > 23 or int(offset[4:6]) > 59):
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' has an out-of-range UTC offset: {value!r}",
            recovery_action=f"set '{field_name}' to an offset between '-23:59' and '+23:59'",
        )
    try:
        datetime(
            int(match.group("year")), int(match.group("month")), int(match.group("day")),
            int(match.group("hour")), int(match.group("minute")), int(match.group("second")),
        )
    except ValueError as exc:
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' is not a real calendar date/time: {value!r} ({exc})",
            recovery_action=f"set '{field_name}' to a valid calendar date and time",
        ) from exc


# ---------------------------------------------------------------------------
# A narrow, auditable subset of JSON Schema (draft 2020-12): exactly the
# keywords schemas/envelope.schema.json uses. Not a general engine, and not
# reused beyond Envelope in this task.
# ---------------------------------------------------------------------------


def _matches_json_schema_type(instance, type_name):
    py_type = _JSON_SCHEMA_TYPES.get(type_name)
    if py_type is None:
        return True
    if type_name == "integer" and isinstance(instance, bool):
        return False
    if type_name == "boolean":
        return isinstance(instance, bool)
    return isinstance(instance, py_type)


def _schema_validate(instance, schema, *, stage, label="<root>"):
    if "const" in schema and (instance != schema["const"] or isinstance(instance, bool) != isinstance(schema["const"], bool)):
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{label}' must equal {schema['const']!r}, got {instance!r}",
            recovery_action=f"set '{label}' to {schema['const']!r}",
        )

    if "enum" in schema and instance not in schema["enum"]:
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{label}' has value {instance!r}, expected one of {schema['enum']}",
            recovery_action=f"set '{label}' to one of {schema['enum']}",
        )

    schema_type = schema.get("type")
    if schema_type is not None:
        allowed_types = schema_type if isinstance(schema_type, list) else [schema_type]
        if not any(_matches_json_schema_type(instance, one) for one in allowed_types):
            raise Blocked(
                stage=stage,
                reason_code="malformed_checkpoint",
                detail=f"field '{label}' must be of type {allowed_types}, got {type(instance).__name__}",
                recovery_action=f"set '{label}' to a value of type {allowed_types}",
            )

    if isinstance(instance, str) and "pattern" in schema and not re.fullmatch(schema["pattern"], instance):
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{label}' does not match pattern {schema['pattern']!r}: {instance!r}",
            recovery_action=f"match '{label}' to pattern {schema['pattern']!r}",
        )

    if isinstance(instance, str) and schema.get("format") == "date-time":
        _require_iso_datetime(instance, label, stage=stage)

    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [name for name in required if name not in instance]
        if missing:
            raise Blocked(
                stage=stage,
                reason_code="malformed_checkpoint",
                detail=f"missing required field(s): {', '.join(missing)}",
                recovery_action="supply every required field before retrying",
            )
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(key for key in instance if key not in properties)
            if extra:
                raise Blocked(
                    stage=stage,
                    reason_code="malformed_checkpoint",
                    detail=f"unexpected field(s) not allowed by schema: {', '.join(extra)}",
                    recovery_action="remove fields not defined by the schema",
                )
        for key, subschema in properties.items():
            if key in instance:
                _schema_validate(instance[key], subschema, stage=stage, label=key)

    if isinstance(instance, (list, tuple)) and "items" in schema:
        for index, item in enumerate(instance):
            _schema_validate(item, schema["items"], stage=stage, label=f"{label}[{index}]")

    return instance


@lru_cache(maxsize=None)
def _load_envelope_schema():
    return load_json_file(ENVELOPE_SCHEMA_PATH, stage="envelope")


def _canonical_json(data):
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


# ---------------------------------------------------------------------------
# RunSpec
# ---------------------------------------------------------------------------

_RUN_SPEC_REQUIRED = ("schema_version", "run_id", "goal", "created_at")


@dataclass(frozen=True)
class RunSpec:
    """Vendor-neutral identity and objective of one run.

    The generated task DAG and the run's roster of AgentSpec records are
    separate, parallel inputs to the Orchestrator (see the ADR 0014
    diagram) rather than fields nested inside RunSpec; that generation is a
    later task in this outcome.
    """

    schema_version: int
    run_id: str
    goal: str
    created_at: str

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise Blocked(
                stage="run_spec",
                reason_code="malformed_checkpoint",
                detail=f"RunSpec must be a JSON object, got {type(data).__name__}",
                recovery_action="pass a JSON object with every RunSpec field",
            )
        require_fields(data, _RUN_SPEC_REQUIRED, stage="run_spec")
        _require_const_int(data["schema_version"], SCHEMA_VERSION, "schema_version", stage="run_spec")
        _require_identifier(data["run_id"], "run_id", stage="run_spec")
        _require_str(data["goal"], "goal", stage="run_spec")
        _require_iso_datetime(data["created_at"], "created_at", stage="run_spec")
        return cls(
            schema_version=SCHEMA_VERSION,
            run_id=data["run_id"],
            goal=data["goal"],
            created_at=data["created_at"],
        )

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "goal": self.goal,
            "created_at": self.created_at,
        }

    def to_json(self):
        return _canonical_json(self.to_dict())


# ---------------------------------------------------------------------------
# AgentSpec
# ---------------------------------------------------------------------------

_AGENT_SPEC_REQUIRED = (
    "schema_version", "agent_id", "role", "capabilities", "tools",
    "output_schema", "model_tier", "reasoning_effort",
)


@dataclass(frozen=True)
class AgentSpec:
    """One generated, isolated execution-agent role.

    `capabilities` and `tools` are abstract tokens the workflow generator
    assigns; `model_tier`/`reasoning_effort` are tiers, not model ids. An
    adapter (a later outcome) compiles all four to host-native settings.
    """

    schema_version: int
    agent_id: str
    role: str
    capabilities: tuple
    tools: tuple
    output_schema: str
    model_tier: str
    reasoning_effort: str

    def __post_init__(self):
        object.__setattr__(self, "capabilities", tuple(self.capabilities))
        object.__setattr__(self, "tools", tuple(self.tools))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise Blocked(
                stage="agent_spec",
                reason_code="malformed_checkpoint",
                detail=f"AgentSpec must be a JSON object, got {type(data).__name__}",
                recovery_action="pass a JSON object with every AgentSpec field",
            )
        require_fields(data, _AGENT_SPEC_REQUIRED, stage="agent_spec")
        _require_const_int(data["schema_version"], SCHEMA_VERSION, "schema_version", stage="agent_spec")
        _require_identifier(data["agent_id"], "agent_id", stage="agent_spec")
        _require_identifier(data["role"], "role", stage="agent_spec")
        capabilities = _require_token_tuple(data["capabilities"], "capabilities", stage="agent_spec")
        tools = _require_token_tuple(data["tools"], "tools", stage="agent_spec", allow_empty=True)
        _require_str(data["output_schema"], "output_schema", stage="agent_spec")
        require_enum(data["model_tier"], MODEL_TIERS, "model_tier", stage="agent_spec")
        require_enum(data["reasoning_effort"], REASONING_EFFORTS, "reasoning_effort", stage="agent_spec")
        return cls(
            schema_version=SCHEMA_VERSION,
            agent_id=data["agent_id"],
            role=data["role"],
            capabilities=capabilities,
            tools=tools,
            output_schema=data["output_schema"],
            model_tier=data["model_tier"],
            reasoning_effort=data["reasoning_effort"],
        )

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "agent_id": self.agent_id,
            "role": self.role,
            "capabilities": list(self.capabilities),
            "tools": list(self.tools),
            "output_schema": self.output_schema,
            "model_tier": self.model_tier,
            "reasoning_effort": self.reasoning_effort,
        }

    def to_json(self):
        return _canonical_json(self.to_dict())


# ---------------------------------------------------------------------------
# TaskNode and TaskDag
# ---------------------------------------------------------------------------

_TASK_NODE_REQUIRED = ("task_id", "role", "depends_on")


def _require_identifier_tuple(value, field_name, *, stage, allow_empty=False):
    """Validate a list/tuple of identifiers (like task_ids in depends_on)."""
    if not isinstance(value, (list, tuple)):
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' must be an array, got {value!r}",
            recovery_action=f"set '{field_name}' to an array of identifiers",
        )
    if not allow_empty and len(value) == 0:
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' must contain at least one item",
            recovery_action=f"add at least one identifier to '{field_name}'",
        )
    for index, item in enumerate(value):
        _require_identifier(item, f"{field_name}[{index}]", stage=stage)
    return tuple(value)


@dataclass(frozen=True)
class TaskNode:
    """One node in a generated task DAG.

    `depends_on` is a tuple of task_ids that must complete before this
    task can be scheduled.
    """

    task_id: str
    role: str
    depends_on: tuple

    def __post_init__(self):
        object.__setattr__(self, "depends_on", tuple(self.depends_on))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise Blocked(
                stage="task_node",
                reason_code="malformed_checkpoint",
                detail=f"TaskNode must be a JSON object, got {type(data).__name__}",
                recovery_action="pass a JSON object with every TaskNode field",
            )
        require_fields(data, _TASK_NODE_REQUIRED, stage="task_node")
        _require_identifier(data["task_id"], "task_id", stage="task_node")
        _require_identifier(data["role"], "role", stage="task_node")
        depends_on = _require_identifier_tuple(data["depends_on"], "depends_on", stage="task_node", allow_empty=True)
        return cls(
            task_id=data["task_id"],
            role=data["role"],
            depends_on=depends_on,
        )

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))

    def to_dict(self):
        return {
            "task_id": self.task_id,
            "role": self.role,
            "depends_on": list(self.depends_on),
        }

    def to_json(self):
        return _canonical_json(self.to_dict())


@dataclass(frozen=True)
class TaskDag:
    """A directed acyclic graph of task nodes.

    The tasks field is a tuple of TaskNode; accessing it by index is
    stable and the tuple itself is immutable. Validation ensures: no
    duplicate task_ids, no unknown dependencies, and no cycles.
    """

    tasks: tuple

    def __post_init__(self):
        object.__setattr__(self, "tasks", tuple(self.tasks))

    @classmethod
    def from_list(cls, data):
        if not isinstance(data, list):
            raise Blocked(
                stage="task_dag",
                reason_code="malformed_checkpoint",
                detail=f"TaskDag must be a list, got {type(data).__name__}",
                recovery_action="pass a list of task node objects",
            )

        nodes = []
        task_ids = set()
        for item in data:
            node = TaskNode.from_dict(item)
            if node.task_id in task_ids:
                raise Blocked(
                    stage="task_dag",
                    reason_code="malformed_checkpoint",
                    detail=f"duplicate task_id: {node.task_id!r}",
                    recovery_action=f"ensure every task_id in the DAG is unique",
                )
            task_ids.add(node.task_id)
            nodes.append(node)

        # Validate: all dependencies reference known task_ids
        for node in nodes:
            for dep in node.depends_on:
                if dep not in task_ids:
                    raise Blocked(
                        stage="task_dag",
                        reason_code="malformed_checkpoint",
                        detail=f"task '{node.task_id}' depends on unknown task '{dep}'",
                        recovery_action=f"ensure all task_ids referenced in depends_on exist in the DAG",
                    )

        # Validate: no cycles using DFS
        _check_dag_acyclic(nodes)

        return cls(tasks=tuple(nodes))

    @classmethod
    def from_json(cls, text):
        return cls.from_list(json.loads(text))

    def to_list(self):
        return [node.to_dict() for node in self.tasks]

    def to_json(self):
        return _canonical_json(self.to_list())


def _check_dag_acyclic(nodes):
    """Verify a list of TaskNode has no cycles.

    Three-colour DFS -- white (unvisited), gray (on the current path),
    black (fully processed) -- with a back edge to a gray node reported as
    a cycle, same as a textbook recursive implementation. The traversal
    itself is iterative with an explicit stack, not Python-level
    recursion: a recursive visit() puts one call frame on the interpreter
    stack per edge, so a long mostly-linear pipeline (exactly what a DAG
    generator emits) could raise a bare RecursionError instead of Blocked,
    with the exact threshold depending on sys.getrecursionlimit() and on
    input ordering -- the same logical DAG could pass on one host and
    crash on another. An explicit stack has no such limit; it is bounded
    by heap memory, not call depth.
    """
    task_map = {node.task_id: node for node in nodes}
    color = {node.task_id: "white" for node in nodes}

    for start in nodes:
        if color[start.task_id] != "white":
            continue

        # Each stack frame is (task_id, iterator over its remaining
        # dependencies, path of ancestors leading to task_id) -- this
        # triple is exactly what a recursive visit(task_id, path) call
        # would have held in its local variables and the interpreter's
        # call stack; here it lives on an explicit Python list instead.
        stack = [(start.task_id, iter(task_map[start.task_id].depends_on), [])]
        color[start.task_id] = "gray"

        while stack:
            task_id, dep_iter, path = stack[-1]
            dep = next(dep_iter, None)
            # depends_on entries are always non-empty validated
            # identifiers (see TaskNode.from_dict), so None can only mean
            # the iterator over this node's dependencies is exhausted.
            if dep is None:
                color[task_id] = "black"
                stack.pop()
                continue

            if color[dep] == "gray":
                raise Blocked(
                    stage="task_dag",
                    reason_code="malformed_checkpoint",
                    detail=(
                        f"cycle detected in task DAG: "
                        f"{' -> '.join(path + [task_id, dep])}"
                    ),
                    recovery_action="restructure the task DAG to eliminate the cycle",
                )
            if color[dep] == "black":
                continue

            color[dep] = "gray"
            stack.append((dep, iter(task_map[dep].depends_on), path + [task_id]))


# ---------------------------------------------------------------------------
# Envelope
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Envelope:
    """One hand-off appended to a run's mailbox.

    Validated directly against schemas/envelope.schema.json in from_dict, so
    this record and that file cannot silently drift apart. Legal
    sender/recipient pairing is a router concern (a later task), not
    enforced here.
    """

    schema_version: int
    envelope_id: str
    run_id: str
    sender: str
    recipient: str
    kind: str
    payload: object
    created_at: str

    def __post_init__(self):
        object.__setattr__(self, "payload", freeze(self.payload))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict):
            raise Blocked(
                stage="envelope",
                reason_code="malformed_checkpoint",
                detail=f"Envelope must be a JSON object, got {type(data).__name__}",
                recovery_action="pass a JSON object matching schemas/envelope.schema.json",
            )
        schema = _load_envelope_schema()
        _schema_validate(data, schema, stage="envelope")
        return cls(
            schema_version=data["schema_version"],
            envelope_id=data["envelope_id"],
            run_id=data["run_id"],
            sender=data["sender"],
            recipient=data["recipient"],
            kind=data["kind"],
            payload=data["payload"],
            created_at=data["created_at"],
        )

    @classmethod
    def from_json(cls, text):
        return cls.from_dict(json.loads(text))

    def to_dict(self):
        return {
            "schema_version": self.schema_version,
            "envelope_id": self.envelope_id,
            "run_id": self.run_id,
            "sender": self.sender,
            "recipient": self.recipient,
            "kind": self.kind,
            "payload": thaw(self.payload),
            "created_at": self.created_at,
        }

    def to_json(self):
        return _canonical_json(self.to_dict())
