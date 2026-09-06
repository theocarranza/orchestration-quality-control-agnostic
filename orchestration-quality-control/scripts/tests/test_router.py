import unittest

from kernel_specs import Envelope, TaskDag
from qc_lib import Blocked
from router import next_tasks, validate_pair
from run_state import reduce


class NextTasksTest(unittest.TestCase):
    def test_empty_dag_returns_empty_tuple(self):
        dag = TaskDag.from_list([])
        state = reduce([])
        result = next_tasks(dag, state)
        self.assertEqual(result, ())

    def test_single_task_with_no_deps_is_runnable(self):
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "worker", "depends_on": []},
        ])
        state = reduce([])
        result = next_tasks(dag, state)
        self.assertEqual(result, ("task-1",))

    def test_dependent_task_not_runnable_until_dependency_passes(self):
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "worker", "depends_on": []},
            {"task_id": "task-2", "role": "worker", "depends_on": ["task-1"]},
        ])
        state = reduce([])
        # Initially, only task-1 is runnable
        result = next_tasks(dag, state)
        self.assertEqual(result, ("task-1",))

    def test_dependent_task_not_runnable_while_dependency_running(self):
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "worker", "depends_on": []},
            {"task_id": "task-2", "role": "worker", "depends_on": ["task-1"]},
        ])
        request = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "orchestrator",
            "recipient": "agent:worker-1",
            "kind": "request",
            # attempt is required on a 'request' payload as of run_state's
            # round-3 attempt-bookkeeping fix (Outcome 2 Task 4); this
            # fixture only needed updating to keep carrying task_id, not
            # any change to what the test asserts.
            "payload": {"task_id": "task-1", "attempt": 1},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([request])
        result = next_tasks(dag, state)
        self.assertEqual(result, ())

    def test_dependent_task_not_runnable_if_dependency_failed(self):
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "worker", "depends_on": []},
            {"task_id": "task-2", "role": "worker", "depends_on": ["task-1"]},
        ])
        result_failed = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "task-1", "attempt": 1, "outcome": "failed"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([result_failed])
        result = next_tasks(dag, state)
        self.assertEqual(result, ())

    def test_dependent_task_runnable_after_dependency_passes(self):
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "worker", "depends_on": []},
            {"task_id": "task-2", "role": "worker", "depends_on": ["task-1"]},
        ])
        result_passed = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "task-1", "attempt": 1, "outcome": "passed"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([result_passed])
        result = next_tasks(dag, state)
        self.assertEqual(result, ("task-2",))

    def test_diamond_dependency(self):
        dag = TaskDag.from_list([
            {"task_id": "root", "role": "root", "depends_on": []},
            {"task_id": "left", "role": "worker", "depends_on": ["root"]},
            {"task_id": "right", "role": "worker", "depends_on": ["root"]},
            {"task_id": "merge", "role": "worker", "depends_on": ["left", "right"]},
        ])
        # Initially only root is runnable
        state = reduce([])
        result = next_tasks(dag, state)
        self.assertEqual(result, ("root",))

        # After root passes, both left and right are runnable
        root_passes = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-1",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "root", "attempt": 1, "outcome": "passed"},
            "created_at": "2026-09-04T12:00:00Z",
        })
        state = reduce([root_passes])
        result = next_tasks(dag, state)
        self.assertEqual(tuple(sorted(result)), ("left", "right"))

        # After one passes, merge is not yet runnable
        left_passes = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-2",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "left", "attempt": 1, "outcome": "passed"},
            "created_at": "2026-09-04T12:00:01Z",
        })
        state = reduce([root_passes, left_passes])
        result = next_tasks(dag, state)
        self.assertEqual(result, ("right",))

        # After both pass, merge is runnable
        right_passes = Envelope.from_dict({
            "schema_version": 1,
            "envelope_id": "env-3",
            "run_id": "run-1",
            "sender": "agent:worker-1",
            "recipient": "orchestrator",
            "kind": "result",
            "payload": {"task_id": "right", "attempt": 1, "outcome": "passed"},
            "created_at": "2026-09-04T12:00:02Z",
        })
        state = reduce([root_passes, left_passes, right_passes])
        result = next_tasks(dag, state)
        self.assertEqual(result, ("merge",))

    def test_result_is_deterministic_sorted(self):
        dag = TaskDag.from_list([
            {"task_id": "task-a", "role": "worker", "depends_on": []},
            {"task_id": "task-b", "role": "worker", "depends_on": []},
            {"task_id": "task-c", "role": "worker", "depends_on": []},
        ])
        state = reduce([])
        result1 = next_tasks(dag, state)
        result2 = next_tasks(dag, state)
        self.assertEqual(result1, result2)
        self.assertEqual(result1, ("task-a", "task-b", "task-c"))

    def test_next_tasks_does_not_mutate_dag(self):
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "worker", "depends_on": []},
        ])
        state = reduce([])
        dag_before = dag.to_list()
        next_tasks(dag, state)
        dag_after = dag.to_list()
        self.assertEqual(dag_before, dag_after)

    def test_next_tasks_does_not_mutate_state(self):
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "worker", "depends_on": []},
        ])
        state = reduce([])
        state_before = dict(state.task_status)
        next_tasks(dag, state)
        state_after = dict(state.task_status)
        self.assertEqual(state_before, state_after)


class ValidatePairTest(unittest.TestCase):
    def test_root_to_orchestrator_is_legal(self):
        validate_pair("root", "orchestrator")  # Should not raise

    def test_orchestrator_to_root_is_legal(self):
        validate_pair("orchestrator", "root")  # Should not raise

    def test_orchestrator_to_worker_is_legal(self):
        validate_pair("orchestrator", "agent:worker-1")  # Should not raise

    def test_worker_to_orchestrator_is_legal(self):
        validate_pair("agent:worker-1", "orchestrator")  # Should not raise

    def test_root_to_worker_is_illegal(self):
        with self.assertRaises(Blocked) as ctx:
            validate_pair("root", "agent:worker-1")
        self.assertIn("communicate directly", ctx.exception.detail.lower())
        self.assertIn("orchestrator", ctx.exception.detail.lower())

    def test_worker_to_root_is_illegal(self):
        with self.assertRaises(Blocked) as ctx:
            validate_pair("agent:worker-1", "root")
        self.assertIn("communicate directly", ctx.exception.detail.lower())
        self.assertIn("orchestrator", ctx.exception.detail.lower())

    def test_worker_to_worker_is_illegal(self):
        with self.assertRaises(Blocked) as ctx:
            validate_pair("agent:worker-1", "agent:worker-2")
        self.assertIn("isolation", ctx.exception.detail.lower())

    def test_self_pair_root_is_illegal(self):
        with self.assertRaises(Blocked) as ctx:
            validate_pair("root", "root")
        self.assertIn("self", ctx.exception.detail.lower())

    def test_self_pair_orchestrator_is_illegal(self):
        with self.assertRaises(Blocked) as ctx:
            validate_pair("orchestrator", "orchestrator")
        self.assertIn("self", ctx.exception.detail.lower())

    def test_self_pair_worker_is_illegal(self):
        with self.assertRaises(Blocked) as ctx:
            validate_pair("agent:worker-1", "agent:worker-1")
        self.assertIn("self", ctx.exception.detail.lower())

    def test_unrecognized_sender_is_illegal(self):
        with self.assertRaises(Blocked) as ctx:
            validate_pair("mystery", "orchestrator")
        self.assertIn("unrecognized", ctx.exception.detail.lower())

    def test_unrecognized_recipient_is_illegal(self):
        with self.assertRaises(Blocked) as ctx:
            validate_pair("root", "unknown")
        self.assertIn("unrecognized", ctx.exception.detail.lower())


if __name__ == "__main__":
    unittest.main()
