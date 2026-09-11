import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import measure_run as run_mod  # noqa: E402


class MailboxPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        self.package_root = Path(self.tmp.name) / "package"
        self.package_root.mkdir()

    def test_mailbox_with_envelopes_and_prompts(self):
        mail_dir = self.run_dir / "sandbox" / ".orchestration-qc" / "mail" / "test_run_id"
        mail_dir.mkdir(parents=True)

        envelopes_content = (
            json.dumps({"from": {"role": "orchestrator"}, "inputs": {"paths": ["file1.txt", "file2.txt"]}}) + "\n"
            + json.dumps({"from": {"role": "validator"}, "inputs": {"paths": ["file3.txt"]}}) + "\n"
        )
        events_file = mail_dir / "events.jsonl"
        events_file.write_text(envelopes_content)

        prompt1 = mail_dir / "0001-orchestrator.prompt.md"
        prompt1.write_text("prompt content 1")

        prompt2 = mail_dir / "0002-validator.prompt.md"
        prompt2.write_text("prompt content 2")

        metrics = run_mod.measure(self.run_dir, self.package_root)

        self.assertTrue(metrics.mailbox_present)
        self.assertEqual(metrics.files_read_per_role, {"orchestrator": 2, "validator": 1})
        self.assertEqual(metrics.files_read_total, 3)
        self.assertEqual(len(metrics.envelope_bytes), 2)
        self.assertEqual(metrics.max_envelope_bytes, max(metrics.envelope_bytes))
        self.assertEqual(metrics.prompt_bytes, (len(prompt1.read_bytes()), len(prompt2.read_bytes())))
        self.assertEqual(metrics.max_prompt_bytes, max(metrics.prompt_bytes))

    def test_transcript_fallback_with_packaged_and_unpacked(self):
        transcript_dir = self.run_dir / "outputs"
        transcript_dir.mkdir(parents=True)

        packaged_file = self.package_root / "references" / "test.md"
        packaged_file.parent.mkdir(parents=True)
        packaged_file.write_text("packaged")

        transcript_content = """# Transcript

## Files read

- run_config.json
- references/test.md
- sandbox/fixture.md
- some/nonexistent/file.md
- references/test.md (with a note)

## Next section

Some other content
"""
        transcript_file = transcript_dir / "transcript.md"
        transcript_file.write_text(transcript_content)

        metrics = run_mod.measure(self.run_dir, self.package_root)

        self.assertFalse(metrics.mailbox_present)
        self.assertEqual(metrics.files_read_per_role, {"run": 2})
        self.assertEqual(metrics.files_read_total, 2)
        self.assertEqual(metrics.envelope_bytes, tuple())
        self.assertEqual(metrics.max_envelope_bytes, 0)
        self.assertEqual(metrics.prompt_bytes, tuple())
        self.assertEqual(metrics.max_prompt_bytes, 0)

    def test_no_transcript_no_mailbox_yields_zero(self):
        metrics = run_mod.measure(self.run_dir, self.package_root)

        self.assertFalse(metrics.mailbox_present)
        self.assertEqual(metrics.files_read_per_role, {"run": 0})
        self.assertEqual(metrics.files_read_total, 0)
        self.assertEqual(metrics.envelope_bytes, tuple())
        self.assertEqual(metrics.max_envelope_bytes, 0)
        self.assertEqual(metrics.prompt_bytes, tuple())
        self.assertEqual(metrics.max_prompt_bytes, 0)

    def test_state_files_and_paths_count_recursively(self):
        state_dir = self.run_dir / "sandbox" / ".orchestration-qc" / "state"
        state_dir.mkdir(parents=True)

        (state_dir / "file1.json").write_text("{}")
        (state_dir / "subdir").mkdir()
        (state_dir / "subdir" / "file2.json").write_text("{}")
        (state_dir / "subdir" / "deep").mkdir()
        (state_dir / "subdir" / "deep" / "file3.json").write_text("{}")

        metrics = run_mod.measure(self.run_dir, self.package_root)

        self.assertEqual(metrics.state_files, 3)
        self.assertEqual(len(metrics.state_paths), 3)
        self.assertIn(".orchestration-qc/state/file1.json", metrics.state_paths)
        self.assertIn(".orchestration-qc/state/subdir/file2.json", metrics.state_paths)
        self.assertIn(".orchestration-qc/state/subdir/deep/file3.json", metrics.state_paths)

    def test_verify_unavailable_when_oqc_script_missing(self):
        metrics = run_mod.measure(self.run_dir, self.package_root)

        self.assertEqual(metrics.verify, "unavailable")

    def test_missing_run_directory_returns_1(self):
        nonexistent = Path(self.tmp.name) / "nonexistent"

        result = run_mod.main([str(nonexistent), "--package-root", str(self.package_root)])

        self.assertEqual(result, 1)

    def test_json_output_is_valid(self):
        transcript_dir = self.run_dir / "outputs"
        transcript_dir.mkdir(parents=True)
        (transcript_dir / "transcript.md").write_text("# Transcript\n\n## Files read\n\n- file.md\n\n## Next\n")

        stdout_capture = io.StringIO()
        with contextlib.redirect_stdout(stdout_capture):
            result = run_mod.main([str(self.run_dir), "--package-root", str(self.package_root), "--json"])

        self.assertEqual(result, 0)
        output = stdout_capture.getvalue()
        parsed = json.loads(output)

        self.assertIn("mailbox_present", parsed)
        self.assertIn("files_read_per_role", parsed)
        self.assertIn("files_read_total", parsed)
        self.assertIn("state_files", parsed)
        self.assertIn("state_paths", parsed)
        self.assertIn("envelope_bytes", parsed)
        self.assertIn("max_envelope_bytes", parsed)
        self.assertIn("prompt_bytes", parsed)
        self.assertIn("max_prompt_bytes", parsed)
        self.assertIn("verify", parsed)


class OrchestratorQualityControlPrefixTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        self.package_root = Path(self.tmp.name) / "package"
        self.package_root.mkdir()

    def test_strips_orchestration_quality_control_prefix(self):
        transcript_dir = self.run_dir / "outputs"
        transcript_dir.mkdir(parents=True)

        packaged_file = self.package_root / "SKILL.md"
        packaged_file.write_text("skill")

        transcript_content = """# Transcript

## Files read

- orchestration-quality-control/SKILL.md

## Next

Content
"""
        transcript_file = transcript_dir / "transcript.md"
        transcript_file.write_text(transcript_content)

        metrics = run_mod.measure(self.run_dir, self.package_root)

        self.assertEqual(metrics.files_read_per_role, {"run": 1})


class TrailingParenthesisTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        self.package_root = Path(self.tmp.name) / "package"
        self.package_root.mkdir()

    def test_strips_trailing_parenthetical_note(self):
        transcript_dir = self.run_dir / "outputs"
        transcript_dir.mkdir(parents=True)

        packaged_file = self.package_root / "test.md"
        packaged_file.write_text("test")

        transcript_content = """# Transcript

## Files read

- test.md (some note; fixture not edited)

## Next

Content
"""
        transcript_file = transcript_dir / "transcript.md"
        transcript_file.write_text(transcript_content)

        metrics = run_mod.measure(self.run_dir, self.package_root)

        self.assertEqual(metrics.files_read_per_role, {"run": 1})


class LongPathEntryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        self.run_dir.mkdir()
        self.package_root = Path(self.tmp.name) / "package"
        self.package_root.mkdir()

    def test_long_entry_over_255_bytes_does_not_crash(self):
        transcript_dir = self.run_dir / "outputs"
        transcript_dir.mkdir(parents=True)

        long_entry = "a" * 300
        transcript_content = f"""# Transcript

## Files read

- {long_entry}
- SKILL.md

## Next

Content
"""
        transcript_file = transcript_dir / "transcript.md"
        transcript_file.write_text(transcript_content)

        packaged_file = self.package_root / "SKILL.md"
        packaged_file.write_text("skill")

        metrics = run_mod.measure(self.run_dir, self.package_root)

        self.assertEqual(metrics.files_read_per_role, {"run": 1})


class RenderTableTest(unittest.TestCase):
    def test_render_table_includes_all_fields(self):
        metrics = run_mod.RunMetrics(
            mailbox_present=True,
            files_read_per_role={"orchestrator": 5, "validator": 3},
            files_read_total=8,
            state_files=4,
            state_paths=("path1", "path2", "path3", "path4"),
            envelope_bytes=(100, 200, 150),
            max_envelope_bytes=200,
            prompt_bytes=(300, 400),
            max_prompt_bytes=400,
            verify="pass",
        )

        table = run_mod.render_table(metrics)

        self.assertIn("mailbox_present", table)
        self.assertIn("files_read_per_role", table)
        self.assertIn("files_read_total", table)
        self.assertIn("state_files", table)
        self.assertIn("state_paths", table)
        self.assertIn("envelope_bytes", table)
        self.assertIn("max_envelope_bytes", table)
        self.assertIn("prompt_bytes", table)
        self.assertIn("max_prompt_bytes", table)
        self.assertIn("verify", table)


if __name__ == "__main__":
    unittest.main()
