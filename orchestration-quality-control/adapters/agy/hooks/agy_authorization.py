#!/usr/bin/env python3
"""Create and clear adapter-only authorizations for approved OQC changes in Antigravity (AGY)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path


def _canonical_text(value: str) -> str:
    return value.replace("\r\n", "\n").rstrip("\n")


def change_digest(path: str, before: str, after: str) -> str:
    payload = {
        "after": _canonical_text(after),
        "before": _canonical_text(before),
        "path": Path(path).as_posix(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def checkpoint_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def authorization_path(checkpoint_path: Path, run_id: str) -> Path:
    return checkpoint_path.parent / f"agy-authorization-{run_id}.json"


def build_authorization(checkpoint_path: Path, approved_ids: list[str]) -> dict:
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    if checkpoint.get("status") != "pending_approval":
        raise ValueError("checkpoint must have status pending_approval")
    findings = {finding["id"]: finding for finding in checkpoint.get("findings", [])}
    unknown = sorted(set(approved_ids) - set(findings))
    if unknown:
        raise ValueError(f"unknown approved finding id(s): {unknown}")
    entries = []
    for finding_id in approved_ids:
        finding = findings[finding_id]
        target = Path(finding["location"]["path"]).as_posix()
        if target not in checkpoint.get("targets", []):
            raise ValueError(f"finding target is outside checkpoint targets: {target}")
        change = finding["suggested_change"]
        entries.append(
            {
                "finding_id": finding_id,
                "target": target,
                "change_sha256": change_digest(target, change["before"], change["after"]),
            }
        )
    return {
        "schema_version": 1,
        "run_id": checkpoint["run_id"],
        "checkpoint_sha256": checkpoint_digest(checkpoint_path),
        "approved_changes": entries,
    }


def _atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def create(checkpoint_path: Path, approved_ids: list[str]) -> Path:
    payload = build_authorization(checkpoint_path, approved_ids)
    path = authorization_path(checkpoint_path, payload["run_id"])
    _atomic_write(path, payload)
    return path


def clear(checkpoint_path: Path) -> Path:
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    path = authorization_path(checkpoint_path, checkpoint["run_id"])
    path.unlink(missing_ok=True)
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    create_parser = subparsers.add_parser("create")
    create_parser.add_argument("--checkpoint", required=True)
    create_parser.add_argument("--approved-ids", nargs="*", default=[])
    clear_parser = subparsers.add_parser("clear")
    clear_parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args()

    checkpoint_path = Path(args.checkpoint).resolve()
    if args.command == "create":
        destination = create(checkpoint_path, args.approved_ids)
        print(f"Created AGY authorization: {destination}")
    elif args.command == "clear":
        cleared = clear(checkpoint_path)
        print(f"Cleared AGY authorization: {cleared}")


if __name__ == "__main__":
    main()
