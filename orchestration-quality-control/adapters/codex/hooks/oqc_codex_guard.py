#!/usr/bin/env python3
"""Codex PreToolUse guard for pending orchestration-QC target files."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path

from codex_authorization import change_digest

STATE_SUBDIR = Path(".orchestration-qc/state")
ALLOWED_SCRIPTS = {
    "checkpoint_state.py",
    "classify_targets.py",
    "codex_authorization.py",
    "derive_finding_id.py",
    "reconcile_decision.py",
    "render_diff.py",
}


def _decision(permission: str, reason: str) -> dict:
    return {
        "permissionDecision": permission,
        "reason": reason,
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": permission,
            "permissionDecisionReason": reason,
        },
    }


def _emit(permission: str, reason: str) -> int:
    print(json.dumps(_decision(permission, reason)))
    return 0


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
    resolved = path.resolve() if path.is_absolute() else (workspace / path).resolve()
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
    lines = patch.replace("\r\n", "\n").splitlines()
    before: list[str] = []
    after: list[str] = []
    in_hunk = False
    hunk_count = 0
    for line in lines:
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


def _authorization_matches(
    checkpoint_path: Path,
    checkpoint: dict,
    target: str,
    before: str,
    after: str,
) -> bool:
    auth_path = checkpoint_path.parent / f"codex-authorization-{checkpoint.get('run_id')}.json"
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
        (plugin_root / "skills/orchestration-quality-control/adapters/codex/hooks").resolve(),
    }
    return script.parent in roots


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return _emit("deny", "Malformed Codex hook input; denying the matched write-capable tool.")

    workspace = Path(payload.get("cwd") or ".").resolve()
    try:
        active = _active_checkpoint(workspace)
    except ValueError as error:
        return _emit("deny", str(error))
    if active is None:
        return _emit("allow", "No orchestration-QC checkpoint is pending.")

    checkpoint_path, checkpoint = active
    tool_name = str(payload.get("tool_name") or payload.get("tool") or payload.get("name") or "")
    tool_input = payload.get("tool_input") or payload.get("arguments") or payload.get("args") or {}
    plugin_root = Path(os.environ.get("PLUGIN_ROOT") or Path(__file__).resolve().parent.parent).resolve()

    if tool_name in {"Bash", "run_command", "exec_command"}:
        command = tool_input if isinstance(tool_input, str) else tool_input.get("command") or tool_input.get("cmd") or ""
        if command and _allowed_script_command(command, plugin_root):
            return _emit("allow", "Allowed deterministic orchestration-QC script invocation.")
        return _emit("deny", "Shell commands are blocked while orchestration-QC approval is pending, except the deterministic script allowlist.")

    patch = tool_input if isinstance(tool_input, str) else tool_input.get("patch") or tool_input.get("input") or ""
    if not patch:
        return _emit("deny", "Missing patch payload while orchestration-QC approval is pending.")
    try:
        raw_target, before, after = _extract_patch(patch)
        target = _normalize_target(raw_target, workspace)
    except (TypeError, ValueError) as error:
        return _emit("deny", f"Patch cannot be authorized: {error}")

    protected = {Path(path).as_posix() for path in checkpoint.get("targets", [])}
    if target not in protected:
        return _emit("allow", "Patch does not touch an active orchestration-QC target.")
    if _authorization_matches(checkpoint_path, checkpoint, target, before, after):
        return _emit("allow", "Patch exactly matches an approved orchestration-QC change.")
    return _emit("deny", f"Patch to protected target '{target}' is not an exact authorized change.")


if __name__ == "__main__":
    raise SystemExit(main())
