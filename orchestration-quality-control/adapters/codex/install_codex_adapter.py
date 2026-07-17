#!/usr/bin/env python3
"""Install or uninstall the OQC custom agents and required Codex depth."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

AGENT_FILENAMES = (
    "oqc_codex_orchestrator.toml",
    "oqc_codex_validator.toml",
    "oqc_codex_remediator.toml",
)
REQUIRED_DEPTH = 2
RECORD_NAME = "oqc-codex-adapter-install.json"
MANUAL_SNIPPET = "[agents]\nmax_depth = 2"


@dataclass(frozen=True)
class ConfigEdit:
    action: str
    before: str
    after: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_agents() -> Path:
    return Path(__file__).resolve().parent / "agents"


def _paths(args: argparse.Namespace) -> tuple[Path, Path, Path]:
    if args.scope == "user":
        codex_home = Path(
            args.codex_home or os.environ.get("CODEX_HOME") or Path.home() / ".codex"
        ).expanduser().resolve()
        base = codex_home
    else:
        base = Path(args.project or Path.cwd()).expanduser().resolve() / ".codex"
    return base / "agents", base / "config.toml", base / RECORD_NAME


def _section_bounds(lines: list[str], section: str) -> tuple[int, int] | None:
    header = f"[{section}]"
    starts = [index for index, line in enumerate(lines) if line.strip() == header]
    if len(starts) > 1:
        raise ValueError(f"config contains more than one {header} section")
    if not starts:
        return None
    start = starts[0]
    end = len(lines)
    for index in range(start + 1, len(lines)):
        stripped = lines[index].strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            end = index
            break
    return start, end


def plan_config_edit(contents: str) -> ConfigEdit:
    lines = contents.splitlines(keepends=True)
    bounds = _section_bounds(lines, "agents")
    if bounds is None:
        separator = "" if not contents or contents.endswith("\n\n") else ("\n" if contents.endswith("\n") else "\n\n")
        block = f"{separator}[agents]\nmax_depth = {REQUIRED_DEPTH}\n"
        return ConfigEdit("append", contents, contents + block)

    start, end = bounds
    matches = []
    pattern = re.compile(r"^(\s*max_depth\s*=\s*)(\d+)(\s*(?:#.*)?(?:\r?\n)?)$")
    for index in range(start + 1, end):
        match = pattern.match(lines[index])
        if match:
            matches.append((index, match))
        elif re.match(r"^\s*max_depth\s*=", lines[index]):
            raise ValueError(f"cannot safely parse max_depth; set it manually:\n{MANUAL_SNIPPET}")
    if len(matches) > 1:
        raise ValueError("config contains more than one agents.max_depth value")
    if not matches:
        insertion = end
        lines.insert(insertion, f"max_depth = {REQUIRED_DEPTH}\n")
        return ConfigEdit("insert", contents, "".join(lines))

    index, match = matches[0]
    if int(match.group(2)) >= REQUIRED_DEPTH:
        return ConfigEdit("none", contents, contents)
    lines[index] = f"{match.group(1)}{REQUIRED_DEPTH}{match.group(3)}"
    return ConfigEdit("replace", contents, "".join(lines))


def _load_sources(source_dir: Path) -> dict[str, bytes]:
    sources = {}
    for filename in AGENT_FILENAMES:
        path = source_dir / filename
        if not path.is_file():
            raise ValueError(f"missing adapter agent definition: {path}")
        sources[filename] = path.read_bytes()
    return sources


def _preflight_install(
    agents_dir: Path, config_path: Path, record_path: Path, sources: dict[str, bytes]
) -> tuple[ConfigEdit, dict]:
    if record_path.exists():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        expected = record.get("agent_hashes", {})
        if expected == {name: _sha256(data) for name, data in sources.items()} and all(
            (agents_dir / name).is_file()
            and _sha256((agents_dir / name).read_bytes()) == digest
            for name, digest in expected.items()
        ):
            contents = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
            edit = plan_config_edit(contents)
            return edit, record
        raise ValueError(f"an incompatible managed install record already exists: {record_path}")

    for filename, data in sources.items():
        destination = agents_dir / filename
        if destination.exists() and destination.read_bytes() != data:
            raise ValueError(f"refusing to overwrite unmanaged custom agent: {destination}")
    config_before = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    edit = plan_config_edit(config_before)
    record = {
        "schema_version": 1,
        "agent_hashes": {name: _sha256(data) for name, data in sources.items()},
        "config_existed": config_path.exists(),
        "config_edit": asdict(edit),
    }
    return edit, record


def install(args: argparse.Namespace) -> int:
    agents_dir, config_path, record_path = _paths(args)
    try:
        sources = _load_sources(Path(args.source_agents).resolve() if args.source_agents else _source_agents())
        edit, record = _preflight_install(agents_dir, config_path, record_path, sources)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Blocked: {error}", file=sys.stderr)
        print(f"Manual configuration if needed:\n{MANUAL_SNIPPET}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({"action": "install", "agents_dir": str(agents_dir), "config_action": edit.action}, indent=2))
        return 0

    agents_dir.mkdir(parents=True, exist_ok=True)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    for filename, data in sources.items():
        (agents_dir / filename).write_bytes(data)
    if edit.after != edit.before or not config_path.exists():
        config_path.write_text(edit.after, encoding="utf-8")
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Installed OQC Codex agents in {agents_dir}")
    print(f"Verified agents.max_depth >= {REQUIRED_DEPTH} in {config_path}")
    return 0


def _revert_config(contents: str, edit: ConfigEdit, config_existed: bool) -> tuple[str, bool]:
    if edit.action == "none":
        return contents, False
    if contents != edit.after:
        raise ValueError("config changed after installation; refusing to overwrite it during uninstall")
    return edit.before, not config_existed and edit.before == ""


def uninstall(args: argparse.Namespace) -> int:
    agents_dir, config_path, record_path = _paths(args)
    if not record_path.is_file():
        print(f"No managed OQC Codex adapter install found at {record_path}")
        return 0
    try:
        record = json.loads(record_path.read_text(encoding="utf-8"))
        for filename, digest in record["agent_hashes"].items():
            path = agents_dir / filename
            if not path.is_file() or _sha256(path.read_bytes()) != digest:
                raise ValueError(f"managed agent changed after installation: {path}")
        contents = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
        edit = ConfigEdit(**record["config_edit"])
        reverted, remove_config = _revert_config(contents, edit, bool(record["config_existed"]))
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"Blocked: {error}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(json.dumps({"action": "uninstall", "agents_dir": str(agents_dir)}, indent=2))
        return 0
    for filename in record["agent_hashes"]:
        (agents_dir / filename).unlink()
    if remove_config:
        config_path.unlink(missing_ok=True)
    elif edit.action != "none":
        config_path.write_text(reverted, encoding="utf-8")
    record_path.unlink()
    print(f"Uninstalled managed OQC Codex agents from {agents_dir}")
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scope", choices=("user", "project"), default="user")
    parser.add_argument("--project", help="Project root for --scope project (defaults to cwd)")
    parser.add_argument("--codex-home", help=argparse.SUPPRESS)
    parser.add_argument("--source-agents", help=argparse.SUPPRESS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--uninstall", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    raise SystemExit(uninstall(args) if args.uninstall else install(args))


if __name__ == "__main__":
    main()
