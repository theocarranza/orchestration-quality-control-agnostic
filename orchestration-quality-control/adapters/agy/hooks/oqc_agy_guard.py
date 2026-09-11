#!/usr/bin/env python3
"""Antigravity (AGY) hook guard for pending orchestration-QC target files."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path

# Ensure local hooks directory is on sys.path for agy_authorization
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from agy_authorization import change_digest

STATE_SUBDIR = Path(".orchestration-qc/state")
ALLOWED_SCRIPTS = {
    "agy_authorization.py",
    "apply_author.py",
    "apply_upgrade.py",
    "author_state.py",
    "checkpoint_state.py",
    "classify_targets.py",
    "derive_finding_id.py",
    "discover_structure.py",
    "discover_workspace.py",
    "plan_interview.py",
    "reconcile_decision.py",
    "render_diff.py",
    "render_upgrade.py",
    "upgrade_state.py",
}
WRITE_TOOLS = {
    "replace_file_content",
    "replace_file",
    "edit_file",
    "write_to_file",
    "write_file",
    "create_file",
    "save_file",
    "overwrite_file",
    "edit",
    "write",
    "str_replace",
    "replace",
    "applypatch",
    "delete",
    "move",
    "notebookedit",
}


def _decision(decision: str, reason: str) -> dict:
    is_allow = decision == "allow"
    return {
        "decision": decision,
        "reason": reason,
        "permission": decision,
        "continue": is_allow,
        "user_message": reason if not is_allow else "",
        "agent_message": reason if not is_allow else "",
    }


def _emit(decision: str, reason: str) -> int:
    print(json.dumps(_decision(decision, reason), ensure_ascii=False))
    return 0


def _workspace(payload: dict) -> Path:
    paths = payload.get("workspacePaths") or payload.get("workspace_roots")
    if isinstance(paths, list) and paths and isinstance(paths[0], str):
        return Path(paths[0]).expanduser().resolve()
    cwd = payload.get("cwd") or os.environ.get("AGY_PROJECT_DIR") or os.environ.get("WORKSPACE") or "."
    return Path(cwd).resolve()


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
    try:
        return resolved.relative_to(workspace.resolve()).as_posix()
    except ValueError:
        return resolved.as_posix()


def _extract_change(tool_name: str, tool_input: dict) -> tuple[str, str, str] | None:
    # 1. Antigravity replace_file_content tool
    if tool_name in {"replace_file_content", "replace_file", "edit_file"}:
        target = (
            tool_input.get("TargetFile")
            or tool_input.get("target_file")
            or tool_input.get("path")
            or tool_input.get("file")
        )
        before = (
            tool_input.get("TargetContent")
            or tool_input.get("target_content")
            or tool_input.get("old_string")
        )
        after = (
            tool_input.get("ReplacementContent")
            or tool_input.get("replacement_content")
            or tool_input.get("new_string")
        )
        if target and before is not None and after is not None:
            return str(target), str(before), str(after)

    # 2. Generic edit tool (Cursor/Codex style)
    if tool_name in {"edit", "str_replace", "replace"}:
        target = (
            tool_input.get("path")
            or tool_input.get("TargetFile")
            or tool_input.get("file")
            or tool_input.get("target_file")
        )
        before = (
            tool_input.get("old_string")
            or tool_input.get("TargetContent")
            or tool_input.get("target_content")
        )
        after = (
            tool_input.get("new_string")
            or tool_input.get("ReplacementContent")
            or tool_input.get("replacement_content")
        )
        if target and before is not None and after is not None:
            return str(target), str(before), str(after)

    # 3. Patch format
    patch = tool_input.get("patch") or tool_input.get("diff")
    if isinstance(patch, str) and patch:
        update_paths = re.findall(r"^\*\*\* Update File: (.+)$", patch, flags=re.MULTILINE)
        if len(update_paths) == 1:
            before_lines = []
            after_lines = []
            in_hunk = False
            for line in patch.replace("\r\n", "\n").splitlines():
                if line.startswith("@@"):
                    in_hunk = True
                    continue
                if not in_hunk:
                    continue
                if line.startswith("*** "):
                    in_hunk = False
                    continue
                if line.startswith("-"):
                    before_lines.append(line[1:])
                elif line.startswith("+"):
                    after_lines.append(line[1:])
            return update_paths[0].strip(), "\n".join(before_lines), "\n".join(after_lines)

    return None


def _authorization_matches(
    checkpoint_path: Path, checkpoint: dict, target: str, before: str, after: str
) -> bool:
    auth_path = checkpoint_path.parent / f"agy-authorization-{checkpoint.get('run_id')}.json"
    try:
        authorization = json.loads(auth_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    current_digest = hashlib.sha256(checkpoint_path.read_bytes()).hexdigest()
    if authorization.get("run_id") != checkpoint.get('run_id'):
        return False
    if authorization.get("checkpoint_sha256") != current_digest:
        return False
    digest = change_digest(target, before, after)
    return any(
        entry.get("target") == target and entry.get("change_sha256") == digest
        for entry in authorization.get("approved_changes", [])
    )


def _allowed_script_command(command: str, plugin_root: Path) -> bool:
    if any(token in command for token in ("&&", "||", ";", "|", ">", "<", "`", "$(", "\n", "\r")):
        return False
    try:
        tokens = shlex.split(command)
    except ValueError:
        return False
    if len(tokens) < 2 or Path(tokens[0]).name not in {"python", "python3"}:
        return False
    arg_idx = 1
    while arg_idx < len(tokens) and tokens[arg_idx].startswith("-"):
        arg_idx += 1
    if arg_idx >= len(tokens):
        return False
    script = Path(tokens[arg_idx])
    if not script.is_absolute():
        script = (Path.cwd() / script).resolve()
    else:
        script = script.resolve()
    if script.name not in ALLOWED_SCRIPTS:
        return False
    roots = {
        (plugin_root / "hooks").resolve(),
        (plugin_root / "scripts").resolve(),
        (plugin_root / "orchestration-quality-control/scripts").resolve(),
        (plugin_root / "skills/orchestration-quality-control/scripts").resolve(),
        (plugin_root / "adapters/agy/hooks").resolve(),
        (plugin_root / "skills/orchestration-quality-control/adapters/agy/hooks").resolve(),
        _HERE.resolve(),
    }
    return script.parent in roots


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read())
    except json.JSONDecodeError:
        return _emit("deny", "Malformed AGY hook input; denying the matched operation.")

    workspace = _workspace(payload)
    try:
        active = _active_checkpoint(workspace)
    except ValueError as error:
        return _emit("deny", str(error))

    if active is None:
        return _emit("allow", "No orchestration-QC checkpoint is pending.")

    checkpoint_path, checkpoint = active
    tool_call = payload.get("toolCall") or {}
    tool_name = (
        tool_call.get("name")
        or payload.get("tool_name")
        or payload.get("tool")
        or ""
    ).lower()
    tool_args = (
        tool_call.get("args")
        or payload.get("tool_input")
        or payload.get("arguments")
        or payload.get("args")
        or {}
    )

    plugin_root = Path(
        os.environ.get("AGY_PLUGIN_ROOT") or Path(__file__).resolve().parent.parent
    ).resolve()

    # 1. Shell / run_command tool
    is_shell = tool_name in {
        "run_command", "shell", "bash", "terminal", "command", "execute_command", "exec_command", "sh"
    }
    if is_shell:
        command = tool_args if isinstance(tool_args, str) else (
            tool_args.get("CommandLine") or tool_args.get("command") or tool_args.get("cmd") or ""
        )
        if command and _allowed_script_command(command, plugin_root):
            return _emit("allow", "Allowed deterministic orchestration-QC script invocation.")
        return _emit(
            "deny",
            "Shell commands are blocked while orchestration-QC approval is pending, except the deterministic script allowlist.",
        )

    # 2. Write tool (overwrite)
    if tool_name in {"write_to_file", "write", "write_file", "create_file", "save_file", "overwrite_file"}:
        raw_target = (
            tool_args.get("TargetFile")
            or tool_args.get("target_file")
            or tool_args.get("path")
            or tool_args.get("file")
            or ""
        )
        if not raw_target:
            return _emit("deny", "File write cannot be authorized: missing TargetFile.")
        target = _normalize_target(raw_target, workspace)
        protected = {Path(path).as_posix() for path in checkpoint.get("targets", [])}
        if target in protected:
            return _emit(
                "deny",
                f"Direct write to protected target '{target}' is blocked while orchestration-QC approval is pending.",
            )
        return _emit("allow", "File write does not touch an active orchestration-QC target.")

    # 3. Replace content / Edit tool
    if tool_name in {
        "replace_file_content", "replace_file", "edit_file", "edit", "str_replace", "replace", "applypatch"
    }:
        change = _extract_change(tool_name, tool_args)
        if change is None:
            return _emit("deny", "File change cannot be authorized: missing target and exact before/after change.")
        raw_target, before, after = change
        target = _normalize_target(raw_target, workspace)
        protected = {Path(path).as_posix() for path in checkpoint.get("targets", [])}
        if target not in protected:
            return _emit("allow", "File change does not touch an active orchestration-QC target.")
        if _authorization_matches(checkpoint_path, checkpoint, target, before, after):
            return _emit("allow", "File change exactly matches an approved orchestration-QC change.")
        return _emit("deny", f"Change to protected target '{target}' is not an exact authorized change.")

    # 4. Other tools (e.g. read-only, discovery)
    if tool_name not in WRITE_TOOLS:
        return _emit("allow", "This tool is not a protected file-edit operation.")

    return _emit("deny", f"Tool {tool_name} is blocked on protected targets while approval is pending.")


if __name__ == "__main__":
    raise SystemExit(main())
