#!/usr/bin/env python3
"""Metrics for one orchestration run: files read, state written, envelope sizes.

Measures how many packaged files each role read before its work, what the run
wrote under sandbox/.orchestration-qc/, and the sizes of its envelopes and
compiled prompts. Handles both 3.2.0 runs (no mailbox) and future 4.0.0 shape
(with mailbox and prompts). Output is a markdown table suitable for embedding
in documentation or aggregated across runs.
"""
import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunMetrics:
    mailbox_present: bool
    files_read_per_role: dict
    files_read_total: int
    state_files: int
    state_paths: tuple
    envelope_bytes: tuple
    max_envelope_bytes: int
    prompt_bytes: tuple
    max_prompt_bytes: int
    verify: str


def repo_root(script_path: Path) -> Path:
    return script_path.resolve().parent.parent


def mailbox_path(run_dir: Path) -> Path:
    return run_dir / "sandbox" / ".orchestration-qc" / "mail"


def has_mailbox(run_dir: Path) -> bool:
    mail_dir = mailbox_path(run_dir)
    if not mail_dir.exists():
        return False
    run_ids = list(mail_dir.glob("*"))
    return any(
        (run_id_dir / "events.jsonl").exists()
        for run_id_dir in run_ids
        if run_id_dir.is_dir()
    )


def read_files_per_role_from_mailbox(run_dir: Path) -> dict:
    mail_dir = mailbox_path(run_dir)
    role_counts = {}

    for run_id_dir in mail_dir.glob("*"):
        events_file = run_id_dir / "events.jsonl"
        if not events_file.exists():
            continue

        for line in events_file.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                envelope = json.loads(line)
                role = envelope.get("from", {}).get("role")
                inputs = envelope.get("inputs", {})
                paths = inputs.get("paths", [])

                if role is not None:
                    role_counts[role] = role_counts.get(role, 0) + len(paths)
            except json.JSONDecodeError:
                pass

    return role_counts


def strip_trailing_note(path_str: str) -> str:
    paren_pos = path_str.find(" (")
    return path_str[:paren_pos] if paren_pos != -1 else path_str


def is_packaged_file(path_str: str, package_root: Path) -> bool:
    normalized = strip_trailing_note(path_str)

    if normalized.startswith("orchestration-quality-control/"):
        normalized = normalized[len("orchestration-quality-control/"):]

    try:
        return (package_root / normalized).exists()
    except (OSError, ValueError):
        return False


def read_files_per_role_from_transcript(run_dir: Path, package_root: Path) -> dict:
    transcript_file = run_dir / "outputs" / "transcript.md"
    if not transcript_file.exists():
        return {"run": 0}

    content = transcript_file.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()

    start_idx = None
    for idx, line in enumerate(lines):
        if line == "## Files read":
            start_idx = idx
            break

    if start_idx is None:
        return {"run": 0}

    end_idx = len(lines)
    for idx in range(start_idx + 1, len(lines)):
        if lines[idx].startswith("## "):
            end_idx = idx
            break

    packaged_count = 0
    for idx in range(start_idx + 1, end_idx):
        line = lines[idx]
        if line.startswith("- "):
            path_str = line[2:].strip()
            if is_packaged_file(path_str, package_root):
                packaged_count += 1

    return {"run": packaged_count}


def read_files_per_role(run_dir: Path, package_root: Path) -> dict:
    return (
        read_files_per_role_from_mailbox(run_dir)
        if has_mailbox(run_dir)
        else read_files_per_role_from_transcript(run_dir, package_root)
    )


def total_files_read(files_per_role: dict) -> int:
    return sum(files_per_role.values())


def count_state_files(run_dir: Path) -> int:
    state_dir = run_dir / "sandbox" / ".orchestration-qc"
    if not state_dir.exists():
        return 0
    return sum(1 for p in state_dir.rglob("*") if p.is_file())


def state_paths_sorted(run_dir: Path) -> tuple:
    state_dir = run_dir / "sandbox" / ".orchestration-qc"
    if not state_dir.exists():
        return tuple()

    sandbox_dir = run_dir / "sandbox"
    paths = []
    for p in state_dir.rglob("*"):
        if p.is_file():
            rel_path = p.relative_to(sandbox_dir)
            paths.append(str(rel_path))

    return tuple(sorted(paths))


def envelope_sizes(run_dir: Path) -> tuple:
    mail_dir = mailbox_path(run_dir)
    if not mail_dir.exists():
        return tuple()

    sizes = []
    for run_id_dir in mail_dir.glob("*"):
        events_file = run_id_dir / "events.jsonl"
        if events_file.exists():
            for line in events_file.read_text(encoding="utf-8", errors="replace").splitlines():
                sizes.append(len(line.encode("utf-8")))

    return tuple(sizes)


def prompt_sizes(run_dir: Path) -> tuple:
    mail_dir = mailbox_path(run_dir)
    if not mail_dir.exists():
        return tuple()

    sizes = []
    for prompt_file in sorted(mail_dir.rglob("*.prompt.md")):
        sizes.append(len(prompt_file.read_bytes()))

    return tuple(sizes)


def verify_mailbox(run_dir: Path, package_root: Path) -> str:
    oqc_script = package_root / "scripts" / "oqc.py"
    if not oqc_script.exists():
        return "unavailable"

    if not has_mailbox(run_dir):
        return "unavailable"

    mail_dir = mailbox_path(run_dir)
    run_id_dirs = list(mail_dir.glob("*"))
    if not run_id_dirs:
        return "unavailable"

    mail_verify_dir = run_id_dirs[0]

    try:
        result = subprocess.run(
            ["python3", str(oqc_script), "mail", "verify", "--run-dir", str(mail_verify_dir)],
            capture_output=True,
            timeout=30,
        )
        return "pass" if result.returncode == 0 else "fail"
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return "fail"


def measure(run_dir: Path, package_root: Path) -> RunMetrics:
    files_by_role = read_files_per_role(run_dir, package_root)
    mailbox_present = has_mailbox(run_dir)
    envelope_sz = envelope_sizes(run_dir)
    prompt_sz = prompt_sizes(run_dir)

    return RunMetrics(
        mailbox_present=mailbox_present,
        files_read_per_role=files_by_role,
        files_read_total=total_files_read(files_by_role),
        state_files=count_state_files(run_dir),
        state_paths=state_paths_sorted(run_dir),
        envelope_bytes=envelope_sz,
        max_envelope_bytes=max(envelope_sz) if envelope_sz else 0,
        prompt_bytes=prompt_sz,
        max_prompt_bytes=max(prompt_sz) if prompt_sz else 0,
        verify=verify_mailbox(run_dir, package_root),
    )


def render_table(metrics: RunMetrics) -> str:
    lines = [
        "| Metric | Value |",
        "|--------|-------|",
        f"| mailbox_present | {metrics.mailbox_present} |",
        f"| files_read_per_role | {metrics.files_read_per_role} |",
        f"| files_read_total | {metrics.files_read_total} |",
        f"| state_files | {metrics.state_files} |",
        f"| state_paths | {metrics.state_paths} |",
        f"| envelope_bytes | {metrics.envelope_bytes} |",
        f"| max_envelope_bytes | {metrics.max_envelope_bytes} |",
        f"| prompt_bytes | {metrics.prompt_bytes} |",
        f"| max_prompt_bytes | {metrics.max_prompt_bytes} |",
        f"| verify | {metrics.verify} |",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Run directory to measure",
    )
    parser.add_argument(
        "--package-root",
        type=Path,
        default="orchestration-quality-control",
        help="Package root relative to repository root (default: orchestration-quality-control)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output JSON instead of markdown table",
    )
    args = parser.parse_args(argv)

    repo = repo_root(Path(__file__))
    package_root = repo / args.package_root
    run_dir = repo / args.run_dir if not args.run_dir.is_absolute() else args.run_dir

    if not run_dir.exists():
        sys.stderr.write(f"Error: run directory not found at {run_dir}\n")
        return 1

    metrics = measure(run_dir, package_root)

    if args.json:
        output = json.dumps({
            "mailbox_present": metrics.mailbox_present,
            "files_read_per_role": metrics.files_read_per_role,
            "files_read_total": metrics.files_read_total,
            "state_files": metrics.state_files,
            "state_paths": metrics.state_paths,
            "envelope_bytes": metrics.envelope_bytes,
            "max_envelope_bytes": metrics.max_envelope_bytes,
            "prompt_bytes": metrics.prompt_bytes,
            "max_prompt_bytes": metrics.max_prompt_bytes,
            "verify": metrics.verify,
        })
        print(output)
    else:
        print(render_table(metrics))

    return 0


if __name__ == "__main__":
    sys.exit(main())
