"""Scheduling and routing functions: next_tasks and validate_pair.

This module provides the router slice of the deterministic kernel:
- next_tasks(dag, state) returns a tuple of task_ids that are ready to run
- validate_pair(sender, recipient) enforces legal envelope sender/recipient pairs
"""

from qc_lib import Blocked
from run_state import status_of


def next_tasks(dag, state):
    """Return a deterministically sorted tuple of task_ids that are runnable now.

    A task is runnable if its status is 'pending' and all of its
    dependencies have status 'passed'. A pure function: reads dag and state
    without mutation.
    """
    runnable = []

    for node in dag.tasks:
        if status_of(state, node.task_id) != "pending":
            continue

        # Check if all dependencies have passed
        all_deps_passed = all(
            status_of(state, dep) == "passed"
            for dep in node.depends_on
        )

        if all_deps_passed:
            runnable.append(node.task_id)

    return tuple(sorted(runnable))


def validate_pair(sender, recipient):
    """Enforce legal sender/recipient pairs per ADR 0014 decision 2.

    Legal pairs:
    - root <-> orchestrator (bidirectional)
    - orchestrator <-> agent:* (bidirectional)

    Illegal pairs each have a distinct reason:
    - root -> agent:* (root must not talk to workers directly)
    - agent:* -> root (workers must talk through orchestrator)
    - agent:* -> agent:* (worker-to-worker violates isolation)
    - self-pairs (root->root, orchestrator->orchestrator, agent->agent)
    """

    def is_worker(name):
        return name.startswith("agent:")

    # Check for self-pairs first
    if sender == recipient:
        raise Blocked(
            stage="router",
            reason_code="malformed_checkpoint",
            detail=f"self-pair not allowed: {sender} -> {recipient}",
            recovery_action="ensure sender and recipient are different",
        )

    # Legal: root <-> orchestrator
    if (sender == "root" and recipient == "orchestrator") or \
       (sender == "orchestrator" and recipient == "root"):
        return

    # Legal: orchestrator <-> worker
    if (sender == "orchestrator" and is_worker(recipient)) or \
       (is_worker(sender) and recipient == "orchestrator"):
        return

    # Illegal: root -> worker
    if sender == "root" and is_worker(recipient):
        raise Blocked(
            stage="router",
            reason_code="malformed_checkpoint",
            detail=f"root must not communicate directly with workers; route through orchestrator: {sender} -> {recipient}",
            recovery_action="route all root-to-worker communication through the orchestrator",
        )

    # Illegal: worker -> root
    if is_worker(sender) and recipient == "root":
        raise Blocked(
            stage="router",
            reason_code="malformed_checkpoint",
            detail=f"workers must not communicate directly with root; route through orchestrator: {sender} -> {recipient}",
            recovery_action="route all worker-to-root communication through the orchestrator",
        )

    # Illegal: worker -> worker
    if is_worker(sender) and is_worker(recipient):
        raise Blocked(
            stage="router",
            reason_code="malformed_checkpoint",
            detail=f"worker-to-worker communication violates isolation: {sender} -> {recipient}",
            recovery_action="route all inter-worker communication through the orchestrator",
        )

    # Unrecognized sender or recipient (not root, not orchestrator, not agent:*)
    raise Blocked(
        stage="router",
        reason_code="malformed_checkpoint",
        detail=f"unrecognized sender or recipient: {sender} -> {recipient}. only root, orchestrator, and agent:* identities are recognized",
        recovery_action="use only recognized identities: root, orchestrator, or agent:*",
    )
