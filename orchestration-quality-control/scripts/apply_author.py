#!/usr/bin/env python3
"""Apply exactly one approved authoring checkpoint into an empty output_root."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path

import qc_lib
from qc_lib import Blocked, normalize_path

STAGE = "apply_author"


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
    if checkpoint.get("run_type") != "author" or checkpoint.get("status") != "pending_approval":
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail="checkpoint is not a pending author run",
            recovery_action="pass a pending author checkpoint",
        )
    if (checkpoint.get("approval") or {}).get("decision") != "approve":
        raise Blocked(
            stage=STAGE,
            reason_code="invalid_decision",
            detail="author checkpoint has no explicit approval",
            recovery_action="record an approve decision through the host UI",
        )
    output_root = normalize_path(checkpoint["output_root"], stage=STAGE)
    destination_root = workspace / output_root
    if destination_root.exists() and (destination_root.is_file() or any(destination_root.rglob("*"))):
        raise Blocked(
            stage=STAGE,
            reason_code="destination_exists",
            detail=f"output_root is not empty: {output_root}",
            recovery_action="choose a missing or empty output_root",
        )
    preview_files = checkpoint.get("preview_files") or {}
    if not preview_files:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail="author checkpoint has no preview files",
            recovery_action="recreate the author checkpoint",
        )
    created: list[Path] = []
    applied = []
    try:
        for relative, content in preview_files.items():
            rel = normalize_path(relative, stage=STAGE)
            destination = (destination_root / rel).resolve()
            if not _within(destination, workspace):
                raise Blocked(
                    stage=STAGE,
                    reason_code="unsafe_path",
                    detail=f"preview path escapes workspace: {rel}",
                    recovery_action="rebuild the preview with workspace-relative paths",
                )
            _atomic_bytes(destination, content.encode("utf-8"))
            created.append(destination)
            applied.append({"path": f"{output_root}/{rel}", "action": "create"})
    except OSError as error:
        for destination in reversed(created):
            destination.unlink(missing_ok=True)
            parent = destination.parent
            while parent != workspace:
                try:
                    parent.rmdir()
                except OSError:
                    break
                parent = parent.parent
        raise Blocked(
            stage=STAGE,
            reason_code="capability_insufficient",
            detail=f"apply failed and was rolled back: {error}",
            recovery_action="resolve the filesystem error and retry the same pending checkpoint",
        ) from error
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
