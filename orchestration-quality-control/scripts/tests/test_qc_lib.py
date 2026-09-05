import json
import unittest
from types import MappingProxyType

from tests import SCRIPTS_DIR

import qc_lib
from qc_lib import Blocked


class NormalizeTextTest(unittest.TestCase):
    def test_trailing_whitespace_stripped_per_line(self):
        self.assertEqual(qc_lib.normalize_text("hello   \nworld  "), "hello\nworld")

    def test_internal_whitespace_collapsed(self):
        self.assertEqual(qc_lib.normalize_text("a    b"), "a b")

    def test_blank_line_runs_collapsed(self):
        self.assertEqual(qc_lib.normalize_text("a\n\n\n\nb"), "a\n\nb")

    def test_unicode_nfc_normalized(self):
        # 'e' + combining acute (NFD) should normalize the same as precomposed é (NFC)
        nfd = "é"
        nfc = "é"
        self.assertEqual(qc_lib.normalize_text(nfd), qc_lib.normalize_text(nfc))


class NormalizePathTest(unittest.TestCase):
    def test_relative_path_accepted(self):
        self.assertEqual(qc_lib.normalize_path("references/rules/x.md", stage="test"), "references/rules/x.md")

    def test_absolute_path_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            qc_lib.normalize_path("/etc/passwd", stage="test")
        self.assertEqual(ctx.exception.reason_code, "target_outside_approved_set")

    def test_parent_traversal_rejected(self):
        with self.assertRaises(Blocked) as ctx:
            qc_lib.normalize_path("../../etc/passwd", stage="test")
        self.assertEqual(ctx.exception.reason_code, "target_outside_approved_set")

    def test_backslash_path_normalized_to_forward_slash(self):
        self.assertEqual(qc_lib.normalize_path("a\\b\\c.md", stage="test"), "a/b/c.md")


class InputSchemaTest(unittest.TestCase):
    def setUp(self):
        import json
        schema_path = SCRIPTS_DIR.parent / "references" / "schemas" / "input.schema.json"
        self.schema = json.loads(schema_path.read_text())

    def test_operation_enum(self):
        self.assertEqual(self.schema["properties"]["operation"]["enum"], ["qc", "upgrade", "author"])

    def test_language_enum_and_default(self):
        self.assertEqual(self.schema["properties"]["language"]["enum"], ["en", "pt-br"])
        self.assertEqual(self.schema["properties"]["language"]["default"], "en")

    def test_stop_after_prepare_type_and_default(self):
        self.assertEqual(self.schema["properties"]["stop_after_prepare"]["type"], "boolean")
        self.assertEqual(self.schema["properties"]["stop_after_prepare"]["default"], False)

    def test_decision_alternatives(self):
        decision_one_of = self.schema["properties"]["decision"]["oneOf"]
        consts = [alt.get("const") for alt in decision_one_of if "const" in alt]
        self.assertIn("all", consts)
        self.assertIn("none", consts)
        self.assertIn("approve", consts)
        self.assertIn("decline", consts)
        has_array = any(alt.get("type") == "array" for alt in decision_one_of)
        self.assertTrue(has_array)

    def test_required_fields(self):
        for item in self.schema.get("allOf", []):
            if "required" in item and "if" not in item:
                self.assertEqual(item["required"], ["operation", "profile", "language"])
                return
        self.fail("Could not find unconditional required in allOf")

    def test_targets_conditional_requirement(self):
        conditionals = [item for item in self.schema.get("allOf", []) if "if" in item and "then" in item]
        for cond in conditionals:
            if_op_enum = cond.get("if", {}).get("properties", {}).get("operation", {}).get("enum")
            if if_op_enum == ["qc", "upgrade"]:
                then_required = cond.get("then", {}).get("required", [])
                self.assertIn("targets", then_required)
                return
        self.fail("Could not find conditional requirement for targets on qc/upgrade")

    def test_additional_properties(self):
        self.assertEqual(self.schema["additionalProperties"], False)


class FreezeTest(unittest.TestCase):
    def test_freeze_simple_dict(self):
        """Test that a simple dict becomes a MappingProxyType."""
        data = {"a": 1, "b": 2}
        frozen = qc_lib.freeze(data)
        self.assertIsInstance(frozen, MappingProxyType)
        self.assertEqual(frozen["a"], 1)
        self.assertEqual(frozen["b"], 2)

    def test_freeze_nested_dict(self):
        """Test that nested dicts are recursively frozen."""
        data = {"outer": {"inner": {"deep": "value"}}}
        frozen = qc_lib.freeze(data)
        self.assertIsInstance(frozen, MappingProxyType)
        self.assertIsInstance(frozen["outer"], MappingProxyType)
        self.assertIsInstance(frozen["outer"]["inner"], MappingProxyType)
        self.assertEqual(frozen["outer"]["inner"]["deep"], "value")

    def test_freeze_list(self):
        """Test that a list becomes a tuple."""
        data = [1, 2, 3]
        frozen = qc_lib.freeze(data)
        self.assertIsInstance(frozen, tuple)
        self.assertEqual(frozen, (1, 2, 3))

    def test_freeze_nested_list(self):
        """Test that nested lists are recursively frozen."""
        data = [[1, 2], [3, 4]]
        frozen = qc_lib.freeze(data)
        self.assertIsInstance(frozen, tuple)
        self.assertIsInstance(frozen[0], tuple)
        self.assertIsInstance(frozen[1], tuple)
        self.assertEqual(frozen, ((1, 2), (3, 4)))

    def test_freeze_mixed_nesting(self):
        """Test that dicts and lists are recursively frozen together."""
        data = {"list": [1, 2, {"nested": "dict"}], "dict": {"key": [3, 4]}}
        frozen = qc_lib.freeze(data)
        self.assertIsInstance(frozen, MappingProxyType)
        self.assertIsInstance(frozen["list"], tuple)
        self.assertIsInstance(frozen["list"][2], MappingProxyType)
        self.assertIsInstance(frozen["dict"]["key"], tuple)

    def test_freeze_empty_dict(self):
        """Test that an empty dict is handled correctly."""
        frozen = qc_lib.freeze({})
        self.assertIsInstance(frozen, MappingProxyType)
        self.assertEqual(len(frozen), 0)

    def test_freeze_empty_list(self):
        """Test that an empty list is handled correctly."""
        frozen = qc_lib.freeze([])
        self.assertIsInstance(frozen, tuple)
        self.assertEqual(frozen, ())

    def test_freeze_already_frozen_mapping_proxy(self):
        """Test that an already-frozen MappingProxyType is recursively frozen.

        This must nest mutable structures inside the frozen container to catch
        a regression where freeze short-circuits on MappingProxyType without
        recursing into nested values.
        """
        # If freeze regresses to a short-circuit on MappingProxyType,
        # these nested plain dict and list would not be re-frozen.
        inner_dict = MappingProxyType({
            "mutable_dict": {"can_mutate": "me"},
            "mutable_list": [1, 2, 3],
        })
        data = {"outer": inner_dict}
        frozen = qc_lib.freeze(data)
        self.assertIsInstance(frozen, MappingProxyType)
        self.assertIsInstance(frozen["outer"], MappingProxyType)

        # These nested structures must be immutable:
        # Attempting to mutate the nested dict must raise
        with self.assertRaises(TypeError):
            frozen["outer"]["mutable_dict"]["new_key"] = "value"

        # Attempting to mutate the nested list (now a tuple) must raise
        with self.assertRaises(TypeError):
            frozen["outer"]["mutable_list"][0] = 999

    def test_freeze_already_frozen_tuple(self):
        """Test that an already-frozen tuple is recursively handled.

        This must nest mutable structures inside the frozen tuple to catch
        a regression where freeze short-circuits on tuple without
        recursing into nested values.
        """
        # If freeze regresses to a short-circuit on tuple,
        # these nested plain dict and list would not be re-frozen.
        data = {"key": ({"mutable_dict": "here"}, [1, 2, 3])}
        frozen = qc_lib.freeze(data)
        self.assertIsInstance(frozen, MappingProxyType)
        self.assertIsInstance(frozen["key"], tuple)

        # The nested dict (now a MappingProxyType) must not allow mutation
        with self.assertRaises(TypeError):
            frozen["key"][0]["new_key"] = "value"

        # The nested list (now a tuple) must not allow mutation
        with self.assertRaises(TypeError):
            frozen["key"][1][0] = 999

    def test_freeze_primitives(self):
        """Test that primitives pass through unchanged."""
        self.assertEqual(qc_lib.freeze(42), 42)
        self.assertEqual(qc_lib.freeze("string"), "string")
        self.assertEqual(qc_lib.freeze(3.14), 3.14)
        self.assertEqual(qc_lib.freeze(True), True)
        self.assertEqual(qc_lib.freeze(None), None)

    def test_freeze_mutability_is_enforced(self):
        """Test that frozen structures cannot be mutated."""
        data = {"key": "value"}
        frozen = qc_lib.freeze(data)
        with self.assertRaises(TypeError):
            frozen["key"] = "new_value"


class ThawTest(unittest.TestCase):
    def test_thaw_mapping_proxy(self):
        """Test that a MappingProxyType becomes a dict."""
        frozen = MappingProxyType({"a": 1, "b": 2})
        thawed = qc_lib.thaw(frozen)
        self.assertIsInstance(thawed, dict)
        self.assertEqual(thawed, {"a": 1, "b": 2})

    def test_thaw_nested_mapping_proxy(self):
        """Test that nested MappingProxyTypes are recursively thawed."""
        frozen = MappingProxyType({
            "outer": MappingProxyType({"inner": MappingProxyType({"deep": "value"})})
        })
        thawed = qc_lib.thaw(frozen)
        self.assertIsInstance(thawed, dict)
        self.assertIsInstance(thawed["outer"], dict)
        self.assertIsInstance(thawed["outer"]["inner"], dict)
        self.assertEqual(thawed["outer"]["inner"]["deep"], "value")

    def test_thaw_tuple(self):
        """Test that a tuple becomes a list."""
        frozen = (1, 2, 3)
        thawed = qc_lib.thaw(frozen)
        self.assertIsInstance(thawed, list)
        self.assertEqual(thawed, [1, 2, 3])

    def test_thaw_nested_tuple(self):
        """Test that nested tuples are recursively thawed."""
        frozen = ((1, 2), (3, 4))
        thawed = qc_lib.thaw(frozen)
        self.assertIsInstance(thawed, list)
        self.assertIsInstance(thawed[0], list)
        self.assertIsInstance(thawed[1], list)
        self.assertEqual(thawed, [[1, 2], [3, 4]])

    def test_thaw_mixed_nesting(self):
        """Test that MappingProxyTypes and tuples are recursively thawed together."""
        frozen = MappingProxyType({
            "list": (1, 2, MappingProxyType({"nested": "dict"})),
            "dict": MappingProxyType({"key": (3, 4)})
        })
        thawed = qc_lib.thaw(frozen)
        self.assertIsInstance(thawed, dict)
        self.assertIsInstance(thawed["list"], list)
        self.assertIsInstance(thawed["list"][2], dict)
        self.assertIsInstance(thawed["dict"]["key"], list)

    def test_thaw_empty_mapping_proxy(self):
        """Test that an empty MappingProxyType is handled correctly."""
        frozen = MappingProxyType({})
        thawed = qc_lib.thaw(frozen)
        self.assertIsInstance(thawed, dict)
        self.assertEqual(len(thawed), 0)

    def test_thaw_empty_tuple(self):
        """Test that an empty tuple is handled correctly."""
        thawed = qc_lib.thaw(())
        self.assertIsInstance(thawed, list)
        self.assertEqual(thawed, [])

    def test_thaw_primitives(self):
        """Test that primitives pass through unchanged."""
        self.assertEqual(qc_lib.thaw(42), 42)
        self.assertEqual(qc_lib.thaw("string"), "string")
        self.assertEqual(qc_lib.thaw(3.14), 3.14)
        self.assertEqual(qc_lib.thaw(True), True)
        self.assertEqual(qc_lib.thaw(None), None)

    def test_thaw_plain_dict_containing_frozen_values_is_fully_plain(self):
        """Test that thaw recurses into plain dicts to thaw nested frozen values.

        This is critical for symmetry with freeze. freeze is total: it accepts
        any mixture of plain and frozen values and returns everything frozen.
        thaw must be equally total: it accepts any mixture and returns
        everything plain and JSON-serialisable. This test catches the defect
        where thaw returned early on a plain dict, leaving frozen values nested
        inside it.
        """
        # Build a plain dict containing frozen values
        frozen_inner = qc_lib.freeze({"inner": [1, 2, 3]})
        plain_dict_with_frozen = {"context": frozen_inner}

        # thaw must recurse into the plain dict and thaw the nested frozen value
        thawed = qc_lib.thaw(plain_dict_with_frozen)

        # The result must be fully plain (no MappingProxyType, no tuple)
        self.assertIsInstance(thawed, dict)
        self.assertIsInstance(thawed["context"], dict)
        self.assertIsInstance(thawed["context"]["inner"], list)

        # The real-world consequence: it must be JSON-serialisable
        # (this would fail with TypeError if frozen values remained)
        json_str = json.dumps(thawed)
        self.assertIsInstance(json_str, str)
        # Deserialise to verify the thawed value round-trips through JSON
        recovered = json.loads(json_str)
        self.assertEqual(recovered, {"context": {"inner": [1, 2, 3]}})

    def test_thaw_plain_list_containing_frozen_values_is_fully_plain(self):
        """Test that thaw recurses into plain lists to thaw nested frozen values.

        Symmetry test: thaw must be total like freeze. This tests the case where
        a plain list wraps frozen values. The natural shape in Task 4/5 (replay,
        result gate, CLI) is to build a plain dict/list of fields, thaw it, then
        json.dumps it; that fails if thaw is partial.
        """
        # Build a plain list containing frozen values
        frozen_inner1 = qc_lib.freeze({"key": "value"})
        frozen_inner2 = (1, 2, 3)  # Already-frozen tuple
        plain_list_with_frozen = [frozen_inner1, frozen_inner2]

        # thaw must recurse into the plain list and thaw the nested frozen values
        thawed = qc_lib.thaw(plain_list_with_frozen)

        # The result must be fully plain
        self.assertIsInstance(thawed, list)
        self.assertIsInstance(thawed[0], dict)
        self.assertIsInstance(thawed[1], list)

        # JSON serialisation must succeed
        json_str = json.dumps(thawed)
        self.assertIsInstance(json_str, str)
        recovered = json.loads(json_str)
        self.assertEqual(recovered, [{"key": "value"}, [1, 2, 3]])


class FreezeThawRoundTripTest(unittest.TestCase):
    def test_round_trip_simple_dict(self):
        """Test that freeze/thaw preserves a simple dict."""
        original = {"a": 1, "b": "hello", "c": None}
        frozen = qc_lib.freeze(original)
        thawed = qc_lib.thaw(frozen)
        self.assertEqual(thawed, original)

    def test_round_trip_simple_list(self):
        """Test that freeze/thaw preserves a simple list."""
        original = [1, "hello", None, 3.14]
        frozen = qc_lib.freeze(original)
        thawed = qc_lib.thaw(frozen)
        self.assertEqual(thawed, original)

    def test_round_trip_complex_nested_structure(self):
        """Test that freeze/thaw preserves a complex nested structure."""
        original = {
            "tasks": [
                {"id": "task_1", "subtasks": [{"id": "sub_1", "done": True}]},
                {"id": "task_2", "metadata": {"priority": "high"}},
            ],
            "metadata": {
                "version": 1,
                "tags": ["important", "urgent"],
                "nested": {"deep": {"value": "test"}},
            },
        }
        frozen = qc_lib.freeze(original)
        thawed = qc_lib.thaw(frozen)
        self.assertEqual(thawed, original)

    def test_round_trip_with_empty_containers(self):
        """Test that freeze/thaw preserves empty containers."""
        original = {"empty_dict": {}, "empty_list": [], "nested_empty": {"inner": []}}
        frozen = qc_lib.freeze(original)
        thawed = qc_lib.thaw(frozen)
        self.assertEqual(thawed, original)

    def test_round_trip_with_various_primitives(self):
        """Test that freeze/thaw preserves various primitive types."""
        original = {
            "int": 42,
            "float": 3.14,
            "string": "hello",
            "bool_true": True,
            "bool_false": False,
            "none": None,
            "list": [1, "two", 3.0, True, None],
        }
        frozen = qc_lib.freeze(original)
        thawed = qc_lib.thaw(frozen)
        self.assertEqual(thawed, original)


if __name__ == "__main__":
    unittest.main()
