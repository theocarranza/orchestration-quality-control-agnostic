#!/usr/bin/env python3
"""Classify target files into document classes.

Usage:
    classify_targets.py --workspace <dir> [--profile <profile.json>] <target> [<target> ...]

Prints a JSON object {"classifications": [{"path": ..., "classes": [...]}]} on
stdout and exits 0, or a blocked payload and exits 2.

Built-in core classes mirror the taxonomy documented in
legacy/e2e-quality-control/README.md's "what-checks-what" table, generalized
away from Aplicatudo vocabulary: a target may match more than one class (for
example a document can be both 'workflow' and 'orchestrator'), matching the
original "a target may fall in multiple classes" behavior.
"""
import argparse
import fnmatch
import json
import sys
from pathlib import Path

import qc_lib
from qc_lib import Blocked, normalize_path

STAGE = "classify"

# Core, profile-independent classification. Globs are matched against the
# workspace-relative path. A rules file and a workflow file are recognized by
# name pattern, matching the templates/rules-template.md and
# templates/workflows-template.md conventions; 'generator-source' is anything
# that is itself a rules or workflow file feeding a downstream generator
# (recognized the same way — the distinguishing behavior lives in the QC rule
# that consumes the classification, not in the classifier).
CORE_CLASSIFICATION = [
    {"glob": "**/rules-*.md", "class": "rules-file"},
    {"glob": "**/workflows-*.md", "class": "workflow"},
    {"glob": "**/*.workflow.md", "class": "workflow"},
    {"glob": "**/orchestrator-*.md", "class": "orchestrator"},
    {"glob": "**/*orchestrator*.md", "class": "orchestrator"},
]


def load_profile_classification(profile_path):
    manifest = qc_lib.load_json_file(profile_path, stage=STAGE, reason_code="unknown_profile")
    qc_lib.require_fields(
        manifest, ["id", "classification"], stage=STAGE, reason_code="unknown_profile"
    )
    return manifest["classification"]


def _matches(rel_path, glob):
    if fnmatch.fnmatch(rel_path, glob):
        return True
    # fnmatch's '*' does not special-case '/', so a '**/<pattern>' glob only
    # matches when the target has at least one directory component before
    # the literal '/'. A target sitting at the workspace root (no directory
    # prefix) must still match against the basename alone.
    if glob.startswith("**/"):
        return fnmatch.fnmatch(Path(rel_path).name, glob[3:])
    return False


def classify_one(rel_path, rules):
    classes = set()
    for rule in rules:
        if _matches(rel_path, rule["glob"]):
            classes.add(rule["class"])
    if not classes:
        classes.add("unknown")
    return sorted(classes)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--profile", default=None)
    parser.add_argument("targets", nargs="+")
    args = parser.parse_args()

    def body():
        workspace = Path(args.workspace)
        rules = list(CORE_CLASSIFICATION)
        if args.profile:
            rules = rules + load_profile_classification(args.profile)

        classifications = []
        for raw_target in args.targets:
            rel = normalize_path(raw_target, stage=STAGE)
            abs_path = workspace / rel
            if not abs_path.exists():
                raise Blocked(
                    stage=STAGE,
                    reason_code="missing_target",
                    detail=f"target does not exist: {rel}",
                    recovery_action="pass a path that exists under the workspace",
                )
            if abs_path.is_dir():
                for child in sorted(abs_path.rglob("*")):
                    if child.is_file():
                        child_rel = str(child.relative_to(workspace))
                        classifications.append(
                            {"path": child_rel, "classes": classify_one(child_rel, rules)}
                        )
            else:
                classifications.append({"path": rel, "classes": classify_one(rel, rules)})

        return {"classifications": classifications}

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
