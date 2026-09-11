#!/usr/bin/env python3
"""Build and install the complete OQC Antigravity (AGY) plugin for local use."""

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
RECORD_NAME = "oqc-agy-adapter-install.json"


def _here() -> Path:
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    return _here().parents[2]


def _generated_distribution() -> bool:
    return (_here() / "plugins" / PLUGIN_NAME).is_dir()


def _marketplace_root() -> Path:
    if _generated_distribution():
        return _here()
    return _repo_root() / "dist" / "agy-marketplace"


def _plugin_source() -> Path:
    return _marketplace_root() / "plugins" / PLUGIN_NAME


def _build_script() -> Path:
    return _here() / "build_plugin.py"


def _default_agy_home() -> Path:
    configured = os.environ.get("AGY_HOME")
    if configured:
        return Path(configured).expanduser().resolve()
    cli_home = Path.home() / ".gemini" / "antigravity-cli"
    if cli_home.is_dir():
        return cli_home
    config_home = Path.home() / ".gemini" / "config"
    if config_home.is_dir():
        return config_home
    return cli_home


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    if getattr(args, "scope", "user") == "workspace":
        workspace_root = Path(getattr(args, "workspace", None) or ".").expanduser().resolve()
        target_root = workspace_root / ".agents" / "plugins"
    else:
        agy_home = Path(getattr(args, "agy_home", None) or _default_agy_home()).expanduser().resolve()
        target_root = agy_home / "plugins"
    return target_root, target_root / PLUGIN_NAME, target_root / RECORD_NAME


def _managed_tree_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if "/__pycache__/" in relative or relative.endswith(".pyc"):
            continue
        paths.append(path)
    return sorted(paths)


def _tree_hash(root: Path) -> str:
    digest = hashlib.sha256()
    for path in _managed_tree_paths(root):
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
    target_root, destination, record_path = _paths(args)
    source = _plugin_source()
    if not args.dry_run and not source.is_dir():
        print(f"Blocked: generated AGY plugin does not exist: {source}", file=sys.stderr)
        return 2
    if destination.exists() or destination.is_symlink():
        if not record_path.is_file():
            print(f"Blocked: refusing to overwrite unmanaged AGY plugin: {destination}", file=sys.stderr)
            return 2
        try:
            record = json.loads(record_path.read_text(encoding="utf-8"))
            if record.get("plugin_hash") != _tree_hash(destination):
                raise ValueError("managed AGY plugin changed after installation")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            print(f"Blocked: {error}", file=sys.stderr)
            return 2
    print(f"Install {source} -> {destination}")
    if args.dry_run:
        return 0
    target_root.mkdir(parents=True, exist_ok=True)
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
    print(f"Installed AGY plugin in {destination}")
    print("Restart your AGY session or reload customizations to activate.")
    return 0


def uninstall(args: argparse.Namespace) -> int:
    _target_root, destination, record_path = _paths(args)
    if not record_path.is_file():
        print(f"No managed OQC AGY plugin install found at {record_path}")
        return 0
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if not destination.is_dir() or _tree_hash(destination) != record["plugin_hash"]:
            raise ValueError("managed AGY plugin changed after installation")
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Blocked: {error}", file=sys.stderr)
        return 2
    print(f"Remove {destination}")
    if args.dry_run:
        return 0
    shutil.rmtree(destination)
    record_path.unlink()
    print("Uninstalled managed OQC AGY plugin.")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("user", "workspace"), default="user", help="Install per-user (global) or per-workspace")
    parser.add_argument("--workspace", help="Workspace root path when scope=workspace")
    parser.add_argument("--agy-home", help="Custom AGY home path when scope=user")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(uninstall(args) if args.uninstall else install(args))


if __name__ == "__main__":
    raise SystemExit(main())
