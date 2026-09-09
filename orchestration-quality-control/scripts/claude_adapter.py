"""Claude host composition over the deterministic AdapterPort."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections.abc import Mapping

from adapter_port import AdapterPort
from claude_transport import ClaudeTransport, parse_stream
from gate import AnswerDecision, RetryDecision, AWAITING_USER_INPUT, approve_answer
from qc_lib import Blocked, freeze, require_enum
from run_state import PHASES

STAGE = "claude_adapter"
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_EPOCH = datetime(2026, 1, 1, tzinfo=timezone.utc)

def _canon(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def _text(value, label):
    if not isinstance(value, str) or not value.strip() or value.strip() == "inherit":
        raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail=f"{label} must be explicit", recovery_action="provide a nonblank explicit value")
    return value

def _safe(value, label):
    _text(value, label)
    if not _ID.fullmatch(value):
        raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail=f"{label} contains unsafe path characters", recovery_action="use a validated identifier")
    return value

def _process_snapshot(value):
    """Keep runner failures inspectable without retaining caller-owned exceptions."""
    if isinstance(value, BaseException):
        return freeze({"exception_type": type(value).__name__, "message": str(value)})
    return freeze(value)

@dataclass(frozen=True)
class TransportEvidence:
    invocation: int
    request: tuple
    response: object
    error: object | None = None
    process_tuple: object | None = None
    raw_stdout: str = ""
    raw_stderr: str = ""
    events: tuple = ()
    native_session_id: str | None = None
    worker_tool_use_id: str | None = None
    adapter_identity: str = "claude-adapter"
    argv: tuple = ()
    settings: object = None
    worker_definition: object = None
    schema_sha256: str = ""
    prompt_sha256: str = ""
    model: str = ""
    effort: str = ""

class ClaudeAdapter(AdapterPort):
    def __init__(self, runner, *, model, effort, worker_definitions, policy=None, artifact_dir=".", executable="claude", mailbox=None):
        self._last_process = None
        def recording_runner(argv):
            try:
                value = runner(argv)
                self._last_process = value
                return value
            except Exception as exc:
                self._last_process = _process_snapshot(exc)
                raise
        self._transport = ClaudeTransport(recording_runner, executable=executable)
        self._model, self._effort = _text(model, "model"), _text(effort, "effort")
        if not isinstance(worker_definitions, Mapping):
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="worker definitions must be a mapping", recovery_action="provide a mapping of worker definitions")
        self._workers = dict(worker_definitions)
        if policy is not None and not callable(policy):
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="policy seam must be callable", recovery_action="inject a callable policy boundary")
        self._policy = policy if policy is not None else (lambda **kwargs: {"native_enforcement": False})
        self._artifact_dir = Path(artifact_dir)
        self._session_id = None
        self._counter = 0
        if mailbox is not None:
            self._counter = len(mailbox.read_all())
        self._transport_evidence = []
        self._identity = "claude-adapter"
        self._invocation_count = 0

    @property
    def transport_evidence(self):
        """Read-only snapshots; nested records are recursively frozen."""
        return tuple(self._transport_evidence)

    def _meta(self):
        self._counter += 1
        return f"env-{self._counter}", (_EPOCH + timedelta(seconds=self._counter)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def spawn(self, mailbox, *, run_id, task_id, attempt, agent_id, brief):
        _safe(run_id, "run_id"); _safe(task_id, "task_id"); _safe(agent_id, "agent_id")
        if not isinstance(attempt, int) or isinstance(attempt, bool) or attempt < 1:
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="attempt must be a positive integer", recovery_action="provide a valid attempt")
        if agent_id not in self._workers:
            raise Blocked(stage=STAGE, reason_code="missing_target", detail="unknown worker definition", recovery_action="use an exact worker definition key")
        brief_bytes = _canon(brief)
        brief_hash = hashlib.sha256(brief_bytes).hexdigest()
        before_request = self._counter
        request_id, created = self._meta()
        try:
            request = self._append(mailbox, envelope_id=request_id, run_id=run_id, sender="orchestrator", recipient=f"agent:{agent_id}", kind="request", payload={"task_id": task_id, "attempt": attempt, "brief": brief, "brief_hash": brief_hash}, created_at=created)
        except Exception:
            self._counter = before_request
            raise
        prompt = json.dumps(brief, sort_keys=True, separators=(",", ":"))
        previous = self._session_id
        artifact_path = None
        artifact_created = False
        try:
            self._invocation_count += 1
            result = self._transport.invoke(prompt, self._model, self._effort, agent_id, self._workers[agent_id], session_id=previous)
            self._validate_transport_result(result, agent_id=agent_id, task_id=task_id, attempt=attempt, expected_session=previous)
            self._session_id = result.session_id
            self._transport_evidence.append(TransportEvidence(
                self._invocation_count, request, freeze(result), process_tuple=freeze(self._last_process),
                raw_stdout=result.raw_stdout, raw_stderr=result.raw_stderr, events=freeze(result.events),
                native_session_id=result.session_id, worker_tool_use_id=result.worker_tool_use_id,
                argv=freeze(result.argv), settings=freeze(result.settings),
                worker_definition=freeze(result.worker_definition), schema_sha256=result.schema_sha256,
                prompt_sha256=result.prompt_sha256, model=self._model, effort=self._effort,
            ))
            payload = dict(result.structured_output)
            if payload.get("task_id") != task_id or payload.get("attempt") != attempt:
                raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="worker result does not match exact request", recovery_action="return the exact task and attempt")
            if "artifact" in payload:
                artifact_bytes = payload.pop("artifact").encode("utf-8")
                path = self._artifact_dir / f"{run_id}__{task_id}__attempt-{attempt}.artifact"
                path.parent.mkdir(parents=True, exist_ok=True)
                if path.exists():
                    raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="deterministic artifact path already exists", recovery_action="use a new run, task, or attempt identity")
                path.write_bytes(artifact_bytes)
                artifact_path = path
                artifact_created = True
                stored = path.read_bytes()
                payload["artifact_path"] = str(path)
                payload["artifact_hash"] = hashlib.sha256(stored).hexdigest()
            payload["execution_evidence"] = {
                "adapter_identity": self._identity,
                "native_session_id": result.session_id,
                "agent_id": agent_id,
                "agent_tool_use_id": result.worker_tool_use_id,
                "invocation_count": self._invocation_count,
            }
            before_result = self._counter
            result_id, result_created = self._meta()
            try:
                envelope = self._append(mailbox, envelope_id=result_id, run_id=run_id, sender=f"agent:{agent_id}", recipient="orchestrator", kind="result", payload=payload, created_at=result_created)
            except Exception:
                self._counter = before_result
                raise
            return request, envelope
        except Exception as exc:
            if artifact_created:
                artifact_path.unlink()
            if not isinstance(exc, Blocked):
                exc = Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail=str(exc), recovery_action="inspect transport evidence")
            raw = self._last_process if isinstance(self._last_process, tuple) else ()
            stdout = raw[1] if len(raw) > 1 and isinstance(raw[1], str) else ""
            stderr = raw[2] if len(raw) > 2 and isinstance(raw[2], str) else ""
            try:
                parsed = parse_stream(stdout, agent_id, raw_stderr=stderr) if stdout else None
                events = parsed.events if parsed else ()
            except Exception:
                events = ()
            self._transport_evidence.append(TransportEvidence(self._invocation_count, request, None, freeze(exc.detail), process_tuple=freeze(self._last_process), raw_stdout=stdout, raw_stderr=stderr, events=freeze(events)))
            self._session_id = previous
            raise exc

    @staticmethod
    def _validate_transport_result(result, *, agent_id, task_id, attempt, expected_session):
        """Bind every host identity to the immutable engine-issued request."""
        if not isinstance(result.session_id, str) or not result.session_id.strip():
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="native session is blank", recovery_action="return a nonblank native session")
        if expected_session is not None and result.session_id != expected_session:
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="native session does not match the resumed session", recovery_action="resume the exact native session")
        tool = result.worker_tool_use
        if not isinstance(tool, Mapping) or tool.get("name") != "Agent":
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="worker tool-use is not Agent", recovery_action="return exact Agent tool-use evidence")
        if not isinstance(tool.get("id"), str) or not tool["id"].strip() or tool["id"] != result.worker_tool_use_id:
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="worker tool-use id is blank or inconsistent", recovery_action="return one native tool-use id")
        input_data = tool.get("input")
        if not isinstance(input_data, Mapping) or input_data.get("subagent_type") != agent_id:
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="worker tool-use recipient does not match the request", recovery_action="return the exact dispatched worker identity")
        payload = result.structured_output
        if not isinstance(payload, Mapping) or payload.get("task_id") != task_id or payload.get("attempt") != attempt:
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="worker result does not match exact task and attempt", recovery_action="return the exact task and attempt")

    def emit_status(self, mailbox, *, run_id, phase, context=None):
        require_enum(phase, PHASES, "phase", stage=STAGE)
        before = self._counter; eid, ts = self._meta(); payload = dict(context or {}); payload["phase"] = phase
        try: return self._append(mailbox, envelope_id=eid, run_id=run_id, sender="orchestrator", recipient="root", kind="status", payload=payload, created_at=ts)
        except Exception: self._counter = before; raise

    def relay_question(self, mailbox, *, run_id, decision):
        if not isinstance(decision, RetryDecision) or decision.action != AWAITING_USER_INPUT:
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="decision must await input", recovery_action="pass approved decision")
        q = decision.question
        if decision.phase != AWAITING_USER_INPUT or not isinstance(q, Mapping) or set(q) != {"question_id", "prompt"} or any(not isinstance(q[k], str) or not q[k].strip() for k in q):
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="question is incomplete", recovery_action="pass complete question")
        from run_state import reduce
        state = reduce(mailbox.read_all())
        expected = {"task_id": decision.task_id, "attempt": decision.attempt, "critique": decision.critique, "attempts_remaining": decision.attempts_remaining, "question_id": q["question_id"], "prompt": q["prompt"]}
        if run_id != state.run_id or state.phase != AWAITING_USER_INPUT or dict(state.context or {}) != {**expected, "phase": AWAITING_USER_INPUT}:
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="decision does not match current waiting context", recovery_action="relay the current approved decision")
        before = self._counter; eid, ts = self._meta()
        try: return self._append(mailbox, envelope_id=eid, run_id=run_id, sender="orchestrator", recipient="root", kind="question", payload={"task_id": decision.task_id, "attempt": decision.attempt, "critique": decision.critique, "attempts_remaining": decision.attempts_remaining, **dict(q)}, created_at=ts)
        except Exception: self._counter = before; raise

    def relay_answer(self, mailbox, *, answer):
        if not isinstance(answer, AnswerDecision):
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="answer must be approved", recovery_action="approve answer")
        raw = {key: getattr(answer, key) for key in ("run_id", "task_id", "attempt", "question_id", "decision", "text")}
        if approve_answer(__import__("run_state").reduce(mailbox.read_all()), raw) != answer:
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="answer does not match state", recovery_action="approve current answer")
        before = self._counter; eid, ts = self._meta()
        try: return self._append(mailbox, envelope_id=eid, run_id=answer.run_id, sender="root", recipient="orchestrator", kind="answer", payload=raw, created_at=ts)
        except Exception: self._counter = before; raise

    def enforce_policy(self, *, run_id, hook_name, context=None):
        disclosure = self._policy(run_id=run_id, hook_name=hook_name, context=context)
        if not isinstance(disclosure, Mapping):
            raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="policy disclosure must be a mapping", recovery_action="return a mapping disclosure")
        return freeze(disclosure)
