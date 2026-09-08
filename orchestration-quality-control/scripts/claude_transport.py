"""Deterministic, injected-runner boundary for Claude CLI JSONL transport.

This module deliberately does not execute Claude itself.  Callers supply the
runner, keeping capture policy and process lifecycle outside this small parser.
"""

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from kernel_specs import validate_worker_result
from qc_lib import Blocked, freeze
from claude_policy_hook import generated_settings


STAGE = "claude_transport"
_SCHEMA_PATH = Path(__file__).resolve().parent.parent / "schemas" / "worker-result.schema.json"


def _blocked(detail, recovery="correct the Claude transport response and retry"):
    return Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail=detail,
                   recovery_action=recovery)


def _nonblank_text(value, field):
    if not isinstance(value, str) or not value.strip() or value.strip() == "inherit":
        raise _blocked(f"{field} must be an explicit nonblank string and cannot be 'inherit'")
    return value


def _validate_agent_settings(value, label="worker_definition"):
    """Reject implicit model/effort settings anywhere in generated agent JSON."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            item_label = f"{label}.{key}"
            if key in ("model", "effort"):
                _nonblank_text(item, item_label)
            else:
                _validate_agent_settings(item, item_label)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _validate_agent_settings(item, f"{label}[{index}]")


def _canonical_json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise _blocked(f"cannot canonicalize CLI JSON argument: {exc}") from exc


def _worker_schema():
    try:
        with _SCHEMA_PATH.open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError) as exc:
        raise _blocked(f"checked-in worker schema is unavailable: {exc}") from exc


def _event_session(event):
    value = event.get("session_id")
    return value if isinstance(value, str) and value.strip() else None


def _agent_tool_uses(event):
    """Return native Agent tool-use blocks without deriving any identity."""
    message = event.get("message")
    content = message.get("content") if isinstance(message, Mapping) else event.get("content")
    if not isinstance(content, (list, tuple)):
        return ()
    return tuple(block for block in content if isinstance(block, Mapping) and block.get("type") == "tool_use"
                 and block.get("name") == "Agent")


@dataclass(frozen=True)
class ParsedClaudeStream:
    """Raw, immutable parse evidence; ``error`` permits archival before raising."""

    raw_stdout: str
    events: tuple
    session_id: str | None
    result_event: object | None
    worker_tool_use: object | None
    structured_output: object | None
    error: Blocked | None = None
    raw_stderr: str = ""


@dataclass(frozen=True)
class ClaudeTransportResult:
    session_id: str
    worker_tool_use_id: str
    worker_tool_use: object
    structured_output: object
    raw_stdout: str
    raw_stderr: str
    events: tuple
    invocation_count: int


def parse_stream(stdout, worker_name, *, expected_session_id=None, raw_stderr=""):
    """Parse recorded JSONL without process or model I/O.

    An invalid stream returns its immutable parsed prefix and the named error so
    an adapter can archive evidence before it chooses to raise it.
    """
    if not isinstance(raw_stderr, str):
        return ParsedClaudeStream(stdout if isinstance(stdout, str) else "", (), None, None, None, None,
                                  _blocked("runner stderr must be a string"), "")
    try:
        _nonblank_text(worker_name, "worker_name")
        if expected_session_id is not None:
            _nonblank_text(expected_session_id, "expected_session_id")
    except Blocked as exc:
        return ParsedClaudeStream(stdout if isinstance(stdout, str) else "", (), None, None, None, None, exc, raw_stderr)
    if not isinstance(stdout, str):
        return ParsedClaudeStream("", (), None, None, None, None, _blocked("runner stdout must be a string"), raw_stderr)
    events = []
    for number, line in enumerate(stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            return ParsedClaudeStream(stdout, tuple(events), None, None, None, None,
                                      _blocked(f"malformed JSONL at line {number}: {exc}"), raw_stderr)
        if not isinstance(event, dict):
            return ParsedClaudeStream(stdout, tuple(events), None, None, None, None,
                                      _blocked(f"JSONL event at line {number} must be an object"), raw_stderr)
        events.append(freeze(event))

    init_records = []
    terminals = []
    worker_uses = []
    wrong_uses = []
    for event in events:
        if event.get("type") == "system" and event.get("subtype") == "init":
            init_records.append(event)
        if event.get("type") == "result":
            terminals.append(event)
        for tool_use in _agent_tool_uses(event):
            identity = tool_use.get("input", {}).get("subagent_type") if isinstance(tool_use.get("input"), Mapping) else None
            if identity == worker_name:
                worker_uses.append(tool_use)
            else:
                wrong_uses.append(tool_use)
    if not init_records:
        return ParsedClaudeStream(stdout, tuple(events), None, None, None, None,
                                  _blocked("missing native init record"), raw_stderr)
    if len(init_records) != 1:
        return ParsedClaudeStream(stdout, tuple(events), None, None, None, None,
                                  _blocked("duplicate native init record"), raw_stderr)
    init_session = _event_session(init_records[0])
    if init_session is None:
        return ParsedClaudeStream(stdout, tuple(events), None, None, None, None,
                                  _blocked("native init record is missing a nonblank session_id"), raw_stderr)
    if not terminals:
        return ParsedClaudeStream(stdout, tuple(events), init_session, None, None, None,
                                  _blocked("missing terminal result record"), raw_stderr)
    if len(terminals) != 1:
        return ParsedClaudeStream(stdout, tuple(events), init_session, None, None, None,
                                  _blocked("duplicate terminal result record"), raw_stderr)
    final_session = _event_session(terminals[0])
    if final_session is None:
        return ParsedClaudeStream(stdout, tuple(events), init_session, terminals[0], None, None,
                                  _blocked("terminal result record is missing a nonblank session_id"), raw_stderr)
    if init_session != final_session:
        return ParsedClaudeStream(stdout, tuple(events), init_session, terminals[0], None, None,
                                  _blocked("contradictory native session_id evidence"), raw_stderr)
    session_id = init_session
    if expected_session_id is not None and session_id != expected_session_id:
        return ParsedClaudeStream(stdout, tuple(events), session_id, terminals[0], None, None,
                                  _blocked("resume returned a different native session_id"), raw_stderr)
    if wrong_uses or len(worker_uses) != 1:
        return ParsedClaudeStream(stdout, tuple(events), session_id, terminals[0], None, None,
                                  _blocked("missing, duplicate, or wrong-worker Agent tool-use evidence"), raw_stderr)
    tool_use = worker_uses[0]
    tool_use_id = tool_use.get("id")
    if not isinstance(tool_use_id, str) or not tool_use_id.strip():
        return ParsedClaudeStream(stdout, tuple(events), session_id, terminals[0], tool_use, None,
                                  _blocked("Agent tool-use evidence has no native id"), raw_stderr)
    result = terminals[0].get("structured_output")
    if not isinstance(result, Mapping):
        return ParsedClaudeStream(stdout, tuple(events), session_id, terminals[0], tool_use, None,
                                  _blocked("terminal result lacks structured_output"), raw_stderr)
    try:
        validated = validate_worker_result(result)
    except Blocked as exc:
        return ParsedClaudeStream(stdout, tuple(events), session_id, terminals[0], tool_use, None,
                                  _blocked(f"invalid structured_output: {exc.detail}"), raw_stderr)
    return ParsedClaudeStream(stdout, tuple(events), session_id, terminals[0], tool_use, freeze(validated), None, raw_stderr)


class ClaudeTransport:
    """Build explicit argv and interpret one recorded Claude stream.

    Runner exceptions and nonzero exits have no complete JSONL parse result.
    The injected runner remains the owner of any raw process/CompletedProcess
    evidence for those failures; only a returned zero-exit stream is parsed.
    """

    def __init__(self, runner, *, executable="claude"):
        if not callable(runner):
            raise _blocked("runner must be callable")
        self._runner = runner
        self._executable = _nonblank_text(executable, "executable")
        self._invocation_count = 0

    def invoke(self, prompt, model, effort, worker_name, worker_definition, worker_schema=None, *, session_id=None):
        _nonblank_text(prompt, "prompt")
        _nonblank_text(model, "model")
        _nonblank_text(effort, "effort")
        _nonblank_text(worker_name, "worker_name")
        if not isinstance(worker_definition, dict):
            raise _blocked("worker_definition must be an object")
        _validate_agent_settings(worker_definition)
        # The command and validation are both bound to the checked-in contract.
        schema = _worker_schema()
        if worker_schema is not None and worker_schema != schema:
            raise _blocked("worker_schema must equal the checked-in worker-result schema")
        argv = [self._executable, "--print", "--model", model, "--effort", effort,
                "--tools", "Agent", "--allowed-tools", f"Agent({worker_name})", "--agents",
                _canonical_json({worker_name: worker_definition}), "--json-schema", _canonical_json(schema),
                "--settings", _canonical_json(generated_settings(worker_name)),
                "--output-format", "stream-json", "--verbose", "--include-hook-events",
                "--permission-mode", "dontAsk"]
        if session_id is not None:
            argv.extend(["--resume", _nonblank_text(session_id, "session_id")])
        argv.append(prompt)
        try:
            exit_code, stdout, stderr = self._runner(tuple(argv))
        except Exception as exc:
            raise _blocked(f"runner failed before producing a response: {exc}") from exc
        self._invocation_count += 1
        if not isinstance(exit_code, int) or isinstance(exit_code, bool):
            raise _blocked("runner exit status must be an integer")
        if exit_code != 0:
            raise _blocked(f"Claude process exited {exit_code}; stderr retained by caller: {stderr!r}")
        parsed = parse_stream(stdout, worker_name, expected_session_id=session_id, raw_stderr=stderr)
        if parsed.error is not None:
            raise parsed.error
        return ClaudeTransportResult(parsed.session_id, parsed.worker_tool_use["id"], parsed.worker_tool_use,
                                     parsed.structured_output, stdout, stderr, parsed.events,
                                     self._invocation_count)
