#!/usr/bin/env python3
"""Stage a package evals.json into a skill-creator-compatible benchmark workspace.

Reads a package's evals.json (`assertions: [{id, text}, ...]` per eval) and,
for each eval, creates `<workspace>/eval-<slug>/` with:
  - eval_metadata.json: {eval_id, eval_name, prompt, assertions: [text, ...]}
    in the shape skill-creator's aggregate_benchmark.py and grader expect.
  - sandbox/: a copy of the eval's fixture file(s), resolved relative to the
    evals.json's own directory, so with_skill/without_skill runs can be
    pointed at a directory containing only the intended input — nothing
    else in the package or repo.

Non-destructive: never writes into the source evals.json or its fixtures.
Re-running overwrites only files this script itself created (safe to redo
after fixing a fixture).

Usage:
  convert_evals.py <evals.json> <workspace_dir>
"""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path


def slugify(files: list[str]) -> str:
    first = files[0].rstrip("/")
    name = Path(first).name
    stem = Path(name).stem if "." in name else name
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    if not slug:
        raise ValueError(f"could not derive a slug from files: {files}")
    return slug


def stage_fixture(src: Path, sandbox: Path) -> None:
    if src.is_dir():
        dest = sandbox / src.name
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(src, dest)
    else:
        shutil.copy2(src, sandbox / src.name)


def stage_eval(eval_obj: dict, evals_dir: Path, workspace: Path) -> Path:
    slug = slugify(eval_obj["files"])
    eval_dir = workspace / f"eval-{slug}"
    sandbox = eval_dir / "sandbox"
    sandbox.mkdir(parents=True, exist_ok=True)

    for rel in eval_obj["files"]:
        src = evals_dir / rel.rstrip("/")
        if not src.exists():
            raise FileNotFoundError(f"fixture not found: {src}")
        stage_fixture(src, sandbox)

    metadata = {
        "eval_id": eval_obj["id"],
        "eval_name": slug,
        "prompt": eval_obj["prompt"],
        "assertions": [a["text"] for a in eval_obj["assertions"]],
    }
    (eval_dir / "eval_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return eval_dir


def convert(evals_json_path: Path, workspace: Path) -> list[Path]:
    data = json.loads(evals_json_path.read_text())
    evals_dir = evals_json_path.parent
    workspace.mkdir(parents=True, exist_ok=True)
    return [stage_eval(e, evals_dir, workspace) for e in data["evals"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evals_json", type=Path)
    parser.add_argument("workspace_dir", type=Path)
    args = parser.parse_args()

    if not args.evals_json.exists():
        print(f"Not found: {args.evals_json}", file=sys.stderr)
        sys.exit(1)

    eval_dirs = convert(args.evals_json, args.workspace_dir)
    for d in eval_dirs:
        print(f"Staged: {d}")


if __name__ == "__main__":
    main()
