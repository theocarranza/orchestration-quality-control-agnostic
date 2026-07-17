#!/usr/bin/env python3
"""Build a deterministic, bounded manifest for an orchestration mechanism."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

import qc_lib
from qc_lib import Blocked, normalize_path

STAGE = "discover_structure"
MAX_FILES = 500
MAX_BYTES = 5 * 1024 * 1024
TEXT_SUFFIXES = {
    ".json", ".js", ".markdown", ".md", ".py", ".sh", ".toml",
    ".ts", ".yaml", ".yml",
}
EXCLUDED_DIRS = {
    ".git", ".orchestration-qc", "__pycache__", "build", "dist",
    "node_modules", "vendor",
}


def _blocked(reason_code: str, detail: str, recovery: str) -> Blocked:
    return Blocked(
        stage=STAGE,
        reason_code=reason_code,
        detail=detail,
        recovery_action=recovery,
    )


def _inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _roles(path: str) -> tuple[list[str], list[str]]:
    lowered = path.lower()
    basename = Path(path).name.lower()
    patterns = (
        ("orchestrator", "orchestrator"),
        ("validator", "validator"),
        ("remediator", "remediator"),
        ("proposal-author", "proposal-author"),
        ("workflow", "workflow"),
        ("rules-", "rules"),
        ("template", "template"),
        ("command", "command"),
        ("hook", "hook"),
        ("schema", "schema"),
        ("checkpoint", "state"),
        ("state", "state"),
        ("agent", "agent"),
    )
    roles = sorted({role for token, role in patterns if token in lowered})
    if basename == "skill.md":
        roles.append("skill")
    roles = sorted(set(roles or ["support"]))
    return roles, [f"path contains '{token}'" for token, role in patterns if role in roles and token in lowered]


def discover(workspace: Path, mechanism_path: str) -> dict:
    workspace = workspace.expanduser().resolve()
    rel = normalize_path(mechanism_path, stage=STAGE)
    requested = workspace / rel
    if not requested.exists():
        raise _blocked("missing_target", f"mechanism path does not exist: {rel}", "select an existing workspace-relative file or folder")
    resolved = requested.resolve()
    if not _inside(resolved, workspace):
        raise _blocked("unsafe_path", f"mechanism path resolves outside the workspace: {rel}", "select a path whose resolved location stays inside the workspace")

    candidates = [requested] if requested.is_file() else [
        path for path in sorted(requested.rglob("*"))
        if path.is_file()
        and path.suffix.lower() in TEXT_SUFFIXES
        and not any(part in EXCLUDED_DIRS for part in path.relative_to(requested).parts)
    ]
    if requested.is_file() and requested.suffix.lower() not in TEXT_SUFFIXES:
        candidates = []
    if not candidates:
        raise _blocked("missing_target", f"no supported orchestration files found under {rel}", "select a narrower folder containing text or configuration files")
    if len(candidates) > MAX_FILES:
        raise _blocked("capability_insufficient", f"discovery found {len(candidates)} files; limit is {MAX_FILES}", "select a narrower orchestration folder")

    entries = []
    total_bytes = 0
    for path in candidates:
        resolved_path = path.resolve()
        if not _inside(resolved_path, workspace):
            raise _blocked("unsafe_path", f"candidate resolves outside the workspace: {path}", "remove the escaping symlink or select a narrower folder")
        data = path.read_bytes()
        total_bytes += len(data)
        if total_bytes > MAX_BYTES:
            raise _blocked("capability_insufficient", f"candidate content exceeds {MAX_BYTES} bytes", "select a narrower orchestration folder")
        candidate_rel = path.relative_to(workspace).as_posix()
        roles, evidence = _roles(candidate_rel)
        entries.append({
            "path": candidate_rel,
            "sha256": hashlib.sha256(data).hexdigest(),
            "size": len(data),
            "roles": roles,
            "evidence": evidence,
        })
    return {
        "schema_version": 1,
        "mechanism_path": rel,
        "candidate_count": len(entries),
        "total_bytes": total_bytes,
        "candidates": entries,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--mechanism-path", required=True)
    args = parser.parse_args()
    qc_lib.run_main(STAGE, lambda: discover(Path(args.workspace), args.mechanism_path))


if __name__ == "__main__":
    main()
