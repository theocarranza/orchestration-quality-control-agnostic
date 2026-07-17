#!/usr/bin/env python3
"""Install or uninstall the complete OQC Codex adapter."""

from __future__ import annotations

import argparse
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_REF = "orchestration-quality-control@orchestration-qc-local"


def _here() -> Path:
    return Path(__file__).resolve().parent


def _repo_root() -> Path:
    return _here().parents[2]


def _is_generated_distribution() -> bool:
    return (_here() / "plugins" / "orchestration-quality-control").is_dir()


def _marketplace_root() -> Path:
    if _is_generated_distribution():
        return _here()
    return _repo_root() / "dist" / "codex-marketplace"


def _source_bootstrap() -> Path:
    return _here() / "install_codex_adapter.py"


def _bootstrap_path() -> Path:
    if _is_generated_distribution():
        return _here() / "install_codex_adapter.py"
    return _marketplace_root() / "install_codex_adapter.py"


def _build_command() -> list[str]:
    return [sys.executable, str(_here() / "build_plugin.py")]


def _bootstrap_command(
    args: argparse.Namespace,
    *,
    uninstall: bool = False,
    bootstrap: Path | None = None,
) -> list[str]:
    command = [sys.executable, str(bootstrap or _bootstrap_path()), "--scope", args.scope]
    if args.project:
        command.extend(("--project", args.project))
    if args.codex_home:
        command.extend(("--codex-home", args.codex_home))
    if args.dry_run:
        command.append("--dry-run")
    if uninstall:
        command.append("--uninstall")
    return command


def _print_command(command: list[str]) -> None:
    print(f"$ {shlex.join(command)}")


def _run(command: list[str], *, dry_run: bool) -> int:
    _print_command(command)
    if dry_run:
        return 0
    try:
        completed = subprocess.run(command, check=False)
    except FileNotFoundError as error:
        print(f"Blocked: required command is unavailable: {error.filename}", file=sys.stderr)
        return 127
    return completed.returncode


def install(args: argparse.Namespace) -> int:
    if not _is_generated_distribution():
        result = _run(_build_command(), dry_run=args.dry_run)
        if result:
            return result

    marketplace = _marketplace_root()
    if not args.dry_run and not marketplace.is_dir():
        print(f"Blocked: generated marketplace does not exist: {marketplace}", file=sys.stderr)
        return 2
    if not args.dry_run and shutil.which("codex") is None:
        print("Blocked: the 'codex' command is not available on PATH", file=sys.stderr)
        return 127

    result = _run(
        ["codex", "plugin", "marketplace", "add", str(marketplace)],
        dry_run=args.dry_run,
    )
    if result:
        return result
    result = _run(["codex", "plugin", "add", PLUGIN_REF], dry_run=args.dry_run)
    if result:
        return result
    return _run(_bootstrap_command(args), dry_run=args.dry_run)


def uninstall(args: argparse.Namespace) -> int:
    bootstrap = _source_bootstrap() if not _is_generated_distribution() else _bootstrap_path()
    if not args.dry_run and not bootstrap.is_file():
        print(f"Blocked: adapter bootstrap does not exist: {bootstrap}", file=sys.stderr)
        return 2
    result = _run(
        _bootstrap_command(args, uninstall=True, bootstrap=bootstrap),
        dry_run=args.dry_run,
    )
    if result:
        return result
    if not args.dry_run and shutil.which("codex") is None:
        print("Blocked: the 'codex' command is not available on PATH", file=sys.stderr)
        return 127
    return _run(["codex", "plugin", "remove", PLUGIN_REF], dry_run=args.dry_run)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--project", help="Project root for --scope project (defaults to cwd)")
    parser.add_argument("--dry-run", action="store_true", help="Print the complete plan without changing state")
    parser.add_argument("--uninstall", action="store_true", help="Remove the managed adapter and plugin")
    parser.add_argument("--codex-home", help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.scope == "user" and args.project:
        raise SystemExit("--project is only valid with --scope project")
    raise SystemExit(uninstall(args) if args.uninstall else install(args))


if __name__ == "__main__":
    main()
