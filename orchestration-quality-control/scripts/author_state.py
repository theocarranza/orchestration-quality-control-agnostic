#!/usr/bin/env python3
"""Create, decide, and inspect greenfield-authoring checkpoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import qc_lib
import validation_evidence
from qc_lib import Blocked, normalize_path

STAGE = "author_state"
SCHEMA_VERSION = 1


def _now(supplied):
    """Real wall-clock time unless a caller supplies one.

    Every timestamp in this module used to be the literal string
    "1970-01-01T00:00:00Z", which made a checkpoint unable to say when it was
    created, approved, or consumed. Tests pass --now explicitly so they stay
    deterministic; production passes nothing and gets the real time.
    """
    if supplied:
        return supplied
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pending(state_dir: Path) -> list[str]:
    found = []
    if state_dir.is_dir():
        for path in sorted(state_dir.glob("checkpoint-*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("status") == "pending_approval":
                found.append(str(payload.get("run_id", path.stem)))
    return found


def _load(path: Path) -> dict:
    payload = qc_lib.load_json_file(path, stage=STAGE)
    if payload.get("run_type") != "author" or payload.get("schema_version") != SCHEMA_VERSION:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"not an author checkpoint: {path}",
            recovery_action="pass a schema-version 1 author checkpoint",
        )
    return payload


def _empty_output_root(workspace: Path, output_root: str) -> None:
    rel = normalize_path(output_root, stage=STAGE)
    destination = workspace / rel
    if not destination.exists():
        return
    if destination.is_file() or any(destination.rglob("*")):
        raise Blocked(
            stage=STAGE,
            reason_code="destination_exists",
            detail=f"output_root is not empty: {rel}",
            recovery_action="choose a missing or empty output_root",
        )


def _preview_files(preview_dir: Path, workspace: Path) -> dict[str, str]:
    if not preview_dir.is_dir():
        raise Blocked(
            stage=STAGE,
            reason_code="missing_target",
            detail=f"preview directory does not exist: {preview_dir}",
            recovery_action="draft process documents into a preview directory first",
        )
    files = {}
    for path in sorted(preview_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(preview_dir).as_posix()
        normalize_path(relative, stage=STAGE)
        files[relative] = path.read_text(encoding="utf-8")
    if not files:
        raise Blocked(
            stage=STAGE,
            reason_code="missing_target",
            detail="preview directory has no files",
            recovery_action="draft ARCHITECTURE.md, rules, and workflows before checkpointing",
        )
    return files


def create(args: argparse.Namespace) -> dict:
    workspace = Path(args.workspace).resolve()
    state_dir = Path(args.state_dir).resolve()
    pending = _pending(state_dir)
    if pending:
        raise Blocked(
            stage=STAGE,
            reason_code="concurrent_run_active",
            detail=f"pending checkpoint already exists: {pending[0]}",
            recovery_action="resolve the existing QC, upgrade, or author checkpoint first",
        )
    _empty_output_root(workspace, args.output_root)
    brief = qc_lib.load_json_file(args.brief_json, stage=STAGE)
    preview_files = _preview_files(Path(args.preview_dir), workspace)

    # Findings are read from the run's hash-chained mailbox, never accepted as a
    # caller-supplied file. See validation_evidence.py's module docstring: the
    # 2026-09-09 trial checkpointed a run as clean while its checking worker had
    # returned three findings, because the coordinator supplied "[]" here.
    digest = validation_evidence.proposal_digest(preview_files)
    verdict = validation_evidence.authoritative_findings(
        validation_evidence.load_mailbox(args.mailbox), digest=digest, run_id=args.run_id
    )
    findings = verdict["findings"]
    if not verdict["all_passed"]:
        raise Blocked(
            stage=STAGE,
            reason_code="qc_not_clean",
            detail=(
                f"the checking worker {verdict['worker']} returned {len(findings)} finding(s) "
                f"about this exact proposal (digest {digest[:12]}); a failing check cannot become "
                "an approvable delivery"
            ),
            recovery_action="rewrite the preview once and re-check, or stop with the findings",
        )
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "run_type": "author",
        "run_id": args.run_id,
        "status": "pending_approval",
        "targets": sorted(f"{args.output_root}/{path}" for path in preview_files),
        "profile": args.profile,
        "language": args.language,
        "output_root": args.output_root,
        "workspace_brief": brief,
        "findings": findings,
        "template_gaps": verdict["template_gaps"],
        "validation": {
            "worker": verdict["worker"],
            "envelope_id": verdict["envelope_id"],
            "inspected_digest": verdict["inspected_digest"],
            "head_hash": verdict["head_hash"],
            "all_passed": verdict["all_passed"],
        },
        "preview_files": preview_files,
        "plain_language_report": Path(args.report).read_text(encoding="utf-8"),
        "created_at": _now(args.now),
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"checkpoint-{args.run_id}.json"
    if path.exists():
        raise Blocked(
            stage=STAGE,
            reason_code="destination_exists",
            detail=f"checkpoint exists: {path}",
            recovery_action="choose a new run id",
        )
    path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"checkpoint_path": str(path), "status": "pending_approval"}


def decide(path: Path, decision: str, now: str = "") -> dict:
    payload = _load(path)
    if payload.get("status") != "pending_approval":
        raise Blocked(
            stage=STAGE,
            reason_code="checkpoint_already_consumed",
            detail=f"checkpoint status is {payload.get('status')}",
            recovery_action="use a pending author checkpoint",
        )
    if decision not in {"approve", "decline"}:
        raise Blocked(
            stage=STAGE,
            reason_code="invalid_decision",
            detail=f"author decision must be approve or decline, got {decision}",
            recovery_action="pass approve or decline",
        )
    now = _now(now)
    if decision == "decline":
        payload["status"] = "aborted"
        payload["resolution"] = {"decision": "decline", "reason": "user_declined"}
    else:
        payload["approval"] = {
            "decision": "approve",
            "decided_at": now,
            # Approval authorises writing already-checked content. Pinning the
            # digest here means apply can prove the package it is about to write
            # is the package that was approved.
            "approved_digest": (payload.get("validation") or {}).get("inspected_digest", ""),
        }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": payload["status"], "decision": decision}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create_parser = sub.add_parser("create")
    for name in (
        "workspace", "state-dir", "run-id", "profile", "language",
        "output-root", "brief-json", "mailbox", "preview-dir", "report",
    ):
        create_parser.add_argument(f"--{name}", required=True)
    create_parser.add_argument("--now", default="", help="RFC 3339 timestamp; real time when omitted")
    # Deliberately still accepted, and deliberately fatal. A caller reaching for
    # the old flag is reaching for the bypass; failing loudly beats silently
    # ignoring it.
    create_parser.add_argument("--findings-json", default=None, help=argparse.SUPPRESS)
    decide_parser = sub.add_parser("decide")
    decide_parser.add_argument("--checkpoint", required=True)
    decide_parser.add_argument("--decision", required=True)
    decide_parser.add_argument("--now", default="")
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--checkpoint", required=True)
    args = parser.parse_args()

    def body():
        if args.command == "create":
            if args.findings_json is not None:
                raise Blocked(
                    stage=STAGE,
                    reason_code="invalid_decision",
                    detail=(
                        "--findings-json is no longer accepted: findings are read from the run's "
                        "mailbox, not supplied by the caller"
                    ),
                    recovery_action="pass --mailbox pointing at the run's envelope log",
                )
            return create(args)
        if args.command == "decide":
            return decide(Path(args.checkpoint), args.decision, args.now)
        payload = _load(Path(args.checkpoint))
        return {"status": payload["status"], "decision": (payload.get("approval") or {}).get("decision")}

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
