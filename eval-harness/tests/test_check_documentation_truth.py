"""Tests for check_documentation_truth.

Validates that references to unbuilt components are detected when they appear
in scanned documentation.
"""
import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import check_documentation_truth as doctruth  # noqa: E402


def make_scanned_tree(root: Path, *, readme: str = "", oqc_readme: str = "", skill_md: str = "") -> None:
    """Create a standard scanned document tree in the given root."""
    root.joinpath("README.md").write_text(readme, encoding="utf-8")
    oqc_dir = root / "orchestration-quality-control"
    oqc_dir.mkdir(parents=True, exist_ok=True)
    oqc_dir.joinpath("README.md").write_text(oqc_readme, encoding="utf-8")
    oqc_dir.joinpath("SKILL.md").write_text(skill_md, encoding="utf-8")


class AbsentTargetFailsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_scanned_tree(self.root, skill_md="Reference to oqc.py here.\n")

    def test_absent_target_produces_finding(self):
        findings = doctruth.find_untrue_claims(self.root)
        self.assertEqual(
            findings,
            ["orchestration-quality-control/SKILL.md:scripts/oqc.py:missing-target"],
        )

    def test_main_returns_1_for_findings(self):
        captured_stdout = io.StringIO()
        with contextlib.redirect_stdout(captured_stdout):
            exit_code = doctruth.main([str(self.root)])
        self.assertEqual(exit_code, 1)
        self.assertEqual(
            captured_stdout.getvalue(),
            "orchestration-quality-control/SKILL.md:scripts/oqc.py:missing-target\n",
        )

class CreatingTargetPassesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_scanned_tree(self.root, skill_md="Reference to oqc.py here.\n")

    def test_creating_target_clears_finding(self):
        # First, verify there's a finding
        findings_before = doctruth.find_untrue_claims(self.root)
        self.assertEqual(len(findings_before), 1)

        # Create the target
        scripts_dir = self.root / "orchestration-quality-control" / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "oqc.py").write_text("# oqc module\n", encoding="utf-8")

        # Now should be clean
        findings_after = doctruth.find_untrue_claims(self.root)
        self.assertEqual(findings_after, [])

    def test_main_returns_0_when_all_targets_exist(self):
        scripts_dir = self.root / "orchestration-quality-control" / "scripts"
        scripts_dir.mkdir()
        (scripts_dir / "oqc.py").write_text("# oqc module\n", encoding="utf-8")

        exit_code = doctruth.main([str(self.root)])
        self.assertEqual(exit_code, 0)

class UnscannedProseTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_scanned_tree(self.root)

        # Create unscanned contributor material that mentions all five targets
        ai_codex = self.root / "AI_Codex" / "Architecture" / "ADR"
        ai_codex.mkdir(parents=True)
        (ai_codex / "0014-example.md").write_text(
            "Mentions oqc.py, mailbox.py, compile_prompt.py, gate.py, "
            "and envelope.schema.json\n",
            encoding="utf-8",
        )

        docs = self.root / "docs"
        docs.mkdir()
        (docs / "some-review.md").write_text(
            "Also mentions scripts/oqc.py, scripts/mailbox.py, "
            "scripts/compile_prompt.py, scripts/gate.py, "
            "and schemas/envelope.schema.json\n",
            encoding="utf-8",
        )

    def test_unscanned_paths_do_not_produce_findings(self):
        findings = doctruth.find_untrue_claims(self.root)
        self.assertEqual(findings, [])

class StableSortedOrderTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_scanned_tree(
            self.root,
            readme="Contains oqc.py and mailbox.py and compile_prompt.py\n",
            oqc_readme="Mentions gate.py and then compile_prompt.py again\n",
            skill_md="References envelope.schema.json and oqc.py\n",
        )

    def test_findings_in_sorted_order(self):
        findings = doctruth.find_untrue_claims(self.root)

        # Expected order: sorted by (document, token)
        expected = [
            "README.md:scripts/compile_prompt.py:missing-target",
            "README.md:scripts/mailbox.py:missing-target",
            "README.md:scripts/oqc.py:missing-target",
            "orchestration-quality-control/README.md:scripts/compile_prompt.py:missing-target",
            "orchestration-quality-control/README.md:scripts/gate.py:missing-target",
            "orchestration-quality-control/SKILL.md:schemas/envelope.schema.json:missing-target",
            "orchestration-quality-control/SKILL.md:scripts/oqc.py:missing-target",
        ]
        self.assertEqual(findings, expected)

    def test_duplicate_findings_deduped(self):
        findings = doctruth.find_untrue_claims(self.root)
        # Count how many times "README.md:scripts/oqc.py:missing-target" appears
        count = findings.count("README.md:scripts/oqc.py:missing-target")
        self.assertEqual(count, 1, "Each (document, token) pair should appear exactly once")

class RealDuplicateDedupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_scanned_tree(
            self.root,
            skill_md=(
                "First we use oqc.py for processing. "
                "Later, scripts/oqc.py is referenced again. "
                "And oqc.py appears once more.\n"
            ),
        )

    def test_real_duplicate_content_deduped(self):
        findings = doctruth.find_untrue_claims(self.root)
        # All three references should dedup to exactly one finding
        expected = ["orchestration-quality-control/SKILL.md:scripts/oqc.py:missing-target"]
        self.assertEqual(findings, expected)

class WholeTokenMatchingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_scanned_tree(
            self.root,
            skill_md="Module investigate.py and subgate.py are mentioned.\n",
        )

    def test_substring_not_matched(self):
        findings = doctruth.find_untrue_claims(self.root)
        # Should be empty - investigate.py doesn't match gate.py, subgate.py doesn't match gate.py
        self.assertEqual(findings, [])

class RealCheckoutPassesTest(unittest.TestCase):
    def test_real_repository_passes(self):
        repo_root = Path(__file__).resolve().parents[2]
        findings = doctruth.find_untrue_claims(repo_root)
        self.assertEqual(
            findings,
            [],
            f"Real checkout should have no findings, but found: {findings}",
        )

class NonAsciiEncodingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_scanned_tree(
            self.root,
            skill_md="The oqc.py module — critical for orchestration — handles state.\n",
        )

    def test_non_ascii_characters_handled(self):
        findings = doctruth.find_untrue_claims(self.root)
        # Should find the oqc.py reference even with em dash in the text
        expected = ["orchestration-quality-control/SKILL.md:scripts/oqc.py:missing-target"]
        self.assertEqual(findings, expected)

class NonAsciiEncodingHostileLocaleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        make_scanned_tree(
            self.root,
            skill_md="The oqc.py module — critical for orchestration — handles state.\n",
        )

    def test_non_ascii_with_hostile_locale(self):
        """Verify UTF-8 encoding argument is actually needed, not just luck."""
        # Build hostile environment that forces ASCII codec
        hostile_env = os.environ.copy()
        hostile_env["LC_ALL"] = "C"
        hostile_env["LANG"] = "C"
        hostile_env["PYTHONUTF8"] = "0"
        hostile_env["PYTHONCOERCECLOCALE"] = "0"
        # Remove PYTHONIOENCODING if present
        hostile_env.pop("PYTHONIOENCODING", None)

        # Get checker path from the module under test
        checker_path = Path(doctruth.__file__)

        # Run checker as subprocess with hostile locale
        result = subprocess.run(
            [sys.executable, str(checker_path), str(self.root)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=hostile_env,
            timeout=30,
        )

        # If encoding="utf-8" is missing, this would crash with UnicodeDecodeError
        # Success means: exit code 1 (found finding), expected output, no crash
        self.assertEqual(
            result.returncode,
            1,
            f"Expected exit 1 (finding), got {result.returncode}. "
            f"stderr: {result.stderr}",
        )
        self.assertIn(
            "orchestration-quality-control/SKILL.md:scripts/oqc.py:missing-target",
            result.stdout,
        )
        self.assertNotIn("UnicodeDecodeError", result.stderr)

class VerifyAllCoreTargetPathsTest(unittest.TestCase):
    """Ensure all CORE_TARGETS entries have correct target paths."""

    def test_all_target_paths_produce_and_clear_findings(self):
        """Verify each target path correctly gates findings via creation and clearing.

        For each token in CORE_TARGETS, creates a temp tree where SKILL.md names
        the token, verifies a finding fires, creates the file at target_path,
        and verifies the finding clears. If the target_path is typo'd, the
        finding will not clear after creating the file at the typo'd location.
        """
        # Hardcode expected paths so we can detect typos
        expected_paths = {
            "scripts/oqc.py": "orchestration-quality-control/scripts/oqc.py",
            "scripts/mailbox.py": "orchestration-quality-control/scripts/mailbox.py",
            "scripts/compile_prompt.py": "orchestration-quality-control/scripts/compile_prompt.py",
            "scripts/gate.py": "orchestration-quality-control/scripts/gate.py",
            "schemas/envelope.schema.json": "orchestration-quality-control/schemas/envelope.schema.json",
        }

        for token, (spellings, target_path_str) in doctruth.CORE_TARGETS.items():
            with self.subTest(token=token):
                # First, verify the target path in CORE_TARGETS matches what we expect
                expected = expected_paths[token]
                self.assertEqual(
                    target_path_str,
                    expected,
                    f"Target path for {token} is {target_path_str}, expected {expected}. "
                    f"This looks like a typo in CORE_TARGETS.",
                )

                # Now test the finding behavior
                tmp = tempfile.TemporaryDirectory()
                self.addCleanup(tmp.cleanup)
                root = Path(tmp.name)
                make_scanned_tree(root, skill_md=f"Reference to {spellings[0]} here.\n")

                # Before creating target, should have finding
                findings_before = doctruth.find_untrue_claims(root)
                self.assertEqual(len(findings_before), 1)
                self.assertIn(f":{token}:missing-target", findings_before[0])

                # Create target and verify finding clears
                target_path = root / target_path_str
                target_path.parent.mkdir(parents=True, exist_ok=True)
                target_path.write_text(f"# {token}\n", encoding="utf-8")

                findings_after = doctruth.find_untrue_claims(root)
                self.assertEqual(
                    findings_after,
                    [],
                    f"Finding did not clear after creating {target_path_str} for {token}",
                )


class RegexBoundaryTest(unittest.TestCase):
    """Test the regex word-boundary matching."""

    def test_dotted_suffixes_not_matched(self):
        """Verify that gate.py.bak and gate.py.orig do not produce findings."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        make_scanned_tree(
            root,
            skill_md="The stray gate.py.bak backup and gate.py.orig old version.\n",
        )

        findings = doctruth.find_untrue_claims(root)
        self.assertEqual(
            findings,
            [],
            "gate.py.bak and gate.py.orig should not match gate.py",
        )

    def test_sentence_ending_period_still_matches(self):
        """Verify period after .py still matches when not followed by word char."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        make_scanned_tree(
            root,
            skill_md="Run scripts/oqc.py.",
        )

        findings = doctruth.find_untrue_claims(root)
        self.assertEqual(
            findings,
            ["orchestration-quality-control/SKILL.md:scripts/oqc.py:missing-target"],
            "Period not followed by word char should still match",
        )


class MissingScannedDocumentTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

        # Create only two of three scanned documents (missing README.md in root)
        oqc_dir = self.root / "orchestration-quality-control"
        oqc_dir.mkdir()
        oqc_dir.joinpath("README.md").write_text("", encoding="utf-8")
        oqc_dir.joinpath("SKILL.md").write_text("", encoding="utf-8")

    def test_missing_document_raises_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            doctruth.find_untrue_claims(self.root)

    def test_main_returns_2_for_missing_document(self):
        captured_stderr = io.StringIO()
        with contextlib.redirect_stderr(captured_stderr):
            exit_code = doctruth.main([str(self.root)])
        self.assertEqual(exit_code, 2)
        self.assertIn("README.md", captured_stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
