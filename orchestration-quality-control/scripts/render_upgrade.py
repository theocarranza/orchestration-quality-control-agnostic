#!/usr/bin/env python3
"""Validate and render an atomic orchestration-upgrade proposal."""

from __future__ import annotations

import argparse
import difflib
import hashlib
from pathlib import Path, PurePosixPath

import qc_lib
from qc_lib import Blocked, normalize_path

STAGE = "render_upgrade"
TEMPLATES = {"isolated-three-agent"}
APPLY_MODES = {"side-by-side", "in-place"}


def _fail(reason: str, detail: str, recovery: str) -> None:
    raise Blocked(stage=STAGE, reason_code=reason, detail=detail, recovery_action=recovery)


def _inside_path(path: str, parent: str) -> bool:
    candidate = PurePosixPath(path)
    root = PurePosixPath(parent)
    return candidate == root or root in candidate.parents


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_proposal(
    workspace: Path,
    manifest: dict,
    proposal: dict,
    *,
    template_id: str,
    apply_mode: str,
    output_root: str | None,
    documentation_path: str,
) -> dict:
    if template_id not in TEMPLATES:
        _fail("invalid_template", f"unknown template: {template_id}", f"choose one of {sorted(TEMPLATES)}")
    if apply_mode not in APPLY_MODES:
        _fail("invalid_proposal", f"unknown apply mode: {apply_mode}", f"choose one of {sorted(APPLY_MODES)}")
    actions = proposal.get("actions")
    if not isinstance(actions, list) or not actions:
        _fail("invalid_proposal", "proposal.actions must be a non-empty list", "return at least one create or update action")
    documentation_path = normalize_path(documentation_path, stage=STAGE)
    normalized_output = normalize_path(output_root, stage=STAGE) if output_root else None
    if apply_mode == "side-by-side" and not normalized_output:
        _fail("invalid_proposal", "side-by-side mode requires output_root", "select a workspace-relative version directory")
    if apply_mode == "side-by-side" and (workspace / normalized_output).exists():
        _fail("destination_exists", f"output root already exists: {normalized_output}", "choose a new version directory")

    source_paths = {entry["path"]: entry for entry in manifest.get("candidates", [])}
    seen = set()
    rendered = []
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            _fail("invalid_proposal", f"action {index} is not an object", "return schema-conformant actions")
        kind = action.get("action")
        if kind not in {"create", "update"}:
            _fail("invalid_proposal", f"action {index} uses forbidden action '{kind}'", "use only create or update")
        path = normalize_path(str(action.get("path", "")), stage=STAGE)
        if not path or path == "." or path in seen:
            _fail("invalid_proposal", f"action path is empty or duplicated: {path}", "use one unique workspace-relative path per action")
        seen.add(path)
        content = action.get("content")
        if not isinstance(content, str):
            _fail("invalid_proposal", f"action {path} has no text content", "provide the complete proposed file content")
        if not isinstance(action.get("rationale"), str) or not action["rationale"].strip():
            _fail("invalid_proposal", f"action {path} has no rationale", "trace every action to a finding or template invariant")
        if not isinstance(action.get("trace_ids", []), list):
            _fail("invalid_proposal", f"action {path} trace_ids is not a list", "provide a list of finding or gap ids")

        destination = workspace / path
        if apply_mode == "side-by-side":
            if not _inside_path(path, normalized_output):
                _fail("target_outside_approved_set", f"side-by-side action escapes output_root: {path}", "place every proposed file under output_root")
            if kind != "create":
                _fail("invalid_proposal", f"side-by-side action must create, not update: {path}", "render the new version entirely as create actions")
        else:
            if kind == "update" and path not in source_paths:
                _fail("target_outside_approved_set", f"in-place update is not a discovered source: {path}", "update only confirmed manifest candidates")
            if kind == "create" and path != documentation_path:
                _fail("target_outside_approved_set", f"in-place create is not the documentation path: {path}", "create only the approved architecture document")

        if kind == "create":
            if destination.exists():
                _fail("destination_exists", f"create destination exists: {path}", "choose a new destination or use an approved update")
            before = ""
            diff = "".join(difflib.unified_diff([], content.splitlines(keepends=True), fromfile="/dev/null", tofile=path))
            source_sha = None
        else:
            if not destination.is_file():
                _fail("missing_target", f"update target does not exist: {path}", "refresh discovery and rebuild the proposal")
            before = destination.read_text(encoding="utf-8")
            expected = action.get("source_sha256")
            actual = hashlib.sha256(destination.read_bytes()).hexdigest()
            if expected != actual or source_paths[path].get("sha256") != actual:
                _fail("stale_target", f"source hash changed for {path}", "rerun discovery and rebuild the proposal")
            diff = "".join(difflib.unified_diff(before.splitlines(keepends=True), content.splitlines(keepends=True), fromfile=path, tofile=path))
            source_sha = actual
        rendered.append({
            **action,
            "path": path,
            "source_sha256": source_sha,
            "content_sha256": _sha(content),
            "diff": diff,
        })
    if documentation_path not in seen:
        _fail("invalid_proposal", f"proposal does not include documentation_path: {documentation_path}", "include ARCHITECTURE.md in the atomic proposal")
    return {"actions": rendered, "preview": "\n".join(item["diff"] for item in rendered)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--proposal", required=True)
    parser.add_argument("--template-id", required=True)
    parser.add_argument("--apply-mode", required=True)
    parser.add_argument("--output-root")
    parser.add_argument("--documentation-path", required=True)
    args = parser.parse_args()
    qc_lib.run_main(STAGE, lambda: validate_proposal(
        Path(args.workspace).resolve(),
        qc_lib.load_json_file(args.manifest, stage=STAGE),
        qc_lib.load_json_file(args.proposal, stage=STAGE),
        template_id=args.template_id,
        apply_mode=args.apply_mode,
        output_root=args.output_root,
        documentation_path=args.documentation_path,
    ))


if __name__ == "__main__":
    main()
