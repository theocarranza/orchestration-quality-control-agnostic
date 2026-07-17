#!/usr/bin/env python3
"""Deterministic run-integrity evidence for the eval-benchmark harness.

Two assertion families in these eval sets ask something a grader should not
have to take on faith: whether the target fixture was left unedited before
an explicit apply step, and whether the run stayed inside its sandbox
instead of reading unrelated project files. Both are answered here from
file hashes and a transcript scan, so the grader cites this file's output as
evidence for those two assertions instead of a subjective read.

The isolation check is a heuristic, not a proof: it flags path-like tokens
in the transcript that are not part of the sandbox or an allowed prefix.
It can under- or over-flag on unusual transcript phrasing. Treat
`paths_outside_sandbox` as evidence for the grader to weigh, not an
automatic fail.

Two subcommands:

  snapshot <sandbox_dir> -o <hashes.json>
      Records sha256 of every file under sandbox_dir, keyed by path relative
      to sandbox_dir. Run this once, before the executor subagent starts.

  verify <sandbox_dir> <baseline_hashes.json> --transcript <transcript.md>
         [--allow <prefix> ...] -o <integrity.json>
      Recomputes hashes and diffs against the baseline (-> unedited /
      changed_files / added_files / removed_files). Scans the transcript for
      file-like paths; anything outside sandbox_dir and not matching an
      --allow prefix is recorded under paths_outside_sandbox
      (-> isolation_ok). Run this once, after the run completes.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

PATH_PATTERN = re.compile(r"[A-Za-z0-9_\-./]+\.[A-Za-z0-9]+")


def hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def snapshot(sandbox_dir: Path) -> dict:
    return {
        str(p.relative_to(sandbox_dir)): hash_file(p)
        for p in sorted(sandbox_dir.rglob("*"))
        if p.is_file()
    }


def diff_snapshots(baseline: dict, current: dict) -> dict:
    changed = sorted(k for k in baseline if k in current and baseline[k] != current[k])
    added = sorted(k for k in current if k not in baseline)
    removed = sorted(k for k in baseline if k not in current)
    return {
        "unedited": not changed and not added and not removed,
        "changed_files": changed,
        "added_files": added,
        "removed_files": removed,
    }


def extract_paths(transcript_text: str) -> set[str]:
    return set(PATH_PATTERN.findall(transcript_text))


def check_isolation(transcript_text: str, sandbox_dir: Path, allow_prefixes: list[str]) -> dict:
    sandbox_names = {p.name for p in sandbox_dir.rglob("*") if p.is_file()}
    mentioned = extract_paths(transcript_text)
    outside = sorted(
        p for p in mentioned
        if Path(p).name not in sandbox_names
        and not any(p.startswith(prefix) for prefix in allow_prefixes)
    )
    return {
        "isolation_ok": not outside,
        "paths_outside_sandbox": outside,
        "allow_prefixes": allow_prefixes,
    }


def cmd_snapshot(args: argparse.Namespace) -> None:
    hashes = snapshot(args.sandbox_dir)
    args.output.write_text(json.dumps(hashes, indent=2) + "\n")
    print(f"Wrote: {args.output}")


def cmd_verify(args: argparse.Namespace) -> None:
    baseline = json.loads(args.baseline_hashes.read_text())
    current = snapshot(args.sandbox_dir)
    result = diff_snapshots(baseline, current)

    transcript_text = args.transcript.read_text() if args.transcript else ""
    result.update(check_isolation(transcript_text, args.sandbox_dir, args.allow or []))

    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote: {args.output}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    p_snap = sub.add_parser("snapshot")
    p_snap.add_argument("sandbox_dir", type=Path)
    p_snap.add_argument("-o", "--output", type=Path, required=True)
    p_snap.set_defaults(func=cmd_snapshot)

    p_verify = sub.add_parser("verify")
    p_verify.add_argument("sandbox_dir", type=Path)
    p_verify.add_argument("baseline_hashes", type=Path)
    p_verify.add_argument("--transcript", type=Path)
    p_verify.add_argument("--allow", action="append")
    p_verify.add_argument("-o", "--output", type=Path, required=True)
    p_verify.set_defaults(func=cmd_verify)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
