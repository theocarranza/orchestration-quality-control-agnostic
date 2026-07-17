#!/usr/bin/env python3
"""Apply exactly one approved orchestration-upgrade checkpoint atomically."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path

import qc_lib
from qc_lib import Blocked
from render_upgrade import validate_proposal

STAGE = "apply_upgrade"


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _atomic_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply(workspace: Path, checkpoint_path: Path) -> dict:
    workspace = workspace.resolve()
    checkpoint = qc_lib.load_json_file(checkpoint_path, stage=STAGE)
    if checkpoint.get("run_type") != "upgrade" or checkpoint.get("status") != "pending_approval":
        raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="checkpoint is not a pending upgrade", recovery_action="pass a pending upgrade checkpoint")
    if (checkpoint.get("approval") or {}).get("decision") != "approve":
        raise Blocked(stage=STAGE, reason_code="invalid_decision", detail="upgrade checkpoint has no explicit approval", recovery_action="record an approve decision through the host UI")
    proposal = {"actions": checkpoint.get("actions", [])}
    rendered = validate_proposal(
        workspace, checkpoint["manifest"], proposal,
        template_id=checkpoint["template_id"],
        apply_mode=checkpoint["apply_mode"],
        output_root=checkpoint.get("output_root"),
        documentation_path=checkpoint["documentation_path"],
        isolation_reason=checkpoint.get("isolation_reason"),
    )

    staged = []
    backups: dict[Path, bytes] = {}
    created: list[Path] = []
    for action in rendered["actions"]:
        destination = workspace / action["path"]
        parent = destination.parent.resolve()
        if not _within(parent, workspace):
            raise Blocked(stage=STAGE, reason_code="unsafe_path", detail=f"destination parent escapes workspace: {action['path']}", recovery_action="rebuild the proposal with workspace-relative paths")
        content = action["content"].encode("utf-8")
        if hashlib.sha256(content).hexdigest() != action["content_sha256"]:
            raise Blocked(stage=STAGE, reason_code="invalid_proposal", detail=f"content hash mismatch: {action['path']}", recovery_action="recreate the checkpoint")
        staged.append((action, destination, content))
        if action["action"] == "update":
            backups[destination] = destination.read_bytes()

    applied = []
    try:
        for action, destination, content in staged:
            _atomic_bytes(destination, content)
            if action["action"] == "create":
                created.append(destination)
            applied.append({"path": action["path"], "action": action["action"], "content_sha256": action["content_sha256"]})
    except OSError as error:
        for destination, data in backups.items():
            _atomic_bytes(destination, data)
        for destination in reversed(created):
            destination.unlink(missing_ok=True)
            parent = destination.parent
            while parent != workspace:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        raise Blocked(stage=STAGE, reason_code="capability_insufficient", detail=f"apply failed and was rolled back: {error}", recovery_action="resolve the filesystem error and retry the same pending checkpoint") from error

    checkpoint["status"] = "consumed"
    checkpoint["resolution"] = {"decision": "approve", "outcome": "applied", "actions": applied}
    checkpoint["consumed_at"] = "1970-01-01T00:00:00Z"
    checkpoint_path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": "consumed", "applied": applied}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args()
    qc_lib.run_main(STAGE, lambda: apply(Path(args.workspace), Path(args.checkpoint)))


if __name__ == "__main__":
    main()
