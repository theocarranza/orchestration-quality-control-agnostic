#!/usr/bin/env python3
"""Render a finding's suggested_change as a literal unified diff.

Findings are presented to the human as diffs, never as prose paraphrases of an
edit. This is deliberate injection containment (see the critique's F7): a
target file cannot get a malicious edit approved by describing it attractively
in prose if the only thing the human ever sees is the literal text change
against the real file.

Usage:
    render_diff.py --workspace <dir> --path <rel> --before <text-file> --after <text-file>

Blocked (anchor_not_found) if 'before' is not present verbatim in the target.
"""
import argparse
import difflib
from pathlib import Path

import qc_lib
from qc_lib import Blocked, normalize_path

STAGE = "render_diff"


def render(workspace, rel_path, before, after):
    abs_path = Path(workspace) / normalize_path(rel_path, stage=STAGE)
    if not abs_path.exists():
        raise Blocked(
            stage=STAGE,
            reason_code="missing_target",
            detail=f"target does not exist: {rel_path}",
            recovery_action="pass a path that exists under the workspace",
        )
    original = abs_path.read_text(encoding="utf-8")
    if before not in original:
        raise Blocked(
            stage=STAGE,
            reason_code="anchor_not_found",
            detail=f"'before' text not found verbatim in {rel_path}",
            recovery_action="re-derive the suggested_change from the current file content",
        )
    updated = original.replace(before, after, 1)
    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(keepends=True),
            updated.splitlines(keepends=True),
            fromfile=rel_path,
            tofile=rel_path,
        )
    )
    return {"diff": "".join(diff_lines), "updated_content": updated}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--path", required=True)
    parser.add_argument("--before", required=True, help="path to a file containing the verbatim 'before' text")
    parser.add_argument("--after", required=True, help="path to a file containing the 'after' text")
    args = parser.parse_args()

    def body():
        before_text = Path(args.before).read_text(encoding="utf-8")
        after_text = Path(args.after).read_text(encoding="utf-8")
        return render(args.workspace, args.path, before_text, after_text)

    qc_lib.run_main(STAGE, body)


if __name__ == "__main__":
    main()
