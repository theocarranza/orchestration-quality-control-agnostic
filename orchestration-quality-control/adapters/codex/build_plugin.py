#!/usr/bin/env python3
"""Build a reproducible Codex marketplace from the canonical OQC package."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import zipfile
from pathlib import Path

PLUGIN_NAME = "orchestration-quality-control"
MARKETPLACE_NAME = "orchestration-qc-local"
VERSION = "1.1.0"
FIXED_ZIP_TIME = (2026, 7, 17, 0, 0, 0)


def _adapter_root() -> Path:
    return Path(__file__).resolve().parent


def _package_root() -> Path:
    return _adapter_root().parents[1]


def _repo_root() -> Path:
    return _package_root().parent


def _ignore(_directory: str, names: list[str]) -> set[str]:
    ignored = {name for name in names if name == "__pycache__" or name.endswith(".pyc")}
    return ignored


def _inject_overlay(skill_path: Path, overlay_path: Path) -> None:
    contents = skill_path.read_text(encoding="utf-8")
    if not contents.startswith("---\n"):
        raise ValueError("canonical SKILL.md does not start with YAML frontmatter")
    end = contents.find("\n---", 4)
    if end == -1:
        raise ValueError("canonical SKILL.md frontmatter is not closed")
    split_at = end + len("\n---")
    overlay = overlay_path.read_text(encoding="utf-8").strip()
    skill_path.write_text(contents[:split_at] + "\n\n" + overlay + "\n" + contents[split_at:].lstrip("\n"), encoding="utf-8")


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _manifest(root: Path) -> dict[str, str]:
    entries = {}
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        if relative == "BUILD-MANIFEST.json":
            continue
        entries[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return entries


def build(output: Path) -> Path:
    output = output.resolve()
    if output.exists():
        shutil.rmtree(output)
    plugin_root = output / "plugins" / PLUGIN_NAME
    skill_root = plugin_root / "skills" / PLUGIN_NAME
    shutil.copytree(_package_root(), skill_root, ignore=_ignore)
    _inject_overlay(skill_root / "SKILL.md", _adapter_root() / "skill-overlay.md")

    manifest = json.loads((_adapter_root() / "plugin.template.json").read_text(encoding="utf-8"))
    if manifest.get("name") != PLUGIN_NAME or manifest.get("version") != VERSION:
        raise ValueError("plugin template name/version does not match build constants")
    _write_json(plugin_root / ".codex-plugin" / "plugin.json", manifest)
    shutil.copytree(_adapter_root() / "hooks", plugin_root / "hooks", ignore=_ignore)

    marketplace = {
        "name": MARKETPLACE_NAME,
        "interface": {"displayName": "Orchestration QC Local"},
        "plugins": [
            {
                "name": PLUGIN_NAME,
                "source": {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Productivity",
            }
        ],
    }
    _write_json(output / ".agents" / "plugins" / "marketplace.json", marketplace)
    shutil.copytree(_adapter_root() / "agents", output / "agents")
    shutil.copy2(_adapter_root() / "install_codex_adapter.py", output / "install_codex_adapter.py")
    shutil.copy2(_adapter_root() / "install_codex.py", output / "install_codex.py")
    shutil.copy2(_adapter_root() / "README.md", output / "README.md")
    _write_json(output / "BUILD-MANIFEST.json", {"schema_version": 1, "files": _manifest(output)})
    return output


def write_zip(marketplace_root: Path, zip_path: Path) -> Path:
    zip_path = zip_path.resolve()
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=zip_path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
            for path in sorted(item for item in marketplace_root.rglob("*") if item.is_file()):
                relative = Path("codex-marketplace") / path.relative_to(marketplace_root)
                info = zipfile.ZipInfo(relative.as_posix(), FIXED_ZIP_TIME)
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                archive.writestr(info, path.read_bytes())
        temporary.replace(zip_path)
    finally:
        temporary.unlink(missing_ok=True)
    return zip_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(_repo_root() / "dist" / "codex-marketplace"))
    parser.add_argument("--zip", dest="zip_path", default=str(_repo_root() / "dist" / f"{PLUGIN_NAME}-codex-{VERSION}.zip"))
    parser.add_argument("--no-zip", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output = build(Path(args.output))
    print(f"Built Codex marketplace: {output}")
    if not args.no_zip:
        print(f"Built Codex release: {write_zip(output, Path(args.zip_path))}")


if __name__ == "__main__":
    main()
