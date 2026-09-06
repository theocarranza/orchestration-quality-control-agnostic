"""compile_prompt.py — the deterministic brief compiler: scripts/compile_prompt.py.

This is the Outcome 2 Task 5 slice of
AI_Codex/Architecture/ADR/0014-generated-workflow-deterministic-kernel.md,
decision 0: "Deterministic code -- not an agent -- decides what runs next,
compiles each agent's brief, gates every result, counts attempts...".
`compile_brief` is that brief compiler: a pure function of
(task_node, agent_spec, critique, attempt) that returns the plain mapping
an `adapter_port.AdapterPort.spawn` call puts on a 'request' envelope's
`payload['brief']`.

Deterministic and byte-stable. The same four inputs always produce an
equal dict, and `json.dumps(brief, sort_keys=True)` on two separately
compiled-but-equal-input briefs is byte-identical: every field here is a
plain str/int/list/None copied straight from an already-validated
`kernel_specs.TaskNode`/`kernel_specs.AgentSpec` (themselves built from
sorted/ordered tuples), and nothing in this module reads a clock, a
random source, or any host-specific setting.

Vendor-neutral by construction. `AgentSpec.capabilities`/`tools` are
abstract tokens the workflow generator assigned and
`model_tier`/`reasoning_effort` are tiers drawn from the closed
vocabularies `kernel_specs.MODEL_TIERS`/`REASONING_EFFORTS` -- never a
host name or a model id. `compile_brief` only ever copies these fields
through unchanged, so a compiled brief can carry no more vendor
vocabulary than the `AgentSpec` it was compiled from already carried,
and `AgentSpec.from_dict` already refuses to construct one outside that
closed vocabulary in the first place (see kernel_specs.py). No host name,
model id, or other vendor token is introduced by this module.

`critique` is threaded through unchanged and always as an explicit
'critique' key -- None on a first attempt or a passing one, the exact
non-empty string a prior `gate.gate_result` verdict produced otherwise --
never omitted. This is the mechanism `gate.retry_or_block`'s contract
depends on ("a failed gate carries its critique into the next attempt")
and the one Outcome 2 Task 4's Fixture A evidence exercises: the second
attempt's compiled brief must carry the first attempt's critique. The
key's *presence*, not merely its value, is the load-bearing half of that
guarantee -- a caller inspecting `brief["critique"]` must never hit a
`KeyError` on a passing or first attempt, exactly mirroring
`fake_adapter.py`'s own `brief={"critique": None}` convention.
"""

from kernel_specs import AgentSpec, TaskNode
from qc_lib import Blocked

STAGE = "compile_prompt"


def _require_task_node(task_node):
    if not isinstance(task_node, TaskNode):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"task_node must be a kernel_specs.TaskNode, got {type(task_node).__name__}",
            recovery_action="pass the TaskNode this brief is being compiled for",
        )


def _require_agent_spec(agent_spec):
    if not isinstance(agent_spec, AgentSpec):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"agent_spec must be a kernel_specs.AgentSpec, got {type(agent_spec).__name__}",
            recovery_action="pass the AgentSpec assigned to this task's role",
        )


def _require_matching_role(task_node, agent_spec):
    # A brief compiled from a mismatched (task_node, agent_spec) pair
    # would silently hand a task to the wrong role's capabilities/tools/
    # output_schema -- caught here rather than left to whatever the
    # worker eventually does with a brief that lied about its own role.
    if task_node.role != agent_spec.role:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=(
                f"task {task_node.task_id!r} has role {task_node.role!r} but "
                f"agent_spec {agent_spec.agent_id!r} has role {agent_spec.role!r}"
            ),
            recovery_action="pass the AgentSpec whose role matches this task node's role",
        )


def _require_attempt(attempt):
    # Attempts are 1-indexed everywhere else in this kernel (see
    # run_state.py's sequential-attempt validation), so a brief's own
    # attempt field must agree: 0 or negative can never be a real attempt.
    if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"attempt must be a positive integer, got {attempt!r}",
            recovery_action="pass attempt >= 1",
        )


def _require_critique(critique):
    # Presence, not truthiness, mirrors gate.gate_result's own guard: an
    # explicitly-passed empty or whitespace-only critique is not an
    # explanation any more than a missing one is, so it is rejected the
    # same way rather than silently accepted as "no critique".
    if critique is not None and (not isinstance(critique, str) or not critique.strip()):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"critique must be None or a non-empty string, got {critique!r}",
            recovery_action="pass None, or the non-empty critique a prior gate_result verdict produced",
        )


def compile_brief(task_node, agent_spec, critique=None, attempt=1):
    """Compile the deterministic brief for one attempt of one task.

    `task_node` is the `kernel_specs.TaskNode` being attempted;
    `agent_spec` is the `kernel_specs.AgentSpec` generated for that node's
    role. `critique` (default None) is the non-empty string a prior
    `gate.gate_result` verdict produced for the immediately preceding
    failed attempt on this task, or None on a first attempt. `attempt`
    (default 1) is the 1-indexed attempt number this brief is being
    compiled for.

    Returns a plain dict -- not frozen. Freezing happens exactly once,
    at the `kernel_specs.Envelope` boundary this brief is eventually
    embedded in (via `payload['brief']`), which already recursively
    freezes its whole payload in `__post_init__`; freezing here too would
    be a second, redundant immutability mechanism rather than a reuse of
    the one `qc_lib.freeze` already provides at that boundary.
    """
    _require_task_node(task_node)
    _require_agent_spec(agent_spec)
    _require_matching_role(task_node, agent_spec)
    _require_attempt(attempt)
    _require_critique(critique)

    return {
        "task_id": task_node.task_id,
        "role": agent_spec.role,
        "agent_id": agent_spec.agent_id,
        "attempt": attempt,
        "capabilities": list(agent_spec.capabilities),
        "tools": list(agent_spec.tools),
        "output_schema": agent_spec.output_schema,
        "model_tier": agent_spec.model_tier,
        "reasoning_effort": agent_spec.reasoning_effort,
        "critique": critique,
    }
