import unittest

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


if __name__ == "__main__":
    unittest.main()
