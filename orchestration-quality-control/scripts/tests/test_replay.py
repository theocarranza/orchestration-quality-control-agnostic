"""The Outcome 2 load-bearing evidence: a model-free replay of a two-task
dependent DAG through the fake adapter, the result gate and the bounded
retry/block decision.

Both fixtures below drive their DAG using nothing but
kernel_specs.TaskDag, router.next_tasks, fake_adapter.FakeAdapter,
gate.gate_result/retry_or_block, and mailbox.Mailbox -- the same pieces a
real orchestrator loop would use, just with a scripted adapter standing in
for a host. Every assertion is made against `run_state.reduce(mailbox
.read_all())`, never against a counter or flag this test module kept for
itself: the mailbox is the source of truth, per ADR 0014 decision 2 and
this task's brief.
"""

import unittest

from fake_adapter import FakeAdapter
from gate import FAILED, PASSED, RETRY, gate_result, retry_or_block
from kernel_specs import TaskDag
from mailbox import Mailbox
from router import next_tasks
from run_state import reduce, status_of

RUN_ID = "run-replay"
MAX_ATTEMPTS = 3

DAG = TaskDag.from_list([
    {"task_id": "task-a", "role": "worker", "depends_on": []},
    {"task_id": "task-b", "role": "worker", "depends_on": ["task-a"]},
])


def _latest_payload(mailbox, *, kind, task_id, attempt=None):
    matches = [
        envelope.payload
        for envelope in mailbox.read_all()
        if envelope.kind == kind
        and envelope.payload.get("task_id") == task_id
        and (attempt is None or envelope.payload.get("attempt") == attempt)
    ]
    if not matches:
        raise AssertionError(
            f"no {kind!r} envelope found for task_id={task_id!r} attempt={attempt!r}"
        )
    return matches[-1]


def _spawn_attempt(adapter, mailbox, *, task_id, attempt, critique):
    """Run one attempt of `task_id` through the fake adapter and return the
    gate's verdict on it. `critique` (possibly None) is exactly what this
    attempt's compiled brief carries -- the one place a prior failure's
    critique is threaded into the next request.
    """
    adapter.spawn(
        mailbox,
        run_id=RUN_ID,
        task_id=task_id,
        attempt=attempt,
        agent_id=task_id,
        brief={"task": task_id, "attempt": attempt, "critique": critique},
    )
    result_payload = _latest_payload(mailbox, kind="result", task_id=task_id, attempt=attempt)
    return gate_result(result_payload)


class FixtureACritiqueCarryingRetryTest(unittest.TestCase):
    """Fixture A: task-a fails once with a critique, the retry receives
    that critique, passes, task-b then runs, and the run reaches
    'completed'.
    """

    SCRIPT = {
        ("task-a", 1): {"outcome": "failed", "critique": "off-by-one in the boundary check"},
        ("task-a", 2): {"outcome": "passed"},
        ("task-b", 1): {"outcome": "passed"},
    }

    def _drive(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(self.SCRIPT)

        # Attempt 1 of task-a: nothing runnable yet but task-a itself.
        state = reduce(mailbox.read_all())
        self.assertEqual(next_tasks(DAG, state), ("task-a",))

        verdict_1 = _spawn_attempt(adapter, mailbox, task_id="task-a", attempt=1, critique=None)
        self.assertEqual(verdict_1.outcome, FAILED)
        self.assertTrue(verdict_1.critique)

        state = reduce(mailbox.read_all())
        decision = retry_or_block(state, "task-a", verdict_1.critique, MAX_ATTEMPTS - 1)
        self.assertEqual(decision.action, RETRY)
        self.assertEqual(decision.critique, verdict_1.critique)

        # Attempt 2 of task-a: must carry attempt 1's critique forward.
        verdict_2 = _spawn_attempt(
            adapter, mailbox, task_id="task-a", attempt=2, critique=decision.critique,
        )
        self.assertEqual(verdict_2.outcome, PASSED)

        # >>> The load-bearing assertion: the SECOND attempt's own request
        # envelope carries the critique from the FIRST failure in its
        # brief -- not merely "a second attempt happened".
        request_2 = _latest_payload(mailbox, kind="request", task_id="task-a", attempt=2)
        self.assertEqual(request_2["brief"]["critique"], verdict_1.critique)
        self.assertIn("off-by-one", request_2["brief"]["critique"])

        # task-a passed: task-b becomes runnable.
        state = reduce(mailbox.read_all())
        self.assertEqual(next_tasks(DAG, state), ("task-b",))

        verdict_b = _spawn_attempt(adapter, mailbox, task_id="task-b", attempt=1, critique=None)
        self.assertEqual(verdict_b.outcome, PASSED)

        state = reduce(mailbox.read_all())
        self.assertEqual(next_tasks(DAG, state), ())
        adapter.emit_status(mailbox, run_id=RUN_ID, phase="completed", context={})
        return mailbox

    def test_critique_reaches_the_second_attempt_and_the_run_completes(self):
        mailbox = self._drive()
        final_state = reduce(mailbox.read_all())
        self.assertEqual(final_state.phase, "completed")
        self.assertEqual(status_of(final_state, "task-a"), "passed")
        self.assertEqual(status_of(final_state, "task-b"), "passed")

    def test_run_is_model_free_and_deterministic_across_two_runs(self):
        # No network, no LLM call, no sleep, no clock read anywhere in
        # this path (see fake_adapter.FakeAdapter's synthetic clock) --
        # proven here by running the exact same fixture twice from
        # scratch and requiring byte-identical mailboxes and equal
        # derived state.
        mailbox_1 = self._drive()
        mailbox_2 = self._drive()
        self.assertEqual(mailbox_1.to_jsonl(), mailbox_2.to_jsonl())
        self.assertEqual(reduce(mailbox_1.read_all()), reduce(mailbox_2.read_all()))


class FixtureBExhaustedRetriesTest(unittest.TestCase):
    """Fixture B: task-a fails every attempt until the budget is
    exhausted. The run must reach 'blocked' or 'awaiting-user-input' --
    never 'completed', and never an infinite loop -- and task-b must
    never run.
    """

    SCRIPT = {
        ("task-a", 1): {"outcome": "failed", "critique": "attempt 1: wrong output shape"},
        ("task-a", 2): {"outcome": "failed", "critique": "attempt 2: still wrong"},
        ("task-a", 3): {"outcome": "failed", "critique": "attempt 3: still wrong"},
    }

    def _drive(self):
        mailbox = Mailbox()
        adapter = FakeAdapter(self.SCRIPT)
        critique = None

        # Bounded by construction (a plain `for` over MAX_ATTEMPTS, not a
        # `while True`): even a broken retry/budget decision cannot make
        # this loop run forever, so a defect here fails the test instead
        # of hanging the suite.
        for attempt in range(1, MAX_ATTEMPTS + 1):
            verdict = _spawn_attempt(
                adapter, mailbox, task_id="task-a", attempt=attempt, critique=critique,
            )
            self.assertEqual(verdict.outcome, FAILED)

            state = reduce(mailbox.read_all())
            remaining = MAX_ATTEMPTS - attempt
            decision = retry_or_block(state, "task-a", verdict.critique, remaining)

            if decision.action == RETRY:
                critique = decision.critique
                continue

            adapter.emit_status(
                mailbox, run_id=RUN_ID, phase=decision.phase,
                context={"task_id": "task-a", "critique": decision.critique},
            )
            return mailbox

        raise AssertionError(
            "retry_or_block never returned a terminal decision within "
            f"{MAX_ATTEMPTS} attempts -- the budget check is broken"
        )

    def test_exhausted_retries_reach_a_named_terminal_state(self):
        mailbox = self._drive()
        final_state = reduce(mailbox.read_all())
        self.assertIn(final_state.phase, ("blocked", "awaiting-user-input"))
        self.assertNotEqual(final_state.phase, "completed")
        self.assertEqual(status_of(final_state, "task-a"), "failed")

    def test_task_b_never_ran(self):
        mailbox = self._drive()
        final_state = reduce(mailbox.read_all())
        self.assertEqual(status_of(final_state, "task-b"), "pending")
        for envelope in mailbox.read_all():
            self.assertNotEqual(envelope.payload.get("task_id"), "task-b")

    def test_task_a_attempts_are_bounded_at_exactly_max_attempts(self):
        mailbox = self._drive()
        request_attempts = sorted(
            envelope.payload["attempt"]
            for envelope in mailbox.read_all()
            if envelope.kind == "request" and envelope.payload.get("task_id") == "task-a"
        )
        self.assertEqual(request_attempts, [1, 2, 3])

    def test_run_never_reaches_next_tasks_runnable_for_b(self):
        mailbox = self._drive()
        final_state = reduce(mailbox.read_all())
        self.assertEqual(next_tasks(DAG, final_state), ())


if __name__ == "__main__":
    unittest.main()
