#!/usr/bin/env python3
"""Build a bounded workspace brief for greenfield orchestration authoring."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import qc_lib
from qc_lib import Blocked

STAGE = "discover_workspace"
MAX_SCAN = 500
EXCLUDED_DIRS = {
    ".git", ".orchestration-qc", "__pycache__", "build", "dist",
    "node_modules", "vendor",
}
MANIFEST_LANGUAGES = {
    "package.json": "javascript",
    "pubspec.yaml": "dart",
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "go.mod": "go",
    "Cargo.toml": "rust",
    "Gemfile": "ruby",
    "composer.json": "php",
}
LOCKFILES = {
    "package-lock.json": "npm",
    "yarn.lock": "yarn",
    "pnpm-lock.yaml": "pnpm",
    "poetry.lock": "poetry",
    "uv.lock": "uv",
    "pubspec.lock": "pub",
    "Cargo.lock": "cargo",
    "go.sum": "go",
    "Gemfile.lock": "bundler",
    "composer.lock": "composer",
}
TEST_DIR_NAMES = {"test", "tests", "e2e", "integration_test"}
MECHANISM_DIRS = (".claude/agents", ".cursor/agents", ".codex/agents")


def _blocked(reason_code: str, detail: str, recovery: str) -> Blocked:
    return Blocked(stage=STAGE, reason_code=reason_code, detail=detail, recovery_action=recovery)


def _is_orchestration(path: Path) -> bool:
    name = path.name.lower()
    return (
        name.startswith("workflows-") and name.endswith(".md")
        or name.startswith("rules-") and name.endswith(".md")
        or "orchestrator" in name
    )


def _scan(root: Path) -> tuple[list[str], list[str]]:
    orchestration: list[str] = []
    pipeline: list[str] = []
    scanned = 0
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIRS]
        current_path = Path(current)
        for filename in filenames:
            scanned += 1
            if scanned > MAX_SCAN:
                return sorted(orchestration), sorted(pipeline)
            path = current_path / filename
            relative = path.relative_to(root).as_posix()
            lowered = filename.lower()
            if _is_orchestration(path):
                orchestration.append(relative)
            if lowered.endswith(".pipeline.yaml") or lowered.endswith(".pipeline.yml"):
                pipeline.append(relative)
    return sorted(orchestration), sorted(pipeline)


def discover(workspace: Path) -> dict:
    workspace = workspace.expanduser().resolve()
    if not workspace.is_dir():
        raise _blocked(
            "missing_target",
            f"workspace is not a readable directory: {workspace}",
            "pass an existing workspace root",
        )
    layout = sorted(
        path.name
        for path in workspace.iterdir()
        if path.is_dir() and path.name not in EXCLUDED_DIRS and not path.name.startswith(".")
    )
    languages = sorted({
        language
        for filename, language in MANIFEST_LANGUAGES.items()
        if (workspace / filename).is_file()
    })
    package_managers = sorted({
        manager
        for filename, manager in LOCKFILES.items()
        if (workspace / filename).is_file()
    })
    manifests = sorted(
        filename
        for filename in (*MANIFEST_LANGUAGES, *LOCKFILES)
        if (workspace / filename).is_file()
    )
    test_trees = [name for name in layout if name in TEST_DIR_NAMES or name.endswith("_test")]
    ci = [".github/workflows"] if (workspace / ".github" / "workflows").is_dir() else []
    mechanism = [path for path in MECHANISM_DIRS if (workspace / path).is_dir()]
    orchestration, pipeline = _scan(workspace)
    hints = []
    if any("pt-br" in part.lower() or "pt_br" in part.lower() for part in layout):
        hints.append("pt-br")
    return {
        "schema_version": 1,
        "languages": languages,
        "package_managers": package_managers,
        "layout": layout,
        "test_trees": test_trees,
        "ci": ci,
        "existing_orchestration": orchestration,
        "existing_mechanism": mechanism,
        "doc_language_hints": hints,
        "profile_hints": ["example-pipeline"] if pipeline else [],
        "readme_present": (workspace / "README.md").is_file(),
        "manifests": manifests,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True)
    args = parser.parse_args()
    qc_lib.run_main(STAGE, lambda: discover(Path(args.workspace)))


if __name__ == "__main__":
    main()
