"""engine_lib.py -- the deterministic spine of this engine.

Standard library only, by requirement: this engine must run on a machine where
the tool that generated it is absent. Nothing here calls a model. Model judgment
belongs to the roles in `agents/`; this module owns run records, digests,
approval binding, and path confinement -- the parts that must behave the same way
every time.
"""

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

PHASES = (
    "planning",
    "drafting",
    "checking",
    "awaiting_approval",
    "applying",
    "completed",
    "stopped",
)

_DIGEST_RE = re.compile(r"^[a-f0-9]{64}$")


class EngineError(Exception):
    """Raised when the engine cannot proceed safely. Carries a recovery action."""

    def __init__(self, reason_code, detail, recovery_action):
        super().__init__(detail)
        self.reason_code = reason_code
        self.detail = detail
        self.recovery_action = recovery_action

    def payload(self):
        return {
            "status": "blocked",
            "reason_code": self.reason_code,
            "detail": self.detail,
            "recovery_action": self.recovery_action,
        }


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def constants(engine_root):
    with open(Path(engine_root) / "constants.json", "r", encoding="utf-8") as handle:
        return json.load(handle)


def change_set_digest(changes):
    """Digest a proposed change set. Binds approval to exact content.

    Sorted by path, canonical separators, so the same change set always digests
    the same way regardless of the order the roles produced it in.
    """
    canonical = json.dumps(
        sorted(
            (
                {
                    "path": change["path"],
                    "action": change["action"],
                    "after": change.get("after", ""),
                }
                for change in changes
            ),
            key=lambda item: item["path"],
        ),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def confine(relative_path, root):
    """Return an absolute path inside `root`, or raise. Follows symlinks."""
    candidate = PurePosixPath(str(relative_path).replace("\\", "/"))
    if candidate.is_absolute() or ".." in candidate.parts:
        raise EngineError(
            "unsafe_path",
            f"'{relative_path}' is absolute or escapes through '..'",
            "use a path relative to the artifact root",
        )
    root = Path(root).resolve()
    target = (root / str(candidate)).resolve()
    if target != root and root not in target.parents:
        raise EngineError(
            "unsafe_path",
            f"'{relative_path}' resolves outside '{root}'",
            "write only inside the artifact root",
        )
    return target


def state_path(state_root, run_id):
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*$", str(run_id)):
        raise EngineError(
            "unsafe_path",
            f"run id '{run_id}' is not a simple name",
            "use letters, digits, dots, dashes and underscores in a run id",
        )
    return Path(state_root) / f"run-{run_id}.json"


def write_atomic(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_run(state_root, run_id):
    path = state_path(state_root, run_id)
    if not path.is_file():
        raise EngineError(
            "missing_target",
            f"no run record for '{run_id}'",
            "start the run first, or pass an existing run id",
        )
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_run(state_root, record):
    write_atomic(
        state_path(state_root, record["run_id"]),
        json.dumps(record, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    return record


def start_run(state_root, *, run_id, operation, operations):
    if operation not in operations:
        raise EngineError(
            "unknown_operation",
            f"'{operation}' is not an operation of this engine; known: {', '.join(operations)}",
            "pass one of the engine's declared operations",
        )
    path = state_path(state_root, run_id)
    if path.exists():
        raise EngineError(
            "destination_exists",
            f"run '{run_id}' already exists",
            "resume it, or choose a new run id",
        )
    return save_run(
        state_root,
        {
            "run_id": run_id,
            "operation": operation,
            "phase": "planning",
            "created_at": now(),
            "results": [],
        },
    )


def record_result(state_root, run_id, result):
    """Append one accepted worker result and persist immediately.

    Persisting on every accepted result -- not only at the end -- is what makes a
    run resumable: an interruption after a role returns loses nothing.
    """
    for field in ("task_id", "role", "outcome"):
        if field not in result:
            raise EngineError(
                "malformed_result",
                f"worker result is missing '{field}'",
                "return a result matching schemas/worker-result.schema.json",
            )
    record = load_run(state_root, run_id)
    record.setdefault("results", []).append(result)
    return save_run(state_root, record)


def propose(state_root, run_id, changes):
    """Move a run to awaiting_approval, pinning the digest of the change set."""
    record = load_run(state_root, run_id)
    record["proposed_changes"] = changes
    record["proposed_digest"] = change_set_digest(changes)
    record["phase"] = "awaiting_approval"
    return save_run(state_root, record)


def approve(state_root, run_id, decision, *, at=None):
    record = load_run(state_root, run_id)
    if record.get("phase") != "awaiting_approval":
        raise EngineError(
            "wrong_phase",
            f"run '{run_id}' is in phase '{record.get('phase')}', not awaiting_approval",
            "propose a change set before recording a decision",
        )
    digest = record.get("proposed_digest", "")
    if not _DIGEST_RE.match(str(digest)):
        raise EngineError(
            "malformed_result",
            "run has no proposed change-set digest to approve",
            "propose a change set first",
        )
    record["approval"] = {
        "decision": decision,
        "approved_digest": digest,
        "decided_at": at or now(),
    }
    record["phase"] = "applying" if decision == "approve" else "stopped"
    return save_run(state_root, record)


def approved_changes(state_root, run_id):
    """Return the approved change set, or raise if approval no longer describes it."""
    record = load_run(state_root, run_id)
    approval = record.get("approval") or {}
    if approval.get("decision") != "approve":
        raise EngineError(
            "not_approved",
            f"run '{run_id}' carries no approval",
            "record an approve decision before applying",
        )
    checked = [
        result
        for result in record.get("results", [])
        if result.get("role") and "findings" in result
    ]
    if not checked:
        raise EngineError(
            "not_checked",
            "no checking result is recorded for this run; approval cannot stand in for a check",
            "run the checking role before applying",
        )
    if any(result.get("findings") for result in checked):
        raise EngineError(
            "not_clean",
            "the recorded check reported findings; a failing check cannot be applied",
            "resolve the findings and check again",
        )
    changes = record.get("proposed_changes", [])
    current = change_set_digest(changes)
    if current != approval.get("approved_digest"):
        raise EngineError(
            "stale_approval",
            "the change set moved after approval; the approval does not describe it",
            "obtain approval for the current change set",
        )
    return changes


def apply_changes(state_root, run_id, artifact_root):
    """Write the approved change set. The only place this engine writes artifacts."""
    changes = approved_changes(state_root, run_id)
    applied, skipped = [], []
    for change in changes:
        try:
            target = confine(change["path"], artifact_root)
        except EngineError as error:
            skipped.append({"path": change.get("path", ""), "reason": error.detail})
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(target, change.get("after", ""))
        applied.append({"path": change["path"], "action": change["action"]})
    record = load_run(state_root, run_id)
    record["applied"] = applied
    record["skipped"] = skipped
    record["phase"] = "completed" if not skipped else "stopped"
    save_run(state_root, record)
    return {"applied": applied, "skipped": skipped, "phase": record["phase"]}


def status(state_root, run_id):
    record = load_run(state_root, run_id)
    return {
        "run_id": record["run_id"],
        "operation": record["operation"],
        "phase": record["phase"],
        "results_recorded": len(record.get("results", [])),
        "awaiting": _awaiting(record),
    }


def _awaiting(record):
    phase = record.get("phase")
    if phase == "awaiting_approval":
        return "a human approval decision"
    if phase == "applying":
        return "the writing role to apply the approved change set"
    if phase in ("completed", "stopped"):
        return "nothing; the run is finished"
    return "the next role in this operation"
