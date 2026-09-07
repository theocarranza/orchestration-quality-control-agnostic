"""Immutable, vendor-neutral input contract for one Orchestrator run."""

import json
from dataclasses import dataclass
from types import MappingProxyType

from compile_workflow import CompiledWorkflow
from kernel_specs import AgentSpec, RunSpec, SCHEMA_VERSION, TaskDag
from qc_lib import Blocked, freeze, thaw

STAGE = "orchestrator_contract"
_CONTROL_ITEMS = (
    ("engine", "The deterministic engine owns scheduling, brief compilation, validation, gating, retries, phase transitions, and stopping."),
    ("root", "Root remains passive after the single Orchestrator delegation, except for receiving results or relaying an engine-declared question."),
    ("isolation", "Workers address only the Orchestrator; workers never address root or another worker."),
    ("relay", "Only the Orchestrator relays worker questions and results to root; the Orchestrator cannot rewrite the mailbox and cannot mutate state."),
)
_CONTROL_INSTRUCTIONS = MappingProxyType(dict(_CONTROL_ITEMS))
# Retain the named constant as an immutable view for callers that inspect it.
CONTROL_INSTRUCTIONS = _CONTROL_INSTRUCTIONS


def _blocked(detail):
    raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail=detail,
                  recovery_action="provide a valid Orchestrator contract")


def _budget(value):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        _blocked(f"max_attempts must be a positive integer, got {value!r}")


@dataclass(frozen=True)
class OrchestratorContract:
    run_spec: RunSpec
    task_dag: TaskDag
    agent_specs: object
    max_attempts: int
    control_instructions: object

    def __post_init__(self):
        _budget(self.max_attempts)
        if self.control_instructions != _CONTROL_INSTRUCTIONS:
            _blocked("canonical control instructions were changed")
        try:
            run = RunSpec.from_dict(self.run_spec.to_dict())
            dag = TaskDag.from_list(self.task_dag.to_list())
            raw_specs = dict(self.agent_specs)
            specs = {key: AgentSpec.from_dict(value.to_dict())
                     for key, value in raw_specs.items()}
        except Blocked:
            raise
        except (AttributeError, TypeError, ValueError) as exc:
            _blocked(f"invalid contract records: {exc}")
        if len({spec.agent_id for spec in specs.values()}) != len(specs):
            _blocked("agent ids must be unique")
        roles = {node.role for node in dag.tasks}
        if set(specs) != roles:
            _blocked("agent role map must exactly cover DAG roles")
        if any(key != spec.role for key, spec in specs.items()):
            _blocked("role map key must equal spec.role")
        object.__setattr__(self, "run_spec", run)
        object.__setattr__(self, "task_dag", dag)
        object.__setattr__(self, "agent_specs", freeze(specs))
        object.__setattr__(self, "control_instructions", freeze(dict(_CONTROL_INSTRUCTIONS)))

    def to_dict(self):
        return {"run_spec": self.run_spec.to_dict(), "task_dag": self.task_dag.to_list(),
                "agent_specs": {k: v.to_dict() for k, v in self.agent_specs.items()},
                "max_attempts": self.max_attempts, "control_instructions": thaw(self.control_instructions)}

    def to_json(self):
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data):
        if not isinstance(data, dict): _blocked("contract must be an object")
        for key in ("run_spec", "task_dag", "agent_specs", "max_attempts", "control_instructions"):
            if key not in data: _blocked(f"missing field: {key}")
        run = RunSpec.from_dict(data["run_spec"])
        dag = TaskDag.from_list(data["task_dag"])
        if not isinstance(data["agent_specs"], dict): _blocked("agent_specs must be an object")
        specs = {key: AgentSpec.from_dict(value) for key, value in data["agent_specs"].items()}
        if len({spec.agent_id for spec in specs.values()}) != len(specs): _blocked("agent ids must be unique")
        roles = {node.role for node in dag.tasks}
        if set(specs) != roles: _blocked("agent role map must exactly cover DAG roles")
        if any(key != spec.role for key, spec in specs.items()): _blocked("role map key must equal spec.role")
        _budget(data["max_attempts"])
        if data["control_instructions"] != _CONTROL_INSTRUCTIONS: _blocked("canonical control instructions were changed")
        return cls(run, dag, specs, data["max_attempts"], _CONTROL_INSTRUCTIONS)

    @classmethod
    def from_json(cls, text):
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError) as exc:
            _blocked(f"invalid contract JSON: {exc}")
        return cls.from_dict(data)


def compile_orchestrator(compiled, max_attempts):
    if not isinstance(compiled, CompiledWorkflow): _blocked("compiled must be a CompiledWorkflow")
    _budget(max_attempts)
    # Reparse serialized records: direct dataclass construction cannot bypass validation.
    run = RunSpec.from_dict(compiled.run_spec.to_dict())
    dag = TaskDag.from_list(compiled.task_dag.to_list())
    specs = {key: AgentSpec.from_dict(value.to_dict()) for key, value in dict(compiled.agent_specs).items()}
    return OrchestratorContract.from_dict({"run_spec": run.to_dict(), "task_dag": dag.to_list(),
        "agent_specs": {key: value.to_dict() for key, value in specs.items()},
        "max_attempts": max_attempts, "control_instructions": _CONTROL_INSTRUCTIONS})
