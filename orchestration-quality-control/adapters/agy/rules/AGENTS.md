# Orchestration Quality Control Rules for Antigravity (AGY)

When the `orchestration-quality-control` plugin is active:

1. **Topology Isolation**:
   - The root AGY session interacts with the user (asking the upfront interview).
   - Only `oqc_agy_orchestrator` coordinates validation and remediation.
   - `oqc_agy_validator` is strictly read-only and never edits files.
   - `oqc_agy_remediator` applies only authorized before/after changes.

2. **Durable State Protection**:
   - Never manually tamper with files inside `.orchestration-qc/state/`.
   - Checkpoints are managed exclusively by deterministic scripts (`checkpoint_state.py`, `upgrade_state.py`, `author_state.py`).

3. **Gated Target Modifications**:
   - When a checkpoint is `pending_approval`, direct edits or commands altering target files are blocked by the `oqc-guard` lifecycle hook until an authorization record is generated.
