#!/usr/bin/env python3
"""The checkpoint state machine: pending_approval -> consumed | aborted.

Filename convention: <state-dir>/checkpoint-<run_id>.json, run_id = <YYYYMMDD>-<slug>.

There is no marker file anywhere in this design. The single observable for
"is a run active?" is: does a checkpoint with status == pending_approval exist
under the documented state directory? Every host adapter must answer that
question the same way — see checkpoint.schema.json and the critique's F6
finding about the old design naming an observable ('is_run_active') without
specifying it.

Subcommands:

  create   --state-dir <dir> --run-id <id> --targets <path...> --profile <id>
           --language <en|pt-br> --findings-json <file> --report <text-file>
      Refuses (concurrent_run_active) if another pending_approval checkpoint
      already exists under state-dir.

  status   --state-dir <dir> --run-id <id>
      Emits {"status": "pending_approval"|"consumed"|"aborted"|"absent"}.

  is-run-active --state-dir <dir>
      Emits {"active": bool, "run_id": str|null}. True iff exactly one
      pending_approval checkpoint exists under state-dir.

  consume  --state-dir <dir> --run-id <id> --resolution-json <file>
      Moves pending_approval -> consumed. Refuses unless every finding in the
      checkpoint has a resolution entry (fail-closed: never silently treat an
      omitted finding as applied or a skipped edit as successful).

  abort    --state-dir <dir> --run-id <id> --reason <text>
      Moves pending_approval -> aborted.
"""
import argparse
import json
from pathlib import Path

import qc_lib
from qc_lib import Blocked

STAGE = "checkpoint_state"
SCHEMA_VERSION = 2


def _checkpoint_path(state_dir, run_id):
    return Path(state_dir) / f"checkpoint-{run_id}.json"


def _find_pending(state_dir):
    state_path = Path(state_dir)
    if not state_path.exists():
        return []
    pending = []
    for candidate in sorted(state_path.glob("checkpoint-*.json")):
        try:
            data = json.loads(candidate.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if data.get("status") == "pending_approval":
            pending.append(data.get("run_id"))
    return pending


def create(state_dir, run_id, targets, profile, language, findings, report):
    pending = _find_pending(state_dir)
    if pending:
        raise Blocked(
            stage=STAGE,
            reason_code="concurrent_run_active",
            detail=f"a pending_approval checkpoint already exists: run_id {pending[0]}",
            recovery_action="resolve the existing checkpoint (execute or abort) before starting a new run",
        )
    checkpoint = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "status": "pending_approval",
        "targets": targets,
        "profile": profile,
        "language": language,
        "findings": findings,
        "plain_language_report": report,
        "created_at": "1970-01-01T00:00:00Z",
    }
    Path(state_dir).mkdir(parents=True, exist_ok=True)
    path = _checkpoint_path(state_dir, run_id)
    path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")
    return {"checkpoint_path": str(path), "status": "pending_approval"}


def _load_checkpoint(state_dir, run_id):
    path = _checkpoint_path(state_dir, run_id)
    if not path.exists():
        return None, path
    return qc_lib.load_json_file(path, stage=STAGE), path


def status(state_dir, run_id):
    checkpoint, _ = _load_checkpoint(state_dir, run_id)
    if checkpoint is None:
        return {"status": "absent"}
    return {"status": checkpoint["status"]}


def is_run_active(state_dir):
    pending = _find_pending(state_dir)
    if len(pending) > 1:
        raise Blocked(
            stage=STAGE,
            reason_code="concurrent_run_active",
            detail=f"multiple pending_approval checkpoints found: {pending}",
            recovery_action="resolve all but one checkpoint before continuing",
        )
    if pending:
        return {"active": True, "run_id": pending[0]}
    return {"active": False, "run_id": None}


def consume(state_dir, run_id, resolution):
    checkpoint, path = _load_checkpoint(state_dir, run_id)
    if checkpoint is None:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"no checkpoint found for run_id {run_id}",
            recovery_action="verify run_id and state_dir",
        )
    if checkpoint["status"] != "pending_approval":
        raise Blocked(
            stage=STAGE,
            reason_code="checkpoint_already_consumed",
            detail=f"checkpoint status is '{checkpoint['status']}', expected 'pending_approval'",
            recovery_action="do not re-consume a checkpoint that already left pending_approval",
        )
    missing_outcome = [
        entry for entry in resolution if entry.get("outcome") not in ("applied", "skipped", "declined")
    ]
    if missing_outcome:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail="every resolution entry must have outcome applied, skipped, or declined",
            recovery_action="supply a valid outcome for every resolved finding",
        )
    for entry in resolution:
        if entry.get("outcome") == "skipped" and not entry.get("reason"):
            raise Blocked(
                stage=STAGE,
                reason_code="malformed_checkpoint",
                detail=f"finding {entry['finding_id']} is skipped without a reason",
                recovery_action="record why the finding could not be applied (e.g. capability_insufficient)",
            )
    checkpoint["status"] = "consumed"
    checkpoint["resolution"] = resolution
    path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")
    return {"status": "consumed", "resolved": len(resolution)}


def abort(state_dir, run_id, reason):
    checkpoint, path = _load_checkpoint(state_dir, run_id)
    if checkpoint is None:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"no checkpoint found for run_id {run_id}",
            recovery_action="verify run_id and state_dir",
        )
    if checkpoint["status"] != "pending_approval":
        raise Blocked(
            stage=STAGE,
            reason_code="checkpoint_already_consumed",
            detail=f"checkpoint status is '{checkpoint['status']}', cannot abort",
            recovery_action="only a pending_approval checkpoint can be aborted",
        )
    checkpoint["status"] = "aborted"
    checkpoint["resolution"] = [{"finding_id": "*", "outcome": "declined", "reason": reason}]
    path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True), encoding="utf-8")
    return {"status": "aborted"}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_create = sub.add_parser("create")
    p_create.add_argument("--state-dir", required=True)
    p_create.add_argument("--run-id", required=True)
    p_create.add_argument("--targets", nargs="+", required=True)
    p_create.add_argument("--profile", required=True)
    p_create.add_argument("--language", required=True)
    p_create.add_argument("--findings-json", required=True)
    p_create.add_argument("--report", required=True)

    p_status = sub.add_parser("status")
    p_status.add_argument("--state-dir", required=True)
    p_status.add_argument("--run-id", required=True)

    p_active = sub.add_parser("is-run-active")
    p_active.add_argument("--state-dir", required=True)

    p_consume = sub.add_parser("consume")
    p_consume.add_argument("--state-dir", required=True)
    p_consume.add_argument("--run-id", required=True)
    p_consume.add_argument("--resolution-json", required=True)

    p_abort = sub.add_parser("abort")
    p_abort.add_argument("--state-dir", required=True)
    p_abort.add_argument("--run-id", required=True)
    p_abort.add_argument("--reason", required=True)

    args = parser.parse_args()

    if args.command == "create":
        def body():
            findings = qc_lib.load_json_file(args.findings_json, stage=STAGE)
            report = Path(args.report).read_text(encoding="utf-8")
            return create(
                args.state_dir, args.run_id, args.targets, args.profile,
                args.language, findings, report,
            )
    elif args.command == "status":
        def body():
            return status(args.state_dir, args.run_id)
    elif args.command == "is-run-active":
        def body():
            return is_run_active(args.state_dir)
    elif args.command == "consume":
        def body():
            resolution = qc_lib.load_json_file(args.resolution_json, stage=STAGE)
            return consume(args.state_dir, args.run_id, resolution)
    else:
        def body():
            return abort(args.state_dir, args.run_id, args.reason)

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
