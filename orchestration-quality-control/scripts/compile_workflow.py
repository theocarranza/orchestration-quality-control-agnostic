"""compile_workflow.py -- the deterministic validation and compilation boundary.

This is the Outcome 2 Task 6 slice of
AI_Codex/Architecture/ADR/0014-generated-workflow-deterministic-kernel.md,
decision 1: "What is generated from discovery and the interview is the task
DAG, the roles, their capabilities, their tools, their output schemas, and
their model/reasoning tiers." `compile_workflow(decisions)` is that
generator: a pure function from accepted discovery/interview decisions to
three sibling artifacts --

  * a `kernel_specs.RunSpec` (run identity and objective)
  * a generated `kernel_specs.TaskDag`
  * generated `kernel_specs.AgentSpec` records, one per role the DAG names

-- returned together as one `CompiledWorkflow`, never nested inside one
another (ADR 0014's diagram and Outcome 2 Task 1 both treat RunSpec, the
DAG and the AgentSpec roster as parallel inputs to the Orchestrator, not a
tree with one root).

Where `decisions` comes from. `plan_interview.plan(brief)` and
`gate_defaults.author_fields(brief, overrides)` decide which interview
fields to ask, skip, or default (see those modules) -- that decision-making
is explicitly out of scope here and is reused, not reimplemented.
`decisions` is what root/interviewer has *after* that interview
concludes: the packaged-default fields `gate_defaults.author_fields`
returns (`output_root`, `profile`, `language`, `shape`, `approval`,
`state`, `stop`, `named_inputs`, `outcome_involves_test_tree`, `intent`),
plus the one field `plan_interview.plan` always asks a human for
(`outcome`, `plan()`'s `always_ask`), plus this run's identity
(`run_id`, `created_at`) -- both of which are a live run's own concern
(assigned once, by whatever session starts the run), not an interview
decision, and so are never derived from a clock or any other source of
variation *inside* this module. `compile_workflow` only ever consumes
these fields; the ones it does not consume (`output_root`, `language`,
`state`, `stop`, `approval`, `intent`) belong to a later authoring gate
and are ignored here rather than rejected, so this module never has to
mirror gate_defaults's own field list to stay in sync with it. See
tests/test_compile_workflow.py for fixtures built by literally calling
`gate_defaults.author_fields` rather than hand-rolling an equivalent shape.

Two workflow shapes, generated deterministically from `decisions["shape"]`:

  * "single-agent" -- one task, role "author", no dependencies. If
    `decisions["outcome_involves_test_tree"]` is true, a second task, role
    "verify", is appended depending on the first -- the two-task dependent
    DAG the master plan's Outcome 2 exit evidence names (a classified
    failure carries its critique into a passing retry, the dependent task
    then runs, and the run reaches `completed`).
  * "isolated-workers" -- one independent task per entry in
    `decisions["named_inputs"]`, each with its own role
    (`author-<named_input>`) and no dependency on any other -- these are
    genuinely parallel, independent branches, not a re-shaped dependent
    chain. If `outcome_involves_test_tree` is true, one more "verify" task
    is appended depending on *every* author task (fan-out, then fan-in).

`shape` and `named_inputs` must agree: "single-agent" forbids named
inputs (there is only one task to isolate anything by) and
"isolated-workers" requires at least one (there is nothing to isolate
otherwise). Either mismatch is a contradiction in `decisions`, rejected by
`_require_consistent_shape` below before any spec is built -- see that
function's docstring for why this, and not either half alone, is the
right place to catch it.

Every identifier this module derives (task_id, role, agent_id) is handed
straight to `kernel_specs.TaskNode.from_dict` / `kernel_specs.AgentSpec.from_dict`
/ `kernel_specs.RunSpec.from_dict`, which already validate the exact
identifier grammar, token grammar, and RFC 3339 timestamp grammar this
kernel uses everywhere else. This module does not re-implement any of
that shape-checking -- doing so would be a second, divergent copy of
validation `kernel_specs.py` already owns; deferring to it instead means
a malformed `run_id`, `created_at`, `outcome` (RunSpec's `goal`),
`named_inputs` entry, or `outcome_involves_test_tree`-driven role name is
still rejected with `qc_lib.Blocked` naming the offending field, just by
the module that already owns that grammar.

Vendor-neutral by construction (ADR 0014 decision 5). `model_tier` and
`reasoning_effort` are fixed, explicit members of
`kernel_specs.MODEL_TIERS` / `REASONING_EFFORTS` -- never a host name, a
model id, or `"inherit"` (which is not even a member of either tuple, so
`kernel_specs.AgentSpec.from_dict` would reject it outright if this module
ever tried). `capabilities` are abstract tokens
(`"author"`/`"verify"`/`"pipeline"`) this module assigns from
`decisions["profile"]`, never a vendor capability name.

Deterministic and model-free. No network call, no LLM call, no clock
read, no random source anywhere in this module -- run identity
(`run_id`/`created_at`) is threaded through from `decisions` exactly as
given, never generated here. Iteration order is always the caller-supplied
`named_inputs` list order (never a `set`, whose iteration order is not a
language guarantee), and duplicate roles collapse via `dict.fromkeys`,
whose insertion-order-preserving behaviour is itself a language guarantee
(CPython 3.7+/the language spec since 3.7), not an implementation detail
this module happens to rely on. Two calls to `compile_workflow` with equal
`decisions` therefore always produce byte-identical
`RunSpec.to_json()`/`TaskDag.to_json()`/`AgentSpec.to_json()` output --
see tests/test_compile_workflow.py's `DeterminismTest` and its paired
break-it drill.

A caller never receives a half-built workflow. Every raised `qc_lib.Blocked`
below happens before `CompiledWorkflow(...)` is ever constructed, and
`compile_workflow` has no side effects (no mailbox append, no file write, no
module-level mutable state) an aborted call could have left behind, so a
`Blocked` exception is the only externally visible outcome of a rejected
call -- there is no partial `RunSpec`/`TaskDag`/`AgentSpec` a caller could
still reach after catching it.
"""

from dataclasses import dataclass

from kernel_specs import AgentSpec, RunSpec, SCHEMA_VERSION, TaskDag
from qc_lib import Blocked, freeze, require_enum, require_fields

STAGE = "compile_workflow"

SHAPES = ("single-agent", "isolated-workers")
PROFILES = ("core", "example-pipeline")

AUTHOR_ROLE_KIND = "author"
VERIFY_ROLE_KIND = "verify"

_MODEL_TIER = "medium"
_REASONING_EFFORT = "medium"

# compile_workflow's own required subset of `decisions`. Everything else a
# real `decisions` mapping carries (output_root, language, state, stop,
# approval, intent -- see gate_defaults.author_fields) is a later
# authoring-gate concern this module never reads, so it is neither
# required nor rejected here.
_REQUIRED_DECISION_FIELDS = (
    "run_id",
    "created_at",
    "outcome",
    "shape",
    "named_inputs",
    "outcome_involves_test_tree",
    "profile",
)

# capabilities assigned per role kind; "example-pipeline" adds one more
# token on top, so the *profile* alone can change the emitted AgentSpec
# manifest without touching the DAG at all.
_BASE_CAPABILITIES = {
    AUTHOR_ROLE_KIND: ("author",),
    VERIFY_ROLE_KIND: ("verify",),
}
_PROFILE_EXTRA_CAPABILITY = {
    "core": (),
    "example-pipeline": ("pipeline",),
}

_OUTPUT_SCHEMA = "schemas/worker-result.schema.json"


@dataclass(frozen=True)
class CompiledWorkflow:
    """The three sibling artifacts `compile_workflow` emits.

    `agent_specs` is a frozen mapping from role (matching
    `kernel_specs.TaskNode.role`) to the `kernel_specs.AgentSpec` generated
    for that role -- exactly the shape `oqc.drive`'s own `agent_specs`
    parameter already expects, so a caller wires this straight in:
    `drive(compiled.task_dag, adapter, mailbox, compiled.agent_specs,
    max_attempts, run_id=compiled.run_spec.run_id)`. `RunSpec` already
    carries the run's identity; `run_id` is read from it rather than
    threaded through as a second, independent source (see the "Decisions
    Task 6 must honour" note this module's tests are built against).

    Frozen and holding a frozen mapping so a caller cannot mutate one
    compiled workflow's agent roster into another's -- the same
    immutability discipline `kernel_specs`'s own records already apply to
    themselves.
    """

    run_spec: RunSpec
    task_dag: TaskDag
    agent_specs: object

    def __post_init__(self):
        object.__setattr__(self, "agent_specs", freeze(dict(self.agent_specs)))


def _require_mapping(decisions):
    if not hasattr(decisions, "get") or not hasattr(decisions, "__getitem__"):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"decisions must be a mapping, got {type(decisions).__name__}",
            recovery_action="pass a mapping of accepted discovery/interview decisions",
        )


def _require_bool(value, field_name):
    if not isinstance(value, bool):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"field '{field_name}' must be a boolean, got {value!r}",
            recovery_action=f"set '{field_name}' to true or false",
        )


def _require_named_inputs(value):
    if not isinstance(value, (list, tuple)):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"field 'named_inputs' must be an array, got {value!r}",
            recovery_action="set 'named_inputs' to an array of identifier strings",
        )
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item:
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"field 'named_inputs[{index}]' must be a non-empty string, got {item!r}",
                recovery_action="use only non-empty strings in 'named_inputs'",
            )
    return list(value)


def _require_consistent_shape(shape, named_inputs):
    """Reject a `(shape, named_inputs)` pair that contradicts itself.

    Neither half is malformed on its own -- `shape` is a valid member of
    SHAPES and `named_inputs` is a valid array of identifiers -- so this
    check cannot live inside either field's own validator; it exists
    because the *combination* is what is contradictory. "single-agent"
    names exactly one task, so there is nothing for a named input to
    isolate: a non-empty list here would silently be ignored by the
    "single-agent" branch below if this check did not exist, which is
    exactly the kind of "malformed or contradictory decisions must raise
    Blocked ... before any spec is emitted" case this module exists to
    catch rather than paper over. "isolated-workers" is the opposite
    problem: it names one task *per* named input, so an empty list would
    generate a DAG with no author task at all.
    """
    if shape == "single-agent" and named_inputs:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=(
                "decisions are contradictory: shape 'single-agent' names "
                f"exactly one task, but named_inputs is non-empty ({named_inputs!r})"
            ),
            recovery_action=(
                "clear 'named_inputs', or set shape to 'isolated-workers' to "
                "generate one isolated task per named input"
            ),
        )
    if shape == "isolated-workers" and not named_inputs:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=(
                "decisions are contradictory: shape 'isolated-workers' generates "
                "one task per entry in 'named_inputs', but 'named_inputs' is empty"
            ),
            recovery_action=(
                "add at least one entry to 'named_inputs', or set shape to "
                "'single-agent'"
            ),
        )


def _capabilities_for(role_kind, profile):
    return _BASE_CAPABILITIES[role_kind] + _PROFILE_EXTRA_CAPABILITY[profile]


def _build_topology(shape, named_inputs, outcome_involves_test_tree):
    """Return `(task_dicts, role_kind_by_role)`, in deterministic order.

    `task_dicts` is a plain list of the mappings `kernel_specs.TaskDag.from_list`
    accepts; `role_kind_by_role` maps every role name this topology names to
    either AUTHOR_ROLE_KIND or VERIFY_ROLE_KIND, so the caller can assign
    the right capability set to each generated AgentSpec without
    re-deriving role kind from a role name's own spelling.
    """
    tasks = []
    role_kind_by_role = {}
    author_task_ids = []

    if shape == "single-agent":
        task_id, role = "task-author", "author"
        tasks.append({"task_id": task_id, "role": role, "depends_on": []})
        role_kind_by_role[role] = AUTHOR_ROLE_KIND
        author_task_ids.append(task_id)
    else:
        for named_input in named_inputs:
            task_id = f"task-{named_input}"
            role = f"author-{named_input}"
            tasks.append({"task_id": task_id, "role": role, "depends_on": []})
            role_kind_by_role[role] = AUTHOR_ROLE_KIND
            author_task_ids.append(task_id)

    if outcome_involves_test_tree:
        verify_role = "verify"
        tasks.append({
            "task_id": "task-verify",
            "role": verify_role,
            "depends_on": list(author_task_ids),
        })
        role_kind_by_role[verify_role] = VERIFY_ROLE_KIND

    return tasks, role_kind_by_role


def compile_workflow(decisions):
    """Compile accepted discovery/interview `decisions` into a `CompiledWorkflow`.

    Raises `qc_lib.Blocked` naming the offending field for any missing,
    malformed, or self-contradictory decision, before any of the three
    artifacts is built. See the module docstring for exactly which fields
    are required and how `shape` drives the generated topology.
    """
    _require_mapping(decisions)
    require_fields(decisions, _REQUIRED_DECISION_FIELDS, stage=STAGE)

    shape = decisions["shape"]
    require_enum(shape, SHAPES, "shape", stage=STAGE)

    profile = decisions["profile"]
    require_enum(profile, PROFILES, "profile", stage=STAGE)

    outcome_involves_test_tree = decisions["outcome_involves_test_tree"]
    _require_bool(outcome_involves_test_tree, "outcome_involves_test_tree")

    named_inputs = _require_named_inputs(decisions["named_inputs"])

    _require_consistent_shape(shape, named_inputs)

    # RunSpec.from_dict validates run_id/created_at/outcome (as `goal`)
    # against kernel_specs' own identifier/timestamp/non-empty-string
    # grammar -- reused here rather than re-implemented.
    run_spec = RunSpec.from_dict({
        "schema_version": SCHEMA_VERSION,
        "run_id": decisions["run_id"],
        "goal": decisions["outcome"],
        "created_at": decisions["created_at"],
    })

    task_dicts, role_kind_by_role = _build_topology(shape, named_inputs, outcome_involves_test_tree)

    # TaskDag.from_list validates identifiers, rejects duplicate task_ids,
    # unknown dependencies, and cycles -- all reused, not re-implemented.
    task_dag = TaskDag.from_list(task_dicts)

    agent_specs = {}
    # dict.fromkeys over role_kind_by_role preserves the insertion order
    # _build_topology produced (itself the deterministic order named_inputs
    # was given in), so this loop's output order never depends on a set or
    # on dict-hash iteration order.
    for role in role_kind_by_role:
        role_kind = role_kind_by_role[role]
        agent_specs[role] = AgentSpec.from_dict({
            "schema_version": SCHEMA_VERSION,
            "agent_id": f"agent-{role}",
            "role": role,
            "capabilities": list(_capabilities_for(role_kind, profile)),
            "tools": [],
            "output_schema": _OUTPUT_SCHEMA,
            "model_tier": _MODEL_TIER,
            "reasoning_effort": _REASONING_EFFORT,
        })

    return CompiledWorkflow(run_spec=run_spec, task_dag=task_dag, agent_specs=agent_specs)
