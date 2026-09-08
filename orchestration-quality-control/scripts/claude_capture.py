"""Canonical, model-free capture verification and an uninvoked Task 5b seam."""
import hashlib, json, os, shutil, subprocess, tempfile
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping

from claude_adapter import ClaudeAdapter
from claude_policy_hook import POLICY_DISCLOSURE
from compile_workflow import compile_workflow
from mailbox import Mailbox
from oqc import verify as oqc_verify
from orchestrator_contract import OrchestratorContract, compile_orchestrator
from qc_lib import Blocked, thaw
from run_state import reduce
from gate import approve_answer

STAGE = "claude_capture"
_CORE = ("contract.json", "mailbox.jsonl", "transport.jsonl", "mailbox-head.json", "manifest.json", "COMPLETE")
_FIELDS = ("invocation", "request", "response", "error", "native_session_id", "worker_tool_use_id", "adapter_identity", "raw_stdout", "raw_stderr", "events", "process_tuple")

def _blocked(detail):
    raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail=detail, recovery_action="recreate a complete canonical capture")
def _canon(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
def _digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def _nonblank(value, label):
    if not isinstance(value, str) or not value.strip(): _blocked(f"{label} must be nonblank")
def _json_value(value):
    if hasattr(value, "to_dict"): return _json_value(value.to_dict())
    if hasattr(value, "__dataclass_fields__"): return {key: _json_value(getattr(value, key)) for key in value.__dataclass_fields__}
    if isinstance(value, Mapping): return {str(key): _json_value(item) for key, item in thaw(value).items()}
    if isinstance(value, (tuple, list)): return [_json_value(item) for item in value]
    return value
def _parse(path, label):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc: _blocked(f"{label} is not canonical JSON: {exc}")

@dataclass(frozen=True)
class _RecordedTestProvenance: pass
def recorded_test_provenance(): return _RecordedTestProvenance()
def _provenance(value):
    if value is None: return "native"
    if isinstance(value, _RecordedTestProvenance): return "recorded-test"
    _blocked("provenance must be native or the explicit recorded test marker")

def _record(value):
    data = _json_value(value)
    if not isinstance(data, dict) or set(data) != set(_FIELDS): _blocked("transport evidence has noncanonical fields")
    return data
def _read_records(path):
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try: record = json.loads(line)
        except json.JSONDecodeError as exc: _blocked(f"transport record is not JSON: {exc}")
        if not isinstance(record, dict) or set(record) != set(_FIELDS): _blocked("transport record has unknown or missing fields")
        records.append(record)
    if not records: _blocked("transport evidence must contain invocations")
    return records

def _canonical_records(evidence, mailbox):
    records = []
    for item in evidence:
        record = _record(item); raw = record["response"]
        if not isinstance(raw, dict) or not isinstance(raw.get("structured_output"), dict): _blocked("transport evidence has no successful immutable response")
        output = raw["structured_output"]
        matches = [envelope for envelope in mailbox.read_all() if envelope.kind == "result" and envelope.payload.get("task_id") == output.get("task_id") and envelope.payload.get("attempt") == output.get("attempt")]
        if len(matches) != 1: _blocked("immutable response does not have exactly one mailbox result")
        record["response"] = matches[0].to_dict(); records.append(record)
    return records

def _validate_records(records, contract, mailbox):
    task_nodes = {node.task_id: node for node in contract.task_dag.tasks}
    if len(task_nodes) != 2 or len(contract.agent_specs) != 2: _blocked("capture requires exactly two generated workers")
    sessions, tools, task_agents = set(), set(), {}
    requests = {(e.payload.get("task_id"), e.payload.get("attempt")): e.to_dict() for e in mailbox.read_all() if e.kind == "request"}
    for expected, record in enumerate(records, 1):
        if record["invocation"] != expected: _blocked("transport invocations must be positive and sequential")
        for field in ("native_session_id", "worker_tool_use_id", "adapter_identity"): _nonblank(record[field], field)
        sessions.add(record["native_session_id"]); tools.add(record["worker_tool_use_id"])
        request, response = record["request"], record["response"]
        if not isinstance(request, dict) or not isinstance(response, dict): _blocked("transport request and response must be envelope objects")
        if request.get("kind") != "request" or request.get("sender") != "orchestrator": _blocked("transport request is not engine-owned")
        if response.get("kind") != "result" or response.get("recipient") != "orchestrator": _blocked("transport response is not addressed to orchestrator")
        recipient = request.get("recipient")
        if not isinstance(recipient, str) or not recipient.startswith("agent:") or response.get("sender") != recipient: _blocked("request recipient does not bind result sender")
        payload = response.get("payload")
        if not isinstance(payload, dict): _blocked("result payload is not an object")
        task_id, attempt = payload.get("task_id"), payload.get("attempt")
        if request.get("payload", {}).get("task_id") != task_id or request.get("payload", {}).get("attempt") != attempt: _blocked("request and result task binding differs")
        if requests.get((task_id, attempt)) != request or task_id not in task_nodes: _blocked("transport request is absent from authoritative mailbox")
        agent_id, spec = recipient[6:], contract.agent_specs.get(task_nodes[task_id].role)
        if spec is None or spec.agent_id != agent_id: _blocked("request worker is not the contract worker")
        evidence = payload.get("execution_evidence")
        expected_evidence = {"adapter_identity": record["adapter_identity"], "native_session_id": record["native_session_id"], "agent_id": agent_id, "agent_tool_use_id": record["worker_tool_use_id"], "invocation_count": expected}
        if not isinstance(evidence, dict) or set(evidence) != set(expected_evidence) or evidence != expected_evidence: _blocked("execution evidence does not bind immutable transport")
        task_agents.setdefault(task_id, agent_id)
        if task_agents[task_id] != agent_id: _blocked("task worker identity changed")
    if len(sessions) != 1 or len(tools) != len(records): _blocked("native session or Agent tool-use identities are not unique")
    if set(task_agents) != set(task_nodes) or len(set(task_agents.values())) != 2: _blocked("two tasks must use distinct worker identities")

def _validate_root_boundary(mailbox):
    prior, saw_question, approved_retries = [], False, set()
    for envelope in mailbox.read_all():
        if envelope.kind == "question" and envelope.sender == "orchestrator" and envelope.recipient == "root": saw_question = True
        if envelope.kind == "request" and envelope.payload.get("attempt", 0) > 1:
            key = (envelope.payload.get("task_id"), envelope.payload.get("attempt") - 1)
            if key not in approved_retries: _blocked("retry was dispatched before a schema-valid ordered answer")
        if envelope.sender == "root":
            if not saw_question or envelope.kind != "answer" or envelope.recipient != "orchestrator": _blocked("root was active before an approved question boundary")
            try: approve_answer(reduce(tuple(prior)), dict(envelope.payload))
            except Blocked as exc: _blocked(f"root answer is missing, invalid, or out of order: {exc.detail}")
            if envelope.payload.get("decision") == "retry": approved_retries.add((envelope.payload.get("task_id"), envelope.payload.get("attempt")))
        prior.append(envelope)

def _artifacts(records, source, work):
    result = []
    for record in records:
        payload = record["response"]["payload"]; path, digest = payload.get("artifact_path"), payload.get("artifact_hash")
        if (path is None) != (digest is None): _blocked("artifact path and hash must appear together")
        if path is None: continue
        if not isinstance(path, str) or not isinstance(digest, str) or len(digest) != 64: _blocked("artifact binding is malformed")
        original = Path(path) if Path(path).is_absolute() else source / path
        if not original.is_file() or _digest(original) != digest: _blocked("artifact bytes do not match engine-owned hash")
        name = f"artifact-{len(result)+1}.bin"; shutil.copyfile(original, work / name)
        result.append({"path": name, "sha256": digest, "invocation": record["invocation"]})
    return result

def capture(contract, mailbox, transport_evidence, artifact_dir, capture_dir, *, provenance=None):
    if not isinstance(contract, OrchestratorContract) or not isinstance(mailbox, Mailbox) or not isinstance(transport_evidence, tuple): _blocked("capture requires contract, authoritative mailbox, and immutable tuple evidence")
    target, source = Path(capture_dir), Path(artifact_dir)
    if target.exists(): _blocked(f"capture directory already exists: {target}")
    target.parent.mkdir(parents=True, exist_ok=True); work = Path(tempfile.mkdtemp(prefix=f".{target.name}.", dir=target.parent))
    try:
        records = _canonical_records(transport_evidence, mailbox); _validate_records(records, contract, mailbox); _validate_root_boundary(mailbox)
        (work / "contract.json").write_text(contract.to_json()+"\n", encoding="utf-8")
        (work / "mailbox.jsonl").write_text(mailbox.to_jsonl(), encoding="utf-8")
        (work / "transport.jsonl").write_text("".join(_canon(item)+"\n" for item in records), encoding="utf-8")
        artifacts = _artifacts(records, source, work)
        (work / "mailbox-head.json").write_text(_canon({"head_hash": oqc_verify(mailbox).head_hash})+"\n", encoding="utf-8")
        names = ("contract.json", "mailbox.jsonl", "transport.jsonl", "mailbox-head.json") + tuple(item["path"] for item in artifacts)
        manifest = {"provenance": _provenance(provenance), "files": {name: _digest(work/name) for name in names}, "artifacts": artifacts, "identities": [{key: item[key] for key in ("invocation", "native_session_id", "worker_tool_use_id", "adapter_identity")} for item in records]}
        (work / "manifest.json").write_text(_canon(manifest)+"\n", encoding="utf-8"); (work / "COMPLETE").write_text("complete\n", encoding="utf-8")
        os.replace(work, target); return target
    except Exception: shutil.rmtree(work, ignore_errors=True); raise

def verify_capture(capture_dir, *, live_acceptance=False):
    root = Path(capture_dir)
    if not root.is_dir() or not (root / "manifest.json").is_file(): _blocked("capture directory or manifest is missing")
    manifest = _parse(root / "manifest.json", "manifest")
    if not isinstance(manifest, dict) or set(manifest) != {"provenance", "files", "artifacts", "identities"}: _blocked("manifest shape is not canonical")
    if live_acceptance and manifest["provenance"] != "native": _blocked("recorded test provenance is not live acceptance")
    if manifest["provenance"] not in ("native", "recorded-test") or not isinstance(manifest["files"], dict) or not isinstance(manifest["artifacts"], list): _blocked("manifest values are malformed")
    artifact_names = [item.get("path") for item in manifest["artifacts"] if isinstance(item, dict)]
    if set(path.name for path in root.iterdir()) != set(_CORE) | set(artifact_names) or (root / "COMPLETE").read_bytes() != b"complete\n": _blocked("archive membership or COMPLETE marker is invalid")
    required = {"contract.json", "mailbox.jsonl", "transport.jsonl", "mailbox-head.json"} | set(artifact_names)
    if set(manifest["files"]) != required: _blocked("manifest file set is incomplete or has unknown members")
    for name, digest in manifest["files"].items():
        if not isinstance(digest, str) or len(digest) != 64 or not (root/name).is_file() or _digest(root/name) != digest: _blocked(f"manifest hash mismatch: {name}")
    for item in manifest["artifacts"]:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "invocation"} or item["sha256"] != manifest["files"].get(item["path"]): _blocked("artifact manifest binding is malformed")
    contract = OrchestratorContract.from_json((root/"contract.json").read_text(encoding="utf-8")); mailbox = Mailbox.from_jsonl((root/"mailbox.jsonl").read_text(encoding="utf-8")); result = oqc_verify(mailbox)
    if result.state.phase != "completed": _blocked("COMPLETE marker requires a completed engine state")
    anchor = _parse(root/"mailbox-head.json", "mailbox anchor")
    if not isinstance(anchor, dict) or set(anchor) != {"head_hash"} or anchor["head_hash"] != result.head_hash: _blocked("mailbox head anchor mismatch")
    records = _read_records(root/"transport.jsonl"); _validate_records(records, contract, mailbox); _validate_root_boundary(mailbox)
    identities = [{key: item[key] for key in ("invocation", "native_session_id", "worker_tool_use_id", "adapter_identity")} for item in records]
    if manifest["identities"] != identities: _blocked("manifest identities do not bind transport")
    for item in manifest["artifacts"]:
        payload = records[item["invocation"]-1]["response"]["payload"]
        if payload.get("artifact_hash") != item["sha256"]: _blocked("stored artifact is not bound to response hash")
    return result

@dataclass(frozen=True)
class Task5bSeam:
    compiled: object; contract: OrchestratorContract; adapter: ClaudeAdapter; policy_disclosure: object; fixture: tuple
def real_subprocess_runner(argv):
    run = subprocess.run(argv, text=True, capture_output=True, check=False); return run.returncode, run.stdout, run.stderr
def compile_task_5b_seam(runner=real_subprocess_runner):
    """Build, but never run, the exact isolated-workers Task 5b acceptance seam."""
    compiled = compile_workflow({"run_id":"task5b-live", "created_at":"2026-09-08T12:00:00Z", "outcome":"live-capture", "shape":"isolated-workers", "named_inputs":["first","second"], "outcome_involves_test_tree":False, "profile":"core"})
    contract = compile_orchestrator(compiled, 2)
    workers = {spec.agent_id: {"description":"generated isolated worker", "prompt":"return only schema-valid output", "model":"claude-opus-4-6", "effort":"medium", "tools":[]} for spec in contract.agent_specs.values()}
    adapter = ClaudeAdapter(runner, model="claude-opus-4-6", effort="medium", worker_definitions=workers, policy=lambda **_: dict(POLICY_DISCLOSURE))
    first, second = (node.task_id for node in contract.task_dag.tasks)
    fixture = (
        {"task_id": first, "attempt": 1, "outcome": "failed", "engine_authorized": True, "question": {"question_id": "task5b-q1", "prompt": "Retry first worker?"}},
        {"task_id": first, "attempt": 1, "outcome": "retry", "answer": {"run_id": contract.run_spec.run_id, "task_id": first, "attempt": 1, "question_id": "task5b-q1", "decision": "retry", "text": "retry"}},
        {"task_id": first, "attempt": 2, "outcome": "passed"},
        {"task_id": second, "attempt": 1, "outcome": "passed"},
    )
    return Task5bSeam(compiled, contract, adapter, dict(POLICY_DISCLOSURE), fixture)
verify = verify_capture
archive = capture
