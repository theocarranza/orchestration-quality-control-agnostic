#!/usr/bin/env python3
"""Decision arithmetic and resolution-completeness checking.

Two subcommands, meant to run either side of the Remediator's work:

  approved-set --checkpoint <file> --decision all|none|<id...>
      Resolves a decision against a checkpoint's findings into the set of
      approved finding ids. Blocked (unknown_finding_id) if a named id is not
      present in the checkpoint. Blocked (invalid_decision) on any other
      malformed decision value.

  finalize --checkpoint <file> --approved-ids <id...> --outcomes-json <file>
      Builds the full resolution array checkpoint_state.py consume expects.
      Every approved id must have a matching outcome entry (applied or
      skipped-with-reason) in outcomes-json, or this call is blocked — a
      quality gate must never silently treat an omitted finding as applied.
      Every id not in the approved set is auto-filled outcome 'declined'.
      Any outcome entry whose applied_path is outside checkpoint.targets is
      blocked (target_outside_approved_set): the Remediator only ever writes
      inside the set of paths the human approved for this run.
"""
import argparse

import qc_lib
from qc_lib import Blocked, normalize_path

STAGE = "reconcile_decision"


def _all_ids(checkpoint):
    return [finding["id"] for finding in checkpoint["findings"]]


def resolve_approved_set(checkpoint, decision):
    ids = _all_ids(checkpoint)
    if decision == "all":
        return list(ids)
    if decision == "none":
        return []
    if isinstance(decision, list):
        unknown = [d for d in decision if d not in ids]
        if unknown:
            raise Blocked(
                stage=STAGE,
                reason_code="unknown_finding_id",
                detail=f"decision names unknown finding id(s): {unknown}",
                recovery_action="only name finding ids present in the checkpoint's findings",
            )
        # de-duplicate, preserve checkpoint order
        approved = [i for i in ids if i in set(decision)]
        return approved
    raise Blocked(
        stage=STAGE,
        reason_code="invalid_decision",
        detail=f"decision must be 'all', 'none', or a list of finding ids; got {decision!r}",
        recovery_action="pass one of: 'all', 'none', ['finding-id', ...]",
    )


def finalize(checkpoint, approved_ids, outcomes):
    approved_set = set(approved_ids)
    all_ids = set(_all_ids(checkpoint))
    targets = set(checkpoint["targets"])

    outcomes_by_id = {}
    for entry in outcomes:
        qc_lib.require_fields(entry, ["finding_id", "outcome"], stage=STAGE)
        if entry["finding_id"] not in all_ids:
            raise Blocked(
                stage=STAGE,
                reason_code="unknown_finding_id",
                detail=f"outcome references unknown finding id: {entry['finding_id']}",
                recovery_action="only report outcomes for finding ids present in the checkpoint",
            )
        qc_lib.require_enum(
            entry["outcome"], {"applied", "skipped"}, "outcome", stage=STAGE
        )
        if entry["outcome"] == "skipped" and not entry.get("reason"):
            raise Blocked(
                stage=STAGE,
                reason_code="capability_insufficient",
                detail=f"finding {entry['finding_id']} is skipped without a reason",
                recovery_action="record why the edit could not be safely applied",
            )
        if entry.get("applied_path"):
            rel = normalize_path(entry["applied_path"], stage=STAGE)
            if rel not in targets:
                raise Blocked(
                    stage=STAGE,
                    reason_code="target_outside_approved_set",
                    detail=f"finding {entry['finding_id']} applied to '{rel}', outside checkpoint.targets",
                    recovery_action="remediation must stay within the checkpoint's approved target set",
                )
        outcomes_by_id[entry["finding_id"]] = entry

    missing = approved_set - set(outcomes_by_id)
    if missing:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"approved finding(s) have no reported outcome: {sorted(missing)}",
            recovery_action="every approved finding must end applied or skipped-with-reason before consume",
        )

    resolution = []
    for finding_id in _all_ids(checkpoint):
        if finding_id in approved_set:
            entry = outcomes_by_id[finding_id]
            resolution.append(
                {
                    k: v
                    for k, v in {
                        "finding_id": finding_id,
                        "outcome": entry["outcome"],
                        "reason": entry.get("reason"),
                    }.items()
                    if v is not None
                }
            )
        else:
            resolution.append({"finding_id": finding_id, "outcome": "declined"})
    return {"resolution": resolution}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_approved = sub.add_parser("approved-set")
    p_approved.add_argument("--checkpoint", required=True)
    p_approved.add_argument("--decision", nargs="+", required=True)

    p_finalize = sub.add_parser("finalize")
    p_finalize.add_argument("--checkpoint", required=True)
    p_finalize.add_argument("--approved-ids", nargs="*", default=[])
    p_finalize.add_argument("--outcomes-json", required=True)

    args = parser.parse_args()

    if args.command == "approved-set":
        def body():
            checkpoint = qc_lib.load_json_file(args.checkpoint, stage=STAGE)
            if args.decision in (["all"], ["none"]):
                decision = args.decision[0]
            else:
                decision = args.decision
            approved = resolve_approved_set(checkpoint, decision)
            return {"approved_ids": approved}
    else:
        def body():
            checkpoint = qc_lib.load_json_file(args.checkpoint, stage=STAGE)
            outcomes = qc_lib.load_json_file(args.outcomes_json, stage=STAGE)
            return finalize(checkpoint, args.approved_ids, outcomes)

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
