#!/usr/bin/env python3
"""Create, decide, inspect, and verify guided-upgrade checkpoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import qc_lib
from qc_lib import Blocked
from render_upgrade import validate_proposal

STAGE = "upgrade_state"
SCHEMA_VERSION = 3


def _load(path: Path) -> dict:
    payload = qc_lib.load_json_file(path, stage=STAGE)
    if payload.get("run_type") != "upgrade" or payload.get("schema_version") != SCHEMA_VERSION:
        raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail=f"not an upgrade checkpoint: {path}", recovery_action="pass a schema-version 3 upgrade checkpoint")
    return payload


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


def create(args: argparse.Namespace) -> dict:
    workspace = Path(args.workspace).resolve()
    state_dir = Path(args.state_dir).resolve()
    pending = _pending(state_dir)
    if pending:
        raise Blocked(stage=STAGE, reason_code="concurrent_run_active", detail=f"pending checkpoint already exists: {pending[0]}", recovery_action="resolve the existing QC or upgrade checkpoint first")
    manifest = qc_lib.load_json_file(args.manifest_json, stage=STAGE)
    findings = qc_lib.load_json_file(args.findings_json, stage=STAGE)
    gaps = qc_lib.load_json_file(args.gaps_json, stage=STAGE)
    proposal = qc_lib.load_json_file(args.proposal_json, stage=STAGE)
    rendered = validate_proposal(
        workspace, manifest, proposal,
        template_id=args.template_id,
        apply_mode=args.apply_mode,
        output_root=args.output_root,
        documentation_path=args.documentation_path,
        isolation_reason=args.isolation_reason,
    )
    source_targets = [entry["path"] for entry in manifest.get("candidates", [])]
    action_targets = [entry["path"] for entry in rendered["actions"]]
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "run_type": "upgrade",
        "run_id": args.run_id,
        "status": "pending_approval",
        "mechanism_path": manifest.get("mechanism_path"),
        "targets": sorted(set(source_targets + action_targets)),
        "profile": args.profile,
        "language": args.language,
        "template_id": args.template_id,
        "template_version": 1,
        "apply_mode": args.apply_mode,
        "output_root": args.output_root,
        "documentation_path": args.documentation_path,
        "isolation_reason": args.isolation_reason,
        "manifest": manifest,
        "findings": findings,
        "template_gaps": gaps,
        "actions": rendered["actions"],
        "plain_language_report": Path(args.report).read_text(encoding="utf-8"),
        "preview": rendered["preview"],
        "created_at": "1970-01-01T00:00:00Z",
    }
    state_dir.mkdir(parents=True, exist_ok=True)
    path = state_dir / f"checkpoint-{args.run_id}.json"
    if path.exists():
        raise Blocked(stage=STAGE, reason_code="destination_exists", detail=f"checkpoint exists: {path}", recovery_action="choose a new run id")
    path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"checkpoint_path": str(path), "status": "pending_approval", "preview": rendered["preview"]}


def decide(path: Path, decision: str) -> dict:
    payload = _load(path)
    if payload.get("status") != "pending_approval":
        raise Blocked(stage=STAGE, reason_code="checkpoint_already_consumed", detail=f"checkpoint status is {payload.get('status')}", recovery_action="use a pending upgrade checkpoint")
    if decision not in {"approve", "decline"}:
        raise Blocked(stage=STAGE, reason_code="invalid_decision", detail=f"upgrade decision must be approve or decline, got {decision}", recovery_action="pass approve or decline")
    if decision == "decline":
        payload["status"] = "aborted"
        payload["resolution"] = {"decision": "decline", "reason": "user_declined"}
    else:
        payload["approval"] = {"decision": "approve", "decided_at": "1970-01-01T00:00:00Z"}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"status": payload["status"], "decision": decision}


def verify(path: Path, findings_path: Path, gaps_path: Path, report_path: Path) -> dict:
    payload = _load(path)
    if payload.get("status") != "consumed":
        raise Blocked(stage=STAGE, reason_code="malformed_checkpoint", detail="verification requires a consumed upgrade checkpoint", recovery_action="apply the approved proposal first")
    findings = qc_lib.load_json_file(findings_path, stage=STAGE)
    gaps = qc_lib.load_json_file(gaps_path, stage=STAGE)
    verification = {
        "schema_version": 1,
        "run_id": payload["run_id"],
        "status": "all_passed" if not findings and not gaps else "failed",
        "findings": findings,
        "template_gaps": gaps,
        "report": report_path.read_text(encoding="utf-8"),
        "verified_at": "1970-01-01T00:00:00Z",
    }
    output = path.parent / f"verification-{payload['run_id']}.json"
    output.write_text(json.dumps(verification, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"verification_path": str(output), "status": verification["status"]}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create_parser = sub.add_parser("create")
    for name in ("workspace", "state-dir", "run-id", "profile", "language", "template-id", "apply-mode", "documentation-path", "manifest-json", "findings-json", "gaps-json", "proposal-json", "report"):
        create_parser.add_argument(f"--{name}", required=True)
    create_parser.add_argument("--output-root")
    create_parser.add_argument("--isolation-reason")
    decide_parser = sub.add_parser("decide")
    decide_parser.add_argument("--checkpoint", required=True)
    decide_parser.add_argument("--decision", required=True)
    status_parser = sub.add_parser("status")
    status_parser.add_argument("--checkpoint", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--checkpoint", required=True)
    verify_parser.add_argument("--findings-json", required=True)
    verify_parser.add_argument("--gaps-json", required=True)
    verify_parser.add_argument("--report", required=True)
    args = parser.parse_args()

    def body():
        if args.command == "create":
            return create(args)
        if args.command == "decide":
            return decide(Path(args.checkpoint), args.decision)
        if args.command == "status":
            payload = _load(Path(args.checkpoint))
            return {"status": payload["status"], "decision": (payload.get("approval") or {}).get("decision")}
        return verify(Path(args.checkpoint), Path(args.findings_json), Path(args.gaps_json), Path(args.report))
    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
