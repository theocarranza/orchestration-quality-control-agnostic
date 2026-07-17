#!/usr/bin/env python3
"""Build and install the complete OQC Cursor plugin for local use."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_NAME = "orchestration-quality-control"
RECORD_NAME = "oqc-cursor-adapter-install.json"


def _here() -> Path:
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    return _here().parents[2]


def _generated_distribution() -> bool:
    return (_here() / "plugins" / PLUGIN_NAME).is_dir()


def _marketplace_root() -> Path:
    if _generated_distribution():
        return _here()
    return _repo_root() / "dist" / "cursor-marketplace"


def _plugin_source() -> Path:
    return _marketplace_root() / "plugins" / PLUGIN_NAME


def _build_script() -> Path:
    return _here() / "build_plugin.py"


def _cursor_home(args: argparse.Namespace) -> Path:
    return Path(args.cursor_home or os.environ.get("CURSOR_HOME") or Path.home() / ".cursor").expanduser().resolve()


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    local_root = _cursor_home(args) / "plugins" / "local"
    return local_root, local_root / PLUGIN_NAME, local_root / RECORD_NAME


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _run_build(args: argparse.Namespace) -> int:
    if _generated_distribution():
        return 0
    command = [sys.executable, str(_build_script())]
    print("$ " + " ".join(command))
    if args.dry_run:
        return 0
    try:
        return subprocess.run(command, check=False).returncode
    except FileNotFoundError as error:
        print(f"Blocked: required command is unavailable: {error.filename}", file=sys.stderr)
        return 127


def install(args: argparse.Namespace) -> int:
    result = _run_build(args)
    if result:
        return result
    local_root, destination, record_path = _paths(args)
    source = _plugin_source()
    if not args.dry_run and not source.is_dir():
        print(f"Blocked: generated Cursor plugin does not exist: {source}", file=sys.stderr)
        return 2
    if destination.exists() or destination.is_symlink():
        if not record_path.is_file():
            print(f"Blocked: refusing to overwrite unmanaged Cursor plugin: {destination}", file=sys.stderr)
            return 2
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("plugin_hash") != _tree_hash(destination):
                raise ValueError("managed Cursor plugin changed after installation")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"Blocked: {error}", file=sys.stderr)
            return 2
    print(f"Install {source} -> {destination}")
    if args.dry_run:
        return 0
    local_root.mkdir(parents=True, exist_ok=True)
    if destination.exists() or destination.is_symlink():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)
    record = {
        "schema_version": 1,
        "plugin_name": PLUGIN_NAME,
        "plugin_hash": _tree_hash(destination),
        "destination": str(destination),
    }
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Installed Cursor plugin in {destination}")
    print("Restart Cursor or run Developer: Reload Window to load the plugin.")
    return 0


def uninstall(args: argparse.Namespace) -> int:
    _local_root, destination, record_path = _paths(args)
    if not record_path.is_file():
        print(f"No managed OQC Cursor plugin install found at {record_path}")
        return 0
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if not destination.is_dir() or _tree_hash(destination) != record["plugin_hash"]:
            raise ValueError("managed Cursor plugin changed after installation")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Blocked: {error}", file=sys.stderr)
        return 2
    print(f"Remove {destination}")
    if args.dry_run:
        return 0
    shutil.rmtree(destination)
    record_path.unlink()
    print("Uninstalled managed OQC Cursor plugin.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("user",), default="user", help="Cursor local plugins are installed per user")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--cursor-home", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(uninstall(args) if args.uninstall else install(args))


if __name__ == "__main__":
    raise SystemExit(main())
