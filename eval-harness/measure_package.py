#!/usr/bin/env python3
"""Package size metrics for budget tracking and capacity planning.

Measures six metrics (files, markdown lines, skill documentation lines, agent
adapters, scripts, and distinct operations) from a package tree to track
growth and validate budget allocations. Output is a markdown table suitable
for embedding in documentation or comparing across versions.
"""
import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PackageMetrics:
    files: int
    markdown_lines: int
    skill_lines: int
    agents: int
    scripts: int
    operations: int


def repo_root(script_path: Path) -> Path:
    return script_path.resolve().parent.parent


def is_path_excluded(p: Path) -> bool:
    parts = p.parts
    return "__pycache__" in parts or "tests" in parts


def count_files(package_root: Path) -> int:
    return sum(1 for p in package_root.rglob("*") if p.is_file() and not is_path_excluded(p))


def count_markdown_lines(package_root: Path) -> int:
    def is_countable(p: Path) -> bool:
        return p.suffix == ".md" and p.name != "CHANGELOG.md"

    total = 0
    for p in package_root.rglob("*.md"):
        if not is_path_excluded(p) and is_countable(p):
            total += len(p.read_text(encoding="utf-8", errors="replace").splitlines())
    return total


def count_skill_lines(package_root: Path) -> int:
    skill_file = package_root / "SKILL.md"
    if not skill_file.exists():
        return 0
    return len(skill_file.read_text(encoding="utf-8", errors="replace").splitlines())


def count_agents(package_root: Path) -> int:
    return sum(
        1 for p in package_root.glob("adapters/*/agents/*") if p.is_file()
    )


def count_scripts(package_root: Path) -> int:
    scripts_dir = package_root / "scripts"
    if not scripts_dir.exists():
        return 0
    return sum(1 for p in scripts_dir.glob("*.py") if p.is_file())


def extract_operations_from_schema(schema_path: Path) -> set[str]:
    try:
        data = json.loads(schema_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()

    def walk_for_operations(obj: object) -> set[str]:
        found = set()
        if isinstance(obj, dict):
            if "operation" in obj:
                op_spec = obj["operation"]
                if isinstance(op_spec, dict):
                    if "const" in op_spec:
                        found.add(op_spec["const"])
                    if "enum" in op_spec and isinstance(op_spec["enum"], list):
                        found.update(str(v) for v in op_spec["enum"])
            for v in obj.values():
                found.update(walk_for_operations(v))
        elif isinstance(obj, list):
            for item in obj:
                found.update(walk_for_operations(item))
        return found

    return walk_for_operations(data)


def count_operations(package_root: Path) -> int:
    all_ops = set()
    for schema_file in package_root.rglob("*input*.schema.json"):
        all_ops.update(extract_operations_from_schema(schema_file))
    return len(all_ops)


def measure(package_root: Path) -> PackageMetrics:
    return PackageMetrics(
        files=count_files(package_root),
        markdown_lines=count_markdown_lines(package_root),
        skill_lines=count_skill_lines(package_root),
        agents=count_agents(package_root),
        scripts=count_scripts(package_root),
        operations=count_operations(package_root),
    )


def render_table(metrics: PackageMetrics) -> str:
    lines = [
        "| Metric | Value |",
        "|--------|-------|",
        f"| files | {metrics.files} |",
        f"| markdown_lines | {metrics.markdown_lines} |",
        f"| skill_lines | {metrics.skill_lines} |",
        f"| agents | {metrics.agents} |",
        f"| scripts | {metrics.scripts} |",
        f"| operations | {metrics.operations} |",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--package-root",
        type=Path,
        default="orchestration-quality-control",
        help="Package root relative to repository root (default: orchestration-quality-control)",
    )
    args = parser.parse_args(argv)

    repo = repo_root(Path(__file__))
    package_root = repo / args.package_root

    if not package_root.exists():
        sys.stderr.write(f"Error: package root not found at {package_root}\n")
        return 1

    metrics = measure(package_root)
    print(render_table(metrics))
    return 0


if __name__ == "__main__":
    sys.exit(main())
