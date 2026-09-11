"""One deterministic Task 5b lifecycle over a caller-configured seam."""

from collections.abc import Mapping
from dataclasses import dataclass
from os import PathLike
from pathlib import Path

from claude_adapter import ClaudeAdapter
from claude_capture import Task5bSeam, _is_native_task_5b_seam, capture, recorded_test_provenance, verify_capture
from mailbox import Mailbox
from oqc import drive, resume
from orchestrator_contract import OrchestratorContract
from qc_lib import Blocked
from run_state import RunState


STAGE = "claude_capture_run"
FAILED_FIELDS = frozenset(("task_id", "attempt", "outcome", "engine_authorized", "question"))
RETRY_FIELDS = frozenset(("task_id", "attempt", "outcome", "answer"))
PASSED_FIELDS = frozenset(("task_id", "attempt", "outcome"))
QUESTION_FIELDS = frozenset(("question_id", "prompt"))
ANSWER_FIELDS = frozenset(("run_id", "task_id", "attempt", "question_id", "decision", "text"))
WAITING_CONTEXT_FIELDS = frozenset(("task_id", "attempt", "critique", "attempts_remaining", "question_id", "prompt", "phase"))
RECORDED_TEST_PROVENANCE_TYPE = type(recorded_test_provenance())


def _blocked(detail):
    raise Blocked(
        stage=STAGE,
        reason_code="malformed_checkpoint",
        detail=detail,
        recovery_action="provide the exact Task 5b seam and recorded lifecycle evidence",
    )


def _require(condition, detail):
    match condition:
        case True:
            return None
        case _:
            return _blocked(detail)


@dataclass(frozen=True)
class Task5bCaptureResult:
    capture_path: Path
    verification: object


def _has_exact_fields(value, fields):
    return isinstance(value, Mapping) and frozenset(value) == fields


def _is_nonblank_text(value):
    return isinstance(value, str) and bool(value.strip())


def _is_positive_integer(value):
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _path(value, label):
    _require(isinstance(value, (str, PathLike)), f"Task 5b {label} must be path-like")
    try:
        return Path(value)
    except (OSError, TypeError, ValueError) as exc:
        return _blocked(f"Task 5b {label} is not a usable path: {exc}")


def _has_expected_contract_topology(contract, worker_definitions):
    tasks = tuple(contract.task_dag.tasks)
    specs = contract.agent_specs
    roles = frozenset(node.role for node in tasks)
    agent_ids = frozenset(spec.agent_id for spec in specs.values())
    return (
        len(tasks) == 2
        and not tasks[0].depends_on
        and tuple(tasks[1].depends_on) == (tasks[0].task_id,)
        and frozenset(specs) == roles
        and len(agent_ids) == 2
        and frozenset(worker_definitions) == agent_ids
    )


def _require_boundary(seam, artifact_dir, capture_dir, provenance):
    _require(isinstance(seam, Task5bSeam), "Task 5b seam must have the accepted seam type")
    _require(isinstance(seam.contract, OrchestratorContract), "Task 5b seam must have the accepted contract type")
    _require(isinstance(seam.adapter, ClaudeAdapter), "Task 5b seam must have the configured adapter type")
    worker_definitions = getattr(seam.adapter, "_workers", None)
    _require(
        isinstance(seam.contract.agent_specs, Mapping) and isinstance(worker_definitions, Mapping),
        "Task 5b contract and adapter must expose generated worker mappings",
    )
    artifact_path = _path(artifact_dir, "artifact directory")
    capture_path = _path(capture_dir, "capture directory")
    _require(
        provenance is None or type(provenance) is RECORDED_TEST_PROVENANCE_TYPE,
        "Task 5b provenance must be native or the explicit recorded test marker",
    )
    _require(
        provenance is not None or _is_native_task_5b_seam(seam),
        "Task 5b native acceptance requires the compile-time real subprocess seam",
    )
    _require(
        _has_expected_contract_topology(seam.contract, worker_definitions),
        "Task 5b contract and adapter must declare the exact isolated two-worker topology",
    )
    _require(
        isinstance(seam.adapter.transport_evidence, tuple),
        "Task 5b adapter transport evidence must be immutable",
    )
    _require(
        seam.adapter._artifact_dir == artifact_path,
        "Task 5b adapter artifact directory must match the caller artifact directory",
    )
    _require(artifact_path != capture_path, "Task 5b artifact and capture directories must differ")
    _require(not capture_path.exists(), "Task 5b capture directory must not already exist")
    return seam.contract, seam.adapter, artifact_path, capture_path


def _has_valid_waiting_state(waiting):
    return (
        isinstance(waiting, RunState)
        and waiting.phase == "awaiting-user-input"
        and _is_nonblank_text(waiting.run_id)
        and _has_exact_fields(waiting.context, WAITING_CONTEXT_FIELDS)
        and _is_nonblank_text(waiting.context["task_id"])
        and _is_positive_integer(waiting.context["attempt"])
        and _is_nonblank_text(waiting.context["critique"])
        and _is_positive_integer(waiting.context["attempts_remaining"])
        and _is_nonblank_text(waiting.context["question_id"])
        and _is_nonblank_text(waiting.context["prompt"])
        and waiting.context["phase"] == "awaiting-user-input"
    )


def _require_fixture(seam, contract):
    _require(
        isinstance(seam, Task5bSeam) and isinstance(seam.fixture, tuple) and len(seam.fixture) == 4,
        "Task 5b seam must contain its four-step fixture",
    )
    failed, retry, first_passed, second_passed = seam.fixture
    _require(
        all(isinstance(step, Mapping) for step in seam.fixture),
        "Task 5b fixture steps must be mappings",
    )
    _require(
        _has_exact_fields(failed, FAILED_FIELDS)
        and _has_exact_fields(retry, RETRY_FIELDS)
        and _has_exact_fields(first_passed, PASSED_FIELDS)
        and _has_exact_fields(second_passed, PASSED_FIELDS),
        "Task 5b fixture steps do not have the required lifecycle fields",
    )
    question = failed["question"]
    answer = retry["answer"]
    _require(
        _has_exact_fields(question, QUESTION_FIELDS)
        and _has_exact_fields(answer, ANSWER_FIELDS),
        "Task 5b fixture question or answer does not have the required fields",
    )
    _require(
        _is_nonblank_text(question["question_id"])
        and _is_nonblank_text(question["prompt"])
        and _is_nonblank_text(answer["run_id"])
        and _is_nonblank_text(answer["task_id"])
        and _is_positive_integer(answer["attempt"])
        and _is_nonblank_text(answer["question_id"])
        and answer["decision"] == "retry"
        and _is_nonblank_text(answer["text"]),
        "Task 5b fixture question or answer is not schema-valid",
    )
    tasks = tuple(node.task_id for node in contract.task_dag.tasks)
    _require(len(tasks) == 2, "Task 5b seam must contain the isolated two-task workflow")
    expected = (
        failed["task_id"] == tasks[0]
        and failed["attempt"] == 1
        and failed["outcome"] == "failed"
        and failed["engine_authorized"] is True
        and retry["task_id"] == tasks[0]
        and retry["attempt"] == 1
        and retry["outcome"] == "retry"
        and answer["run_id"] == contract.run_spec.run_id
        and answer["task_id"] == tasks[0]
        and answer["attempt"] == 1
        and answer["question_id"] == question["question_id"]
        and first_passed == {"task_id": tasks[0], "attempt": 2, "outcome": "passed"}
        and second_passed == {"task_id": tasks[1], "attempt": 1, "outcome": "passed"}
    )
    _require(expected, "Task 5b fixture does not declare the required lifecycle")
    return failed, answer, tasks


def _derived_answer(answer_fixture, waiting):
    context = dict(waiting.context or {})
    question_id = context.get("question_id")
    bindings = {
        "run_id": waiting.run_id,
        "task_id": context.get("task_id"),
        "attempt": context.get("attempt"),
        "question_id": question_id,
        "decision": "retry",
    }
    _require(
        not any(answer_fixture.get(key) != value for key, value in bindings.items()),
        "fixture retry answer does not bind the actual awaiting state",
    )
    _require(
        isinstance(answer_fixture.get("text"), str) and bool(answer_fixture["text"].strip()),
        "fixture retry answer text is not schema-valid",
    )
    return {**bindings, "text": answer_fixture["text"]}


def _require_first_attempt(mailbox, failed_fixture):
    results = tuple(
        envelope.payload
        for envelope in mailbox.read_all()
        if envelope.kind == "result"
    )
    expected_question = failed_fixture["question"]
    _require(
        len(results) == 1 and results[0].get("outcome") == "failed" and results[0].get("question") == expected_question,
        "first worker result does not satisfy the engine-authorized fixture question",
    )


def _require_completed_lifecycle(mailbox, task_ids):
    results = tuple(
        (envelope.payload.get("task_id"), envelope.payload.get("attempt"), envelope.payload.get("outcome"))
        for envelope in mailbox.read_all()
        if envelope.kind == "result"
    )
    expected = ((task_ids[0], 1, "failed"), (task_ids[0], 2, "passed"), (task_ids[1], 1, "passed"))
    _require(results == expected, "stored lifecycle does not match first failure, retry pass, and dependent pass")


def run_task_5b_capture(seam, artifact_dir, capture_dir, *, provenance):
    """Drive the fixed Task 5b sequence and verify its archive without rerunning it."""
    contract, adapter, artifact_path, capture_path = _require_boundary(seam, artifact_dir, capture_dir, provenance)
    failed_fixture, answer_fixture, task_ids = _require_fixture(seam, contract)
    mailbox = Mailbox()
    waiting = drive(
        contract.task_dag,
        adapter,
        mailbox,
        contract.agent_specs,
        contract.max_attempts,
        run_id=contract.run_spec.run_id,
    )
    _require(_has_valid_waiting_state(waiting), "first worker did not return a valid engine-authorized awaiting state")
    _require_first_attempt(mailbox, failed_fixture)
    completed = resume(
        contract.task_dag,
        adapter,
        mailbox,
        contract.agent_specs,
        contract.max_attempts,
        answer=_derived_answer(answer_fixture, waiting),
    )
    _require(completed.phase == "completed", "retry and dependent worker did not complete the lifecycle")
    _require_completed_lifecycle(mailbox, task_ids)
    evidence = adapter.transport_evidence
    _require(len(evidence) == 3, "Task 5b requires exactly three logical worker invocations")
    capture_path = capture(
        contract,
        mailbox,
        evidence,
        artifact_path,
        capture_path,
        provenance=provenance,
    )
    verification = verify_capture(capture_path, live_acceptance=provenance is None)
    _require(
        len(adapter.transport_evidence) == len(evidence),
        "archive verification performed an additional worker invocation",
    )
    return Task5bCaptureResult(capture_path, verification)
