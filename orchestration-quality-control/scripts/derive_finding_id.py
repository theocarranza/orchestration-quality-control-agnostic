#!/usr/bin/env python3
"""Derive and verify content-anchored finding identifiers.

id = "<rule-code>-<kind-shortname>-<hash10>[-<occurrence>]"
hash10 = first 10 hex chars of SHA-256 over:
    normalize_path(path) + "\\x00" + rule_code + "\\x00" + kind + "\\x00" + normalize_text(anchor)

No line numbers ever enter the hash. This is deliberate: a partial "apply
some" run can shift every line after an edit, and re-validation after that
edit must still recognize an untouched finding as the same finding. See
references/schemas/finding.schema.json and the critique's Gap 4 (F4) on
finding-id design.

Two subcommands:

  derive  --workspace <dir> --path <rel> --rule <file.md#CODE> --kind <ns/name>
          --anchor-text <text> [--occurrence-of <existing-ids-json>]
      Emits {"id": "..."} after checking the anchor is present in the target
      file (normalized substring search). Blocked with anchor_not_found if not.

  verify  --workspace <dir> --checkpoint <checkpoint.json>
      Re-anchors every finding in a checkpoint against current file contents.
      Emits {"results": [{"id": ..., "still_open": bool}]}. A finding whose
      anchor is no longer present is resolved (still_open: false); this is how
      re-validation after a partial apply works without touching any id.
"""
import argparse
import hashlib
import re
import sys
from pathlib import Path

import qc_lib
from qc_lib import Blocked, normalize_path, normalize_text

STAGE = "derive_finding_id"

RULE_CODE_RE = re.compile(r"^[a-z0-9-]+\.md#([A-Za-z0-9]+)$")
KIND_RE = re.compile(r"^[a-z0-9-]+/[a-z0-9-]+$")


def _rule_shortcode(rule):
    match = RULE_CODE_RE.match(rule)
    if not match:
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"rule '{rule}' does not match '<file>.md#<CODE>'",
            recovery_action="pass rule as '<rules-file>.md#<rule-code>'",
        )
    return match.group(1)


def _kind_shortname(kind):
    if not KIND_RE.match(kind):
        raise Blocked(
            stage=STAGE,
            reason_code="malformed_checkpoint",
            detail=f"kind '{kind}' does not match '<namespace>/<name>'",
            recovery_action="use a namespaced kind, see references/schemas/kinds.md",
        )
    return kind.split("/", 1)[1]


def anchor_present(file_text, anchor):
    return normalize_text(anchor) in normalize_text(file_text)


def compute_hash10(rel_path, rule, kind, anchor):
    normalized = "\x00".join(
        [normalize_path(rel_path, stage=STAGE), rule, kind, normalize_text(anchor)]
    )
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return digest[:10]


def derive(workspace, rel_path, rule, kind, anchor, existing_ids):
    abs_path = Path(workspace) / normalize_path(rel_path, stage=STAGE)
    if not abs_path.exists():
        raise Blocked(
            stage=STAGE,
            reason_code="missing_target",
            detail=f"target does not exist: {rel_path}",
            recovery_action="pass a path that exists under the workspace",
        )
    file_text = abs_path.read_text(encoding="utf-8")
    if not anchor_present(file_text, anchor):
        raise Blocked(
            stage=STAGE,
            reason_code="anchor_not_found",
            detail=f"anchor text not found verbatim in {rel_path}",
            recovery_action=(
                "the finding must quote real text from the target; "
                "re-derive the anchor from the actual file content"
            ),
        )
    rule_code = _rule_shortcode(rule)
    kind_short = _kind_shortname(kind)
    hash10 = compute_hash10(rel_path, rule, kind, anchor)
    base_id = f"{rule_code}-{kind_short}-{hash10}"

    occurrence = 1
    for existing in existing_ids:
        if existing == base_id or existing.startswith(base_id + "-"):
            occurrence += 1
    finding_id = base_id if occurrence == 1 else f"{base_id}-{occurrence}"
    return {"id": finding_id}


def verify(workspace, checkpoint_path):
    checkpoint = qc_lib.load_json_file(checkpoint_path, stage=STAGE)
    qc_lib.require_fields(checkpoint, ["findings"], stage=STAGE)
    results = []
    for finding in checkpoint["findings"]:
        qc_lib.require_fields(finding, ["id", "location", "anchor"], stage=STAGE)
        rel_path = finding["location"]["path"]
        abs_path = Path(workspace) / normalize_path(rel_path, stage=STAGE)
        if not abs_path.exists():
            results.append({"id": finding["id"], "still_open": False})
            continue
        file_text = abs_path.read_text(encoding="utf-8")
        still_open = anchor_present(file_text, finding["anchor"])
        results.append({"id": finding["id"], "still_open": still_open})
    return {"results": results}


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p_derive = sub.add_parser("derive")
    p_derive.add_argument("--workspace", required=True)
    p_derive.add_argument("--path", required=True)
    p_derive.add_argument("--rule", required=True)
    p_derive.add_argument("--kind", required=True)
    p_derive.add_argument("--anchor-text", required=True)
    p_derive.add_argument("--existing-ids", nargs="*", default=[])

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("--workspace", required=True)
    p_verify.add_argument("--checkpoint", required=True)

    args = parser.parse_args()

    if args.command == "derive":
        def body():
            return derive(
                args.workspace, args.path, args.rule, args.kind,
                args.anchor_text, args.existing_ids,
            )
    else:
        def body():
            return verify(args.workspace, args.checkpoint)

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
