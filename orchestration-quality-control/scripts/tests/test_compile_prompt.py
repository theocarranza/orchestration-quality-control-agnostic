"""Tests for compile_prompt.compile_brief: determinism, byte-stability, the
critique-carrying mechanism Task 4's Fixture A depends on, and vendor
neutrality.
"""

import json
import unittest

from compile_prompt import compile_brief
from kernel_specs import AgentSpec, MODEL_TIERS, REASONING_EFFORTS, TaskNode
from qc_lib import Blocked


def _task_node(**overrides):
    data = {"task_id": "task-a", "role": "worker", "depends_on": []}
    data.update(overrides)
    return TaskNode.from_dict(data)


def _agent_spec(**overrides):
    data = {
        "schema_version": 1,
        "agent_id": "worker-1",
        "role": "worker",
        "capabilities": ["analyze", "summarize"],
        "tools": ["search"],
        "output_schema": "schemas/worker-result.schema.json",
        "model_tier": "medium",
        "reasoning_effort": "medium",
    }
    data.update(overrides)
    return AgentSpec.from_dict(data)


class DeterminismTest(unittest.TestCase):
    def test_identical_inputs_produce_an_equal_brief(self):
        brief_1 = compile_brief(_task_node(), _agent_spec(), critique="off by one", attempt=2)
        brief_2 = compile_brief(_task_node(), _agent_spec(), critique="off by one", attempt=2)
        self.assertEqual(brief_1, brief_2)
        self.assertIsNot(brief_1, brief_2)

    def test_identical_inputs_are_byte_stable_when_serialised(self):
        brief_1 = compile_brief(_task_node(), _agent_spec(), critique="off by one", attempt=2)
        brief_2 = compile_brief(_task_node(), _agent_spec(), critique="off by one", attempt=2)
        json_1 = json.dumps(brief_1, sort_keys=True, separators=(",", ":"))
        json_2 = json.dumps(brief_2, sort_keys=True, separators=(",", ":"))
        self.assertEqual(json_1, json_2)

    def test_a_different_attempt_number_produces_a_different_brief(self):
        brief_1 = compile_brief(_task_node(), _agent_spec(), attempt=1)
        brief_2 = compile_brief(_task_node(), _agent_spec(), attempt=2)
        self.assertNotEqual(brief_1, brief_2)


class CritiqueReachesTheBriefTest(unittest.TestCase):
    # The load-bearing evidence Task 4's Fixture A and gate.retry_or_block's
    # own contract depend on: a critique passed in must appear in the
    # compiled brief.
    def test_a_critique_appears_verbatim_in_the_brief(self):
        brief = compile_brief(_task_node(), _agent_spec(), critique="off-by-one in the boundary check", attempt=2)
        self.assertEqual(brief["critique"], "off-by-one in the boundary check")

    def test_critique_key_is_present_and_none_when_not_supplied(self):
        brief = compile_brief(_task_node(), _agent_spec())
        self.assertIn("critique", brief)
        self.assertIsNone(brief["critique"])

    def test_critique_key_is_present_and_none_when_explicitly_none(self):
        brief = compile_brief(_task_node(), _agent_spec(), critique=None, attempt=1)
        self.assertIn("critique", brief)
        self.assertIsNone(brief["critique"])


class AttemptFieldTest(unittest.TestCase):
    def test_attempt_defaults_to_one(self):
        brief = compile_brief(_task_node(), _agent_spec())
        self.assertEqual(brief["attempt"], 1)

    def test_attempt_is_passed_through(self):
        brief = compile_brief(_task_node(), _agent_spec(), attempt=3)
        self.assertEqual(brief["attempt"], 3)


class FieldsCopiedFromInputsTest(unittest.TestCase):
    def test_task_id_comes_from_the_task_node(self):
        brief = compile_brief(_task_node(task_id="task-z"), _agent_spec(role="worker"))
        self.assertEqual(brief["task_id"], "task-z")

    def test_role_and_agent_id_come_from_the_agent_spec(self):
        brief = compile_brief(_task_node(), _agent_spec(agent_id="worker-9"))
        self.assertEqual(brief["role"], "worker")
        self.assertEqual(brief["agent_id"], "worker-9")

    def test_capabilities_tools_and_tiers_come_from_the_agent_spec(self):
        brief = compile_brief(
            _task_node(),
            _agent_spec(
                capabilities=["execute", "verify"],
                tools=["diff"],
                output_schema="schemas/out.json",
                model_tier="high",
                reasoning_effort="low",
            ),
        )
        self.assertEqual(brief["capabilities"], ["execute", "verify"])
        self.assertEqual(brief["tools"], ["diff"])
        self.assertEqual(brief["output_schema"], "schemas/out.json")
        self.assertEqual(brief["model_tier"], "high")
        self.assertEqual(brief["reasoning_effort"], "low")

    def test_every_model_tier_and_reasoning_effort_passes_through_unchanged(self):
        # Table test over the full closed vocabulary compile_brief must
        # never narrow or translate.
        for tier in MODEL_TIERS:
            for effort in REASONING_EFFORTS:
                with self.subTest(tier=tier, effort=effort):
                    brief = compile_brief(
                        _task_node(), _agent_spec(model_tier=tier, reasoning_effort=effort),
                    )
                    self.assertEqual(brief["model_tier"], tier)
                    self.assertEqual(brief["reasoning_effort"], effort)


class VendorNeutralityTest(unittest.TestCase):
    EXPECTED_KEYS = {
        "task_id", "role", "agent_id", "attempt", "capabilities", "tools",
        "output_schema", "model_tier", "reasoning_effort", "critique",
        "answer_context",
    }

    def test_brief_has_exactly_the_expected_keys(self):
        brief = compile_brief(_task_node(), _agent_spec())
        self.assertEqual(set(brief.keys()), self.EXPECTED_KEYS)

    def test_no_vendor_or_host_vocabulary_appears_anywhere_in_the_brief(self):
        brief = compile_brief(
            _task_node(), _agent_spec(), critique="some critique", attempt=2,
        )
        serialised = json.dumps(brief).lower()
        for forbidden in ("claude", "anthropic", "openai", "gpt", "gemini", "sonnet", "opus", "haiku"):
            self.assertNotIn(forbidden, serialised)

    def test_answer_context_is_explicit_and_deterministic(self):
        first = compile_brief(_task_node(), _agent_spec(), answer_context="retry with artifact")
        second = compile_brief(_task_node(), _agent_spec(), answer_context="retry with artifact")
        other = compile_brief(_task_node(), _agent_spec(), answer_context="stop and inspect")
        self.assertEqual(first["answer_context"], "retry with artifact")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)


class ValidationTest(unittest.TestCase):
    def test_non_task_node_task_node_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            compile_brief({"task_id": "task-a"}, _agent_spec())
        self.assertIn("task_node", ctx.exception.detail)

    def test_non_agent_spec_agent_spec_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            compile_brief(_task_node(), {"role": "worker"})
        self.assertIn("agent_spec", ctx.exception.detail)

    def test_mismatched_role_is_blocked(self):
        with self.assertRaises(Blocked) as ctx:
            compile_brief(_task_node(role="worker"), _agent_spec(role="reviewer"))
        self.assertIn("role", ctx.exception.detail.lower())

    def test_attempt_zero_is_blocked(self):
        with self.assertRaises(Blocked):
            compile_brief(_task_node(), _agent_spec(), attempt=0)

    def test_negative_attempt_is_blocked(self):
        with self.assertRaises(Blocked):
            compile_brief(_task_node(), _agent_spec(), attempt=-1)

    def test_boolean_attempt_is_rejected(self):
        # bool is a subclass of int in Python; True/False must not silently
        # pass as 1/0.
        with self.assertRaises(Blocked):
            compile_brief(_task_node(), _agent_spec(), attempt=True)

    def test_non_integer_attempt_is_blocked(self):
        with self.assertRaises(Blocked):
            compile_brief(_task_node(), _agent_spec(), attempt="1")

    def test_empty_string_critique_is_blocked(self):
        with self.assertRaises(Blocked):
            compile_brief(_task_node(), _agent_spec(), critique="")

    def test_whitespace_only_critique_is_blocked(self):
        with self.assertRaises(Blocked):
            compile_brief(_task_node(), _agent_spec(), critique="   ")

    def test_empty_or_non_string_answer_context_is_blocked(self):
        for value in ("", "   ", 7, object()):
            with self.subTest(value=value):
                with self.assertRaises(Blocked):
                    compile_brief(_task_node(), _agent_spec(), answer_context=value)

    def test_non_string_critique_is_blocked(self):
        with self.assertRaises(Blocked):
            compile_brief(_task_node(), _agent_spec(), critique=123)


if __name__ == "__main__":
    unittest.main()
