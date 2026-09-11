import json
import os
import subprocess
import sys
import unittest
from dataclasses import FrozenInstanceError
from types import MappingProxyType

from tests import SCRIPTS_DIR

from qc_lib import Blocked
from kernel_specs import AgentSpec, Envelope, GENESIS_HASH, RunSpec, TaskNode, TaskDag, validate_root_answer


class RootAnswerSchemaTest(unittest.TestCase):
    def _answer(self, **overrides):
        value = {"run_id": "run-1", "task_id": "task-1", "attempt": 1,
                 "question_id": "q-1", "decision": "retry", "text": "Proceed"}
        value.update(overrides)
        return value

    def test_valid_root_answer_is_accepted(self):
        self.assertEqual(validate_root_answer(self._answer())["decision"], "retry")

    def test_schema_rejects_required_types_values_and_extra_fields(self):
        for field in ("run_id", "task_id", "attempt", "question_id", "decision", "text"):
            with self.subTest(field=field):
                value = self._answer(); del value[field]
                with self.assertRaises(Blocked): validate_root_answer(value)
        for field, bad in (("run_id", ""), ("task_id", " "), ("question_id", ""), ("text", ""),
                           ("attempt", 0), ("attempt", True), ("decision", "maybe")):
            with self.subTest(field=field, bad=bad), self.assertRaises(Blocked):
                validate_root_answer(self._answer(**{field: bad}))
        with self.assertRaises(Blocked): validate_root_answer(self._answer(extra=True))

    def test_schema_rejects_wrong_type_for_each_field(self):
        invalid = {"run_id": 1, "task_id": [], "attempt": "1", "question_id": {},
                   "decision": 1, "text": None}
        for field, value in invalid.items():
            with self.subTest(field=field), self.assertRaises(Blocked):
                validate_root_answer(self._answer(**{field: value}))

    def test_schema_rejects_whitespace_only_nonblank_fields(self):
        for field in ("run_id", "task_id", "question_id", "text"):
            with self.subTest(field=field), self.assertRaises(Blocked):
                validate_root_answer(self._answer(**{field: " \t\n"}))


def _agent_dict(**overrides):
    data = {
        "schema_version": 1,
        "agent_id": "researcher-1",
        "role": "researcher",
        "capabilities": ["analyze", "summarize"],
        "tools": ["search"],
        "output_schema": "schemas/worker-result.schema.json",
        "model_tier": "medium",
        "reasoning_effort": "medium",
    }
    data.update(overrides)
    return data


def _run_dict(**overrides):
    data = {
        "schema_version": 1,
        "run_id": "run-0001",
        "goal": "Produce a reviewed report.",
        "created_at": "2026-09-04T12:00:00+00:00",
    }
    data.update(overrides)
    return data


def _envelope_dict(**overrides):
    data = {
        "schema_version": 2,
        "envelope_id": "env-0001",
        "run_id": "run-0001",
        "sender": "root",
        "recipient": "orchestrator",
        "kind": "request",
        "payload": {"note": "begin"},
        "created_at": "2026-09-04T12:00:00+00:00",
        "previous_hash": GENESIS_HASH,
    }
    data.update(overrides)
    return data


class AgentSpecTest(unittest.TestCase):
    def test_well_formed_agent_spec_constructs(self):
        spec = AgentSpec.from_dict(_agent_dict())
        self.assertEqual(spec.agent_id, "researcher-1")
        self.assertEqual(spec.capabilities, ("analyze", "summarize"))
        self.assertEqual(spec.tools, ("search",))

    def test_each_required_field_absence_is_named(self):
        for field_name in (
            "schema_version", "agent_id", "role", "capabilities", "tools",
            "output_schema", "model_tier", "reasoning_effort",
        ):
            with self.subTest(field=field_name):
                data = _agent_dict()
                del data[field_name]
                with self.assertRaises(Blocked) as ctx:
                    AgentSpec.from_dict(data)
                self.assertIn(field_name, ctx.exception.detail)

    def test_invalid_model_tier_is_named(self):
        with self.assertRaises(Blocked) as ctx:
            AgentSpec.from_dict(_agent_dict(model_tier="ultra"))
        self.assertIn("model_tier", ctx.exception.detail)

    def test_no_vendor_vocabulary_in_tiers(self):
        # "low"/"medium"/"high" are the only vocabulary a well-formed
        # AgentSpec may use for model/reasoning strength; a host name or
        # model id must be rejected the same way any other bad enum value is.
        with self.assertRaises(Blocked):
            AgentSpec.from_dict(_agent_dict(model_tier="claude-opus-4"))
        for tier in ("low", "medium", "high"):
            spec = AgentSpec.from_dict(_agent_dict(model_tier=tier, reasoning_effort=tier))
            self.assertEqual(spec.model_tier, tier)

    def test_mutation_after_construction_raises(self):
        spec = AgentSpec.from_dict(_agent_dict())
        with self.assertRaises(FrozenInstanceError):
            spec.agent_id = "other"

    def test_capability_tuple_item_assignment_raises(self):
        spec = AgentSpec.from_dict(_agent_dict())
        with self.assertRaises(TypeError):
            spec.capabilities[0] = "x"

    def test_trailing_newline_in_identifier_is_rejected(self):
        # re.match's '$' matches before a trailing newline, so a naive
        # pattern check would let 'agent-1\n' through as if it were 'agent-1'.
        with self.assertRaises(Blocked) as ctx:
            AgentSpec.from_dict(_agent_dict(agent_id="researcher-1\n"))
        self.assertIn("agent_id", ctx.exception.detail)

    def test_trailing_newline_in_token_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            AgentSpec.from_dict(_agent_dict(capabilities=["analyze\n"]))
        self.assertIn("capabilities", ctx.exception.detail)

    def test_serialisation_round_trips_byte_stably(self):
        spec = AgentSpec.from_dict(_agent_dict())
        first = spec.to_json()
        restored = AgentSpec.from_json(first)
        second = restored.to_json()
        self.assertEqual(first, second)
        self.assertEqual(spec.to_dict(), restored.to_dict())

        # Key order in the source mapping must not affect the wire form.
        reordered = dict(reversed(list(_agent_dict().items())))
        reordered_json = AgentSpec.from_dict(reordered).to_json()
        self.assertEqual(first, reordered_json)


class RunSpecTest(unittest.TestCase):
    def test_well_formed_run_spec_constructs(self):
        spec = RunSpec.from_dict(_run_dict())
        self.assertEqual(spec.run_id, "run-0001")
        self.assertEqual(spec.goal, "Produce a reviewed report.")

    def test_each_required_field_absence_is_named(self):
        for field_name in ("schema_version", "run_id", "goal", "created_at"):
            with self.subTest(field=field_name):
                data = _run_dict()
                del data[field_name]
                with self.assertRaises(Blocked) as ctx:
                    RunSpec.from_dict(data)
                self.assertIn(field_name, ctx.exception.detail)

    def test_mutation_after_construction_raises(self):
        spec = RunSpec.from_dict(_run_dict())
        with self.assertRaises(FrozenInstanceError):
            spec.goal = "different"

    def test_trailing_newline_in_identifier_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            RunSpec.from_dict(_run_dict(run_id="run-0001\n"))
        self.assertIn("run_id", ctx.exception.detail)

    def test_zulu_suffixed_datetime_is_accepted(self):
        # RFC 3339's 'Z' offset must validate identically on every supported
        # interpreter, not only on the ones whose datetime.fromisoformat
        # happens to accept 'Z' natively.
        spec = RunSpec.from_dict(_run_dict(created_at="2026-09-04T12:00:00Z"))
        self.assertEqual(spec.created_at, "2026-09-04T12:00:00Z")

    def test_date_only_string_is_rejected(self):
        # A bare calendar date has no time component and must not be
        # accepted as a date-time, on any interpreter.
        with self.assertRaises(Blocked) as ctx:
            RunSpec.from_dict(_run_dict(created_at="2026-09-04"))
        self.assertIn("created_at", ctx.exception.detail)

    def test_serialisation_round_trips_byte_stably(self):
        spec = RunSpec.from_dict(_run_dict())
        first = spec.to_json()
        second = RunSpec.from_json(first).to_json()
        self.assertEqual(first, second)
        self.assertEqual(spec.to_dict(), RunSpec.from_json(first).to_dict())


class EnvelopeTest(unittest.TestCase):
    def setUp(self):
        schema_path = SCRIPTS_DIR.parent / "schemas" / "envelope.schema.json"
        self.schema = json.loads(schema_path.read_text())

    def test_well_formed_envelope_validates_against_schema(self):
        data = _envelope_dict()
        # The fixture must exercise every field the schema requires, and
        # nothing else, since additionalProperties is false.
        self.assertEqual(sorted(self.schema["required"]), sorted(data.keys()))
        envelope = Envelope.from_dict(data)
        self.assertEqual(envelope.kind, "request")
        self.assertEqual(envelope.sender, "root")

    def test_each_required_field_absence_is_named(self):
        for field_name in self.schema["required"]:
            with self.subTest(field=field_name):
                data = _envelope_dict()
                del data[field_name]
                with self.assertRaises(Blocked) as ctx:
                    Envelope.from_dict(data)
                self.assertIn(field_name, ctx.exception.detail)

    def test_unknown_kind_is_rejected_by_schema(self):
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(kind="not-a-kind"))
        self.assertIn("kind", ctx.exception.detail)

    def test_unexpected_field_is_rejected_by_schema(self):
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(host="claude"))
        self.assertIn("host", ctx.exception.detail)

    def test_no_vendor_vocabulary_in_kind_enum(self):
        self.assertEqual(
            sorted(self.schema["properties"]["kind"]["enum"]),
            sorted(["request", "result", "status", "question", "answer"]),
        )

    def test_mutation_after_construction_raises(self):
        envelope = Envelope.from_dict(_envelope_dict())
        with self.assertRaises(FrozenInstanceError):
            envelope.sender = "other"

    def test_payload_item_assignment_raises(self):
        envelope = Envelope.from_dict(_envelope_dict())
        with self.assertRaises(TypeError):
            envelope.payload["note"] = "changed"

    def test_nested_payload_mutation_raises(self):
        # _freeze must recurse: a shallow implementation would leave the
        # top-level payload frozen while nested dicts/lists stayed mutable,
        # and every other test in this file would still pass. Prove the
        # nested case explicitly, for a dict, a list item, and append.
        envelope = Envelope.from_dict(_envelope_dict(payload={
            "nested": {"inner": "value"},
            "items": ["a", "b"],
        }))
        with self.assertRaises(TypeError):
            envelope.payload["nested"]["inner"] = "changed"
        with self.assertRaises(TypeError):
            envelope.payload["items"][0] = "changed"
        with self.assertRaises(AttributeError):
            envelope.payload["items"].append("c")

    def test_direct_construction_with_frozen_top_level_freezes_nested_too(self):
        # Envelope is a public frozen dataclass; nothing forces construction
        # through from_dict. If a caller (or a future mailbox/router module)
        # hands the constructor an already-MappingProxyType payload whose
        # nested dicts/lists are still plain, _freeze must not short-circuit
        # on the already-frozen top level and skip recursing into them.
        payload = MappingProxyType({
            "nested": {"inner": "value"},
            "items": ["a", "b"],
        })
        envelope = Envelope(
            schema_version=2,
            envelope_id="env-0002",
            run_id="run-0001",
            sender="root",
            recipient="orchestrator",
            kind="request",
            payload=payload,
            created_at="2026-09-04T12:00:00+00:00",
            previous_hash=GENESIS_HASH,
        )
        with self.assertRaises(TypeError):
            envelope.payload["nested"]["inner"] = "MUTATED"
        with self.assertRaises(TypeError):
            envelope.payload["items"][0] = "MUTATED"
        with self.assertRaises(AttributeError):
            envelope.payload["items"].append("c")

    def test_trailing_newline_in_identifier_is_rejected_by_schema(self):
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(envelope_id="env-0001\n"))
        self.assertIn("envelope_id", ctx.exception.detail)

    def test_zulu_suffixed_datetime_is_accepted(self):
        envelope = Envelope.from_dict(_envelope_dict(created_at="2026-09-04T12:00:00Z"))
        self.assertEqual(envelope.created_at, "2026-09-04T12:00:00Z")

    def test_date_only_string_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(created_at="2026-09-04"))
        self.assertIn("created_at", ctx.exception.detail)

    def test_serialisation_round_trips_byte_stably(self):
        envelope = Envelope.from_dict(_envelope_dict())
        first = envelope.to_json()
        restored = Envelope.from_json(first)
        second = restored.to_json()
        self.assertEqual(first, second)
        self.assertEqual(envelope.to_dict(), restored.to_dict())

    def test_schema_version_1_is_now_rejected(self):
        # schema_version bumped from 1 to 2 (Outcome 3 Task 1): the old
        # value must now fail exactly like any other wrong const, not be
        # silently accepted as a still-valid prior version. No migration
        # path is owed -- no persisted mailbox exists outside tests.
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(schema_version=1))
        self.assertIn("schema_version", ctx.exception.detail)

    def test_previous_hash_field_round_trips_through_json(self):
        envelope = Envelope.from_dict(_envelope_dict(previous_hash="a" * 64))
        self.assertEqual(envelope.previous_hash, "a" * 64)
        restored = Envelope.from_json(envelope.to_json())
        self.assertEqual(restored.previous_hash, "a" * 64)

    def test_previous_hash_must_match_the_64_hex_character_pattern(self):
        with self.assertRaises(Blocked) as ctx:
            Envelope.from_dict(_envelope_dict(previous_hash="not-a-hash"))
        self.assertIn("previous_hash", ctx.exception.detail)

    def test_previous_hash_rejects_uppercase_hex(self):
        # The pattern is deliberately lowercase-only, matching
        # hashlib.sha256(...).hexdigest()'s own output exactly -- accepting
        # uppercase too would let two textually-different previous_hash
        # values be treated as "the same hash" by string comparison
        # elsewhere, which they must never be.
        with self.assertRaises(Blocked):
            Envelope.from_dict(_envelope_dict(previous_hash="A" * 64))

    def test_genesis_hash_is_64_lowercase_hex_characters(self):
        # GENESIS_HASH must itself satisfy the same pattern every other
        # previous_hash value does -- schemas/envelope.schema.json has no
        # separate carve-out for it.
        self.assertEqual(len(GENESIS_HASH), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in GENESIS_HASH))
        Envelope.from_dict(_envelope_dict(previous_hash=GENESIS_HASH))  # does not raise


class EnvelopeHashChainTest(unittest.TestCase):
    # Outcome 3 Task 1: Envelope.hash() is what the *next* envelope in a
    # mailbox records as its own previous_hash (via
    # adapter_port.AdapterPort._append) -- these tests pin the properties
    # that make that chaining meaningful: the same content always hashes
    # identically, and different content never accidentally collides.

    def test_hash_is_a_64_character_lowercase_hex_string(self):
        envelope = Envelope.from_dict(_envelope_dict())
        digest = envelope.hash()
        self.assertEqual(len(digest), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in digest))

    def test_hash_is_deterministic_for_identical_content(self):
        first = Envelope.from_dict(_envelope_dict())
        second = Envelope.from_dict(_envelope_dict())
        self.assertEqual(first.hash(), second.hash())

    def test_hash_is_deterministic_regardless_of_source_dict_key_order(self):
        # to_json() is already proven key-order-independent
        # (test_serialisation_round_trips_byte_stably's reordering check on
        # the sibling record types); hash() must inherit that property
        # rather than reintroduce order-sensitivity via a second,
        # divergent serialisation.
        forward = Envelope.from_dict(_envelope_dict())
        reordered_source = dict(reversed(list(_envelope_dict().items())))
        reordered = Envelope.from_dict(reordered_source)
        self.assertEqual(forward.hash(), reordered.hash())

    def test_hash_changes_when_the_payload_changes(self):
        base = Envelope.from_dict(_envelope_dict())
        changed = Envelope.from_dict(_envelope_dict(payload={"note": "different"}))
        self.assertNotEqual(base.hash(), changed.hash())

    def test_hash_changes_when_only_previous_hash_changes(self):
        # An envelope's own hash covers its own previous_hash field too
        # (it is computed over the *whole* canonical JSON) -- this is what
        # makes the chain transitive: tampering an earlier entry changes
        # its hash, which changes every later envelope's previous_hash
        # requirement, not just the one immediately following it.
        first = Envelope.from_dict(_envelope_dict(previous_hash=GENESIS_HASH))
        second = Envelope.from_dict(_envelope_dict(previous_hash="b" * 64))
        self.assertNotEqual(first.hash(), second.hash())

    def test_hash_is_not_a_stored_field_on_the_envelope_itself(self):
        # "An envelope's own hash is derived, never stored on itself" --
        # to_dict()/to_json() must not carry a 'hash' key, and computing it
        # is a method call, not attribute access.
        envelope = Envelope.from_dict(_envelope_dict())
        self.assertNotIn("hash", envelope.to_dict())
        self.assertFalse(hasattr(envelope, "hash_"))
        self.assertTrue(callable(envelope.hash))

    def test_hash_is_identical_across_two_interpreter_processes_with_different_pythonhashseed(self):
        # The brief's explicit determinism requirement: the same envelope
        # content must hash identically in any process, under any
        # PYTHONHASHSEED. hashlib.sha256 itself is unaffected by
        # PYTHONHASHSEED (that only perturbs Python's built-in hash(), used
        # by dict/set iteration order before Python's dicts guaranteed
        # insertion order) -- but the *content* fed to it comes from
        # to_json()'s sort_keys=True canonical serialisation, which must
        # never depend on it either. Proven directly, in two real
        # subprocesses with two different PYTHONHASHSEED values, rather
        # than merely asserted from reading the implementation.
        script = (
            "import sys; sys.path.insert(0, {scripts_dir!r}); "
            "from kernel_specs import Envelope; "
            "data = {data!r}; "
            "print(Envelope.from_dict(data).hash())"
        ).format(scripts_dir=str(SCRIPTS_DIR), data=_envelope_dict(
            payload={"nested": {"b": 2, "a": 1}, "items": [1, 2, 3]},
        ))

        def _hash_in_subprocess(pythonhashseed):
            env = dict(os.environ)
            env["PYTHONHASHSEED"] = pythonhashseed
            completed = subprocess.run(
                [sys.executable, "-c", script],
                env=env, capture_output=True, text=True, check=True,
            )
            return completed.stdout.strip()

        first = _hash_in_subprocess("0")
        second = _hash_in_subprocess("1")
        third = _hash_in_subprocess("random")
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(len(first), 64)


class TaskNodeTest(unittest.TestCase):
    def test_well_formed_task_node_constructs(self):
        node = TaskNode.from_dict({
            "task_id": "analyze-target",
            "role": "researcher",
            "depends_on": ["discover-files"],
        })
        self.assertEqual(node.task_id, "analyze-target")
        self.assertEqual(node.role, "researcher")
        self.assertEqual(node.depends_on, ("discover-files",))

    def test_task_node_with_empty_depends_on(self):
        node = TaskNode.from_dict({
            "task_id": "root-task",
            "role": "root",
            "depends_on": [],
        })
        self.assertEqual(node.depends_on, ())

    def test_each_required_field_absence_is_named(self):
        for field_name in ("task_id", "role", "depends_on"):
            with self.subTest(field=field_name):
                data = {
                    "task_id": "task-1",
                    "role": "worker",
                    "depends_on": [],
                }
                del data[field_name]
                with self.assertRaises(Blocked) as ctx:
                    TaskNode.from_dict(data)
                self.assertIn(field_name, ctx.exception.detail)

    def test_task_node_mutation_after_construction_raises(self):
        node = TaskNode.from_dict({
            "task_id": "task-1",
            "role": "worker",
            "depends_on": [],
        })
        with self.assertRaises(FrozenInstanceError):
            node.task_id = "task-2"

    def test_task_node_serialisation_round_trips(self):
        node = TaskNode.from_dict({
            "task_id": "task-1",
            "role": "worker",
            "depends_on": ["task-0"],
        })
        first = node.to_json()
        restored = TaskNode.from_json(first)
        second = restored.to_json()
        self.assertEqual(first, second)

    def test_invalid_identifier_in_depends_on_labels_correct_index(self):
        # Verify error labels index correctly when invalid item is not first
        with self.assertRaises(Blocked) as ctx:
            TaskNode.from_dict({
                "task_id": "task-1",
                "role": "worker",
                "depends_on": ["good-id", "Bad-With-Caps", "another-good-id"],
            })
        # Should report error at index 1 (the invalid "Bad-With-Caps")
        self.assertIn("depends_on[1]", ctx.exception.detail)
        self.assertIn("Bad-With-Caps", ctx.exception.detail)


class TaskDagTest(unittest.TestCase):
    def test_well_formed_task_dag_constructs(self):
        dag = TaskDag.from_list([
            {"task_id": "discover", "role": "root", "depends_on": []},
            {"task_id": "analyze", "role": "worker", "depends_on": ["discover"]},
        ])
        self.assertEqual(len(dag.tasks), 2)
        self.assertEqual(dag.tasks[0].task_id, "discover")
        self.assertEqual(dag.tasks[1].depends_on, ("discover",))

    def test_duplicate_task_id_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": []},
                {"task_id": "task-1", "role": "worker", "depends_on": []},
            ])
        self.assertIn("duplicate", ctx.exception.detail.lower())
        self.assertIn("task_id", ctx.exception.detail)

    def test_unknown_dependency_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": []},
                {"task_id": "task-2", "role": "worker", "depends_on": ["unknown-task"]},
            ])
        self.assertIn("unknown", ctx.exception.detail.lower())
        self.assertIn("unknown-task", ctx.exception.detail)

    def test_cycle_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": ["task-2"]},
                {"task_id": "task-2", "role": "worker", "depends_on": ["task-1"]},
            ])
        self.assertIn("cycle", ctx.exception.detail.lower())

    def test_self_loop_cycle_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": ["task-1"]},
            ])
        self.assertIn("cycle", ctx.exception.detail.lower())

    def test_longer_cycle_is_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "task-1", "role": "root", "depends_on": ["task-2"]},
                {"task_id": "task-2", "role": "worker", "depends_on": ["task-3"]},
                {"task_id": "task-3", "role": "worker", "depends_on": ["task-1"]},
            ])
        self.assertIn("cycle", ctx.exception.detail.lower())

    def test_task_dag_serialisation_round_trips(self):
        data = [
            {"task_id": "discover", "role": "root", "depends_on": []},
            {"task_id": "analyze", "role": "worker", "depends_on": ["discover"]},
        ]
        dag = TaskDag.from_list(data)
        first = dag.to_json()
        restored = TaskDag.from_json(first)
        second = restored.to_json()
        self.assertEqual(first, second)

    def test_task_dag_mutation_after_construction_raises(self):
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "root", "depends_on": []},
        ])
        with self.assertRaises(TypeError):
            dag.tasks[0] = None

    def test_task_dag_field_reassignment_raises(self):
        # test_task_dag_mutation_after_construction_raises only proves the
        # `tasks` tuple itself rejects item assignment, which is true of
        # any tuple whether or not TaskDag is frozen -- it would pass
        # identically with `frozen=True` removed. Reassigning the `tasks`
        # field itself is what actually exercises TaskDag's own frozen
        # guarantee.
        dag = TaskDag.from_list([
            {"task_id": "task-1", "role": "root", "depends_on": []},
        ])
        with self.assertRaises(FrozenInstanceError):
            dag.tasks = ()

    def test_cycle_reachable_only_through_a_diamond_is_rejected(self):
        # A cycle that is not on the first edge explored from the entry
        # node, but only becomes visible after fanning out through a
        # diamond (start -> b1, start -> b2 -> both merge back into
        # `merge`, which depends on `start` again). Detection must not
        # depend on which branch of the diamond happens to be visited
        # first.
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list([
                {"task_id": "start", "role": "root", "depends_on": ["merge"]},
                {"task_id": "b1", "role": "worker", "depends_on": ["start"]},
                {"task_id": "b2", "role": "worker", "depends_on": ["start"]},
                {"task_id": "merge", "role": "worker", "depends_on": ["b1", "b2"]},
            ])
        self.assertIn("cycle", ctx.exception.detail.lower())

    def test_long_linear_chain_constructs_without_recursion_error(self):
        # Regression for unbounded Python recursion in cycle detection: a
        # mostly-linear pipeline (exactly what a DAG generator emits) must
        # not depend on sys.getrecursionlimit() to construct successfully.
        # 5000 nodes comfortably exceeds the default recursion limit
        # (1000), so this fails loudly with RecursionError under a
        # recursive visit() and must pass under an iterative one.
        node_count = 5000
        data = [{"task_id": "task-0", "role": "root", "depends_on": []}]
        for index in range(1, node_count):
            data.append({
                "task_id": f"task-{index}",
                "role": "worker",
                "depends_on": [f"task-{index - 1}"],
            })
        dag = TaskDag.from_list(data)
        self.assertEqual(len(dag.tasks), node_count)

    def test_long_chain_with_back_edge_raises_blocked_not_recursion_error(self):
        node_count = 5000
        data = [{"task_id": "task-0", "role": "root", "depends_on": [f"task-{node_count - 1}"]}]
        for index in range(1, node_count):
            data.append({
                "task_id": f"task-{index}",
                "role": "worker",
                "depends_on": [f"task-{index - 1}"],
            })
        with self.assertRaises(Blocked) as ctx:
            TaskDag.from_list(data)
        self.assertIn("cycle", ctx.exception.detail.lower())


class WorkerResultSchemaTest(unittest.TestCase):
    def test_public_validator_enforces_minimum_and_min_length(self):
        from kernel_specs import validate_worker_result
        with self.assertRaises(Blocked):
            validate_worker_result({"task_id": "", "attempt": 0, "outcome": "passed"})

    def test_min_length_is_checked_independently(self):
        from kernel_specs import validate_worker_result
        with self.assertRaises(Blocked) as ctx:
            validate_worker_result({"task_id": "", "attempt": 1, "outcome": "passed"})
        self.assertIn("task_id", ctx.exception.detail)

    def test_minimum_is_checked_independently(self):
        from kernel_specs import validate_worker_result
        with self.assertRaises(Blocked) as ctx:
            validate_worker_result({"task_id": "t", "attempt": 0, "outcome": "passed"})
        self.assertIn("attempt", ctx.exception.detail)

    def test_integer_minimum_rejects_boolean(self):
        from kernel_specs import validate_worker_result
        with self.assertRaises(Blocked):
            validate_worker_result({"task_id": "t", "attempt": True, "outcome": "passed"})

    def test_required_fields_are_enforced_individually(self):
        from kernel_specs import validate_worker_result
        for field in ("task_id", "attempt", "outcome"):
            result = {"task_id": "t", "attempt": 1, "outcome": "passed"}
            result.pop(field)
            with self.subTest(field=field), self.assertRaises(Blocked):
                validate_worker_result(result)

    def test_field_types_are_enforced(self):
        from kernel_specs import validate_worker_result
        for field, value in (("task_id", 1), ("attempt", "1"), ("outcome", 1)):
            result = {"task_id": "t", "attempt": 1, "outcome": "passed"}
            result[field] = value
            with self.subTest(field=field), self.assertRaises(Blocked):
                validate_worker_result(result)

    def test_outcome_enum_is_enforced(self):
        from kernel_specs import validate_worker_result
        with self.assertRaises(Blocked):
            validate_worker_result({"task_id": "t", "attempt": 1, "outcome": "unknown"})

    def test_top_level_extra_fields_are_rejected(self):
        from kernel_specs import validate_worker_result
        with self.assertRaises(Blocked):
            validate_worker_result({"task_id": "t", "attempt": 1, "outcome": "passed", "extra": True})

    def test_question_required_fields_are_enforced_individually(self):
        from kernel_specs import validate_worker_result
        for field in ("question_id", "prompt"):
            question = {"question_id": "q", "prompt": "Choose"}
            question.pop(field)
            with self.subTest(field=field), self.assertRaises(Blocked):
                validate_worker_result({"task_id": "t", "attempt": 1, "outcome": "failed", "critique": "why", "question": question})

    def test_question_field_types_are_enforced(self):
        from kernel_specs import validate_worker_result
        for field in ("question_id", "prompt"):
            question = {"question_id": "q", "prompt": "Choose"}
            question[field] = 1
            with self.subTest(field=field), self.assertRaises(Blocked):
                validate_worker_result({"task_id": "t", "attempt": 1, "outcome": "failed", "critique": "why", "question": question})

    def test_question_min_length_is_enforced(self):
        from kernel_specs import validate_worker_result
        for field in ("question_id", "prompt"):
            question = {"question_id": "q", "prompt": "Choose"}
            question[field] = ""
            with self.subTest(field=field), self.assertRaises(Blocked):
                validate_worker_result({"task_id": "t", "attempt": 1, "outcome": "failed", "critique": "why", "question": question})

    def test_question_extra_fields_are_rejected(self):
        from kernel_specs import validate_worker_result
        with self.assertRaises(Blocked):
            validate_worker_result({"task_id": "t", "attempt": 1, "outcome": "failed", "critique": "why", "question": {"question_id": "q", "prompt": "Choose", "extra": True}})


if __name__ == "__main__":
    unittest.main()
