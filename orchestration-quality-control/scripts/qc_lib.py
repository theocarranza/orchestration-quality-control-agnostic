"""Shared helpers for the orchestration-quality-control deterministic scripts.

Every script in this package is model-free: given the same inputs it produces the
same outputs, every time, on any host with a stock python3. Nothing here calls out
to a language model. That is the point of this module existing — see
references/schemas/blocked.schema.json and the "Deterministic substrate" section
of AI_Codex/Agent_Reports/2026-07-16-adversarial-critique-qc-architecture-feedback.md.
"""

import json
import re
import sys
import unicodedata
from pathlib import PurePosixPath


class Blocked(Exception):
    """Raised by any script stage that cannot proceed safely.

    Carries exactly the fields required by references/schemas/blocked.schema.json.
    main() in each script catches this, prints the payload, and exits 2.
    """

    def __init__(self, stage, reason_code, detail, recovery_action):
        super().__init__(detail)
        self.stage = stage
        self.reason_code = reason_code
        self.detail = detail
        self.recovery_action = recovery_action

    def payload(self):
        return {
            "status": "blocked",
            "stage": self.stage,
            "reason_code": self.reason_code,
            "detail": self.detail,
            "recovery_action": self.recovery_action,
        }


REASON_CODES = frozenset(
    [
        "missing_target",
        "malformed_checkpoint",
        "unknown_profile",
        "invalid_decision",
        "unknown_finding_id",
        "anchor_not_found",
        "checkpoint_already_consumed",
        "concurrent_run_active",
        "capability_insufficient",
        "target_outside_approved_set",
        "destination_exists",
        "invalid_proposal",
        "invalid_template",
        "stale_target",
        "unsafe_path",
    ]
)


def run_main(stage, body):
    """Call body() and print its return value as JSON on success (exit 0).

    On Blocked, print the blocked payload and exit 2. This is the single entry
    shape every script's __main__ block uses, so callers can rely on the same
    exit-code contract everywhere.
    """
    try:
        result = body()
    except Blocked as exc:
        print(json.dumps(exc.payload(), indent=2, sort_keys=True))
        sys.exit(2)
    print(json.dumps(result, indent=2, sort_keys=True))
    sys.exit(0)


def normalize_text(text):
    """Unicode NFC, trailing-whitespace-per-line stripped, whitespace runs
    collapsed, blank-line runs collapsed.

    This is the normalization every anchor and hash computation goes through.
    It must never depend on line numbers — the entire point is that content-
    anchored identity survives a partial-apply edit that shifts line numbers.
    """
    text = unicodedata.normalize("NFC", text)
    lines = [re.sub(r"[ \t]+$", "", line) for line in text.split("\n")]
    collapsed_lines = []
    for line in lines:
        collapsed_lines.append(re.sub(r"[ \t]+", " ", line))
    text = "\n".join(collapsed_lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_path(raw_path, *, stage):
    """Validate a workspace-relative path: no absolute paths, no '..' escapes.

    Every schema in references/schemas/ that carries a path (finding.location.path,
    checkpoint.targets[]) requires this shape. Raises Blocked(reason_code=
    'target_outside_approved_set') on violation, since an absolute path or a '..'
    escape is exactly the shape of a target trying to point outside the
    approved set.
    """
    path = PurePosixPath(raw_path.replace("\\", "/"))
    if path.is_absolute():
        raise Blocked(
            stage=stage,
            reason_code="target_outside_approved_set",
            detail=f"path '{raw_path}' is absolute; only workspace-relative paths are accepted",
            recovery_action="pass a path relative to the workspace root",
        )
    if ".." in path.parts:
        raise Blocked(
            stage=stage,
            reason_code="target_outside_approved_set",
            detail=f"path '{raw_path}' contains a '..' segment",
            recovery_action="pass a path that stays within the workspace root",
        )
    return str(path)


def require_fields(obj, required, *, stage, reason_code="malformed_checkpoint"):
    missing = [field for field in required if field not in obj]
    if missing:
        raise Blocked(
            stage=stage,
            reason_code=reason_code,
            detail=f"missing required field(s): {', '.join(missing)}",
            recovery_action="supply every required field before retrying",
        )


def require_enum(value, allowed, field_name, *, stage, reason_code="malformed_checkpoint"):
    if value not in allowed:
        raise Blocked(
            stage=stage,
            reason_code=reason_code,
            detail=f"field '{field_name}' has value '{value}', expected one of {sorted(allowed)}",
            recovery_action=f"set '{field_name}' to one of {sorted(allowed)}",
        )


def load_json_file(path, *, stage, reason_code="malformed_checkpoint"):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:
        raise Blocked(
            stage=stage,
            reason_code="missing_target" if reason_code == "malformed_checkpoint" else reason_code,
            detail=f"file not found: {path}",
            recovery_action="verify the path and retry",
        ) from exc
    except json.JSONDecodeError as exc:
        raise Blocked(
            stage=stage,
            reason_code=reason_code,
            detail=f"invalid JSON in {path}: {exc}",
            recovery_action="fix the malformed JSON and retry",
        ) from exc


def read_stdin_json(*, stage):
    raw = sys.stdin.read()
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Blocked(
            stage=stage,
            reason_code="malformed_checkpoint",
            detail=f"invalid JSON on stdin: {exc}",
            recovery_action="pipe well-formed JSON to this script",
        ) from exc
