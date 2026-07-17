#!/usr/bin/env python3
"""Cursor hook guard for pending orchestration-QC target files."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path

from cursor_authorization import change_digest

STATE_SUBDIR = Path(".orchestration-qc/state")
ALLOWED_SCRIPTS = {
    "apply_upgrade.py",
    "checkpoint_state.py",
    "classify_targets.py",
    "cursor_authorization.py",
    "derive_finding_id.py",
    "discover_structure.py",
    "reconcile_decision.py",
    "render_diff.py",
    "render_upgrade.py",
    "upgrade_state.py",
}
WRITE_TOOLS = {"edit", "write", "applypatch", "delete", "move", "notebookedit"}


def _decision(permission: str, reason: str) -> dict:
    result = {"continue": permission == "allow", "permission": permission}
    if permission == "deny":
        result["user_message"] = reason
        result["agent_message"] = reason
    return result


def _emit(permission: str, reason: str) -> int:
    print(json.dumps(_decision(permission, reason), ensure_ascii=False))
    return 0


def _workspace(payload: dict) -> Path:
    roots = payload.get("workspace_roots")
    if isinstance(roots, list) and roots and isinstance(roots[0], str):
        return Path(roots[0]).expanduser().resolve()
    return Path(payload.get("cwd") or os.environ.get("CURSOR_PROJECT_DIR") or ".").resolve()


def _active_checkpoint(workspace: Path) -> tuple[Path, dict] | None:
    state_dir = workspace / STATE_SUBDIR
    active = []
    if state_dir.is_dir():
        for path in sorted(state_dir.glob("checkpoint-*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if payload.get("status") == "pending_approval":
                active.append((path, payload))
    if len(active) > 1:
        raise ValueError("multiple pending orchestration-QC checkpoints exist")
    return active[0] if active else None


def _normalize_target(raw_path: str, workspace: Path) -> str:
    path = Path(raw_path)
    resolved = path.expanduser().resolve() if path.is_absolute() else (workspace / path).resolve()
    return resolved.relative_to(workspace.resolve()).as_posix()


def _extract_patch(patch: str) -> tuple[str, str, str]:
    update_paths = re.findall(r"^\*\*\* Update File: (.+)$", patch, flags=re.MULTILINE)
    if (
        len(update_paths) != 1
        or "*** Add File:" in patch
        or "*** Delete File:" in patch
        or "*** Move to:" in patch
    ):
        raise ValueError("authorized patches require exactly one Update File block")
    before: list[str] = []
    after: list[str] = []
    in_hunk = False
    hunk_count = 0
    for line in patch.replace("\r\n", "\n").splitlines():
        if line.startswith("@@"):
            in_hunk = True
            hunk_count += 1
            continue
        if not in_hunk:
            continue
        if line.startswith("*** "):
            in_hunk = False
            continue
        if line.startswith("-"):
            before.append(line[1:])
        elif line.startswith("+"):
            after.append(line[1:])
        elif line.startswith(" "):
            raise ValueError("authorized patches may not contain unchanged hunk context")
    if hunk_count != 1:
        raise ValueError("authorized patches require exactly one hunk")
    return update_paths[0].strip(), "\n".join(before), "\n".join(after)


def _first(mapping: dict, keys: tuple[str, ...]) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def _extract_change(tool_input: object) -> tuple[str, str, str] | None:
    if isinstance(tool_input, str):
        if "*** Update File:" not in tool_input:
            return None
        return _extract_patch(tool_input)
    if not isinstance(tool_input, dict):
        return None
    patch = _first(tool_input, ("patch", "diff", "input"))
    if isinstance(patch, str) and "*** Update File:" in patch:
        return _extract_patch(patch)
    target = _first(tool_input, ("path", "file_path", "filePath", "target_file", "targetFile", "filename"))
    before = _first(tool_input, ("before", "old_string", "oldString", "old_text", "oldText"))
    after = _first(tool_input, ("after", "new_string", "newString", "new_text", "newText"))
    if isinstance(target, str) and isinstance(before, str) and isinstance(after, str):
        return target, before, after
    return None


def _authorization_matches(
    checkpoint_path: Path,
    checkpoint: dict,
    target: str,
    before: str,
    after: str,
) -> bool:
    auth_path = checkpoint_path.parent / f"cursor-authorization-{checkpoint.get('run_id')}.json"
    try:
        authorization = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    current_digest = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    if authorization.get("run_id") != checkpoint.get("run_id"):
        return False
    if authorization.get("checkpoint_sha256") != current_digest:
        return False
    digest = change_digest(target, before, after)
    return any(
        entry.get("target") == target and entry.get("change_sha256") == digest
        for entry in authorization.get("approved_changes", [])
    )


def _allowed_script_command(command: str, plugin_root: Path) -> bool:
    if any(token in command for token in ("&&", "||", ";", "|", ">", "<", "`", "$(")):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if len(tokens) < 2 or Path(tokens[0]).name not in {"python", "python3"}:
        return False
    script = Path(tokens[1])
    if not script.is_absolute():
        script = (Path.cwd() / script).resolve()
    else:
        script = script.resolve()
    if script.name not in ALLOWED_SCRIPTS:
        return False
    roots = {
        (plugin_root / "hooks").resolve(),
        (plugin_root / "skills/orchestration-quality-control/scripts").resolve(),
        (plugin_root / "skills/orchestration-quality-control/adapters/cursor/hooks").resolve(),
    }
    return script.parent in roots


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        return _emit("deny", "Malformed Cursor hook input; denying the matched operation.")
    workspace = _workspace(payload)
    try:
        active = _active_checkpoint(workspace)
    except ValueError as error:
        return _emit("deny", str(error))
    if active is None:
        return _emit("allow", "No orchestration-QC checkpoint is pending.")

    checkpoint_path, checkpoint = active
    event = str(payload.get("hook_event_name") or payload.get("event") or "")
    tool_name = str(payload.get("tool_name") or payload.get("tool") or "")
    tool_input = payload.get("tool_input") or payload.get("arguments") or payload.get("args") or {}
    plugin_root = Path(
        os.environ.get("CURSOR_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent
    ).resolve()

    is_shell = event == "beforeShellExecution" or tool_name.lower() in {"shell", "bash"}
    if is_shell:
        command = tool_input if isinstance(tool_input, str) else tool_input.get("command", "")
        if command and _allowed_script_command(command, plugin_root):
            return _emit("allow", "Allowed deterministic orchestration-QC script invocation.")
        return _emit("deny", "Shell commands are blocked while orchestration-QC approval is pending, except the deterministic script allowlist.")

    if event and event != "preToolUse":
        return _emit("allow", "This Cursor hook event does not modify a protected target.")
    if tool_name.lower() not in WRITE_TOOLS:
        return _emit("allow", "This Cursor tool is not a protected file-edit operation.")

    try:
        change = _extract_change(tool_input)
        if change is None:
            raise ValueError("missing target and exact before/after change")
        raw_target, before, after = change
        target = _normalize_target(raw_target, workspace)
    except (TypeError, ValueError) as error:
        return _emit("deny", f"File change cannot be authorized: {error}")

    protected = {Path(path).as_posix() for path in checkpoint.get("targets", [])}
    if target not in protected:
        return _emit("allow", "File change does not touch an active orchestration-QC target.")
    if _authorization_matches(checkpoint_path, checkpoint, target, before, after):
        return _emit("allow", "File change exactly matches an approved orchestration-QC change.")
    return _emit("deny", f"Change to protected target '{target}' is not an exact authorized change.")


if __name__ == "__main__":
    raise SystemExit(main())
