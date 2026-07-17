import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from qc_lib import Blocked

import apply_upgrade
import discover_structure
import render_upgrade
import upgrade_state


class UpgradeScriptTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmp.name)
        self.mechanism = self.workspace / "orchestration"
        self.mechanism.mkdir()
        self.workflow = self.mechanism / "workflow.md"
        self.workflow.write_text("before workflow\n", encoding="utf-8")
        self.state_dir = self.workspace / ".orchestration-qc" / "state"
        self.state_dir.mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _manifest(self) -> dict:
        return discover_structure.discover(self.workspace, "orchestration")

    def _proposal(
        self,
        *,
        apply_mode: str = "side-by-side",
        output_root: str = "orchestration-v2",
        documentation_path: str = "orchestration-v2/ARCHITECTURE.md",
        content: str = "# Architecture\n",
        workflow_content: str | None = None,
    ) -> dict:
        actions = [
            {
                "action": "create",
                "path": documentation_path,
                "content": content,
                "rationale": "document the proposed architecture",
                "trace_ids": ["doc-1"],
            },
            {
                "action": "create",
                "path": f"{output_root}/workflow.md",
                "content": workflow_content or "after workflow\n",
                "rationale": "apply template workflow structure",
                "trace_ids": ["gap-1"],
            },
        ]
        return {"actions": actions}

    def _create_checkpoint(self, run_id: str = "upgrade-run") -> Path:
        manifest = self._manifest()
        proposal = self._proposal()
        rendered = render_upgrade.validate_proposal(
            self.workspace,
            manifest,
            proposal,
            template_id="portable-single-agent",
            apply_mode="side-by-side",
            output_root="orchestration-v2",
            documentation_path="orchestration-v2/ARCHITECTURE.md",
            isolation_reason=None,
        )
        checkpoint = {
            "schema_version": 3,
            "run_type": "upgrade",
            "run_id": run_id,
            "status": "pending_approval",
            "mechanism_path": "orchestration",
            "targets": sorted({entry["path"] for entry in manifest["candidates"]} | {entry["path"] for entry in rendered["actions"]}),
            "profile": "core",
            "language": "en",
            "template_id": "portable-single-agent",
            "template_version": 1,
            "apply_mode": "side-by-side",
            "output_root": "orchestration-v2",
            "documentation_path": "orchestration-v2/ARCHITECTURE.md",
            "isolation_reason": None,
            "manifest": manifest,
            "findings": [],
            "template_gaps": [],
            "actions": rendered["actions"],
            "plain_language_report": "upgrade report",
            "preview": rendered["preview"],
            "created_at": "1970-01-01T00:00:00Z",
        }
        path = self.state_dir / f"checkpoint-{run_id}.json"
        path.write_text(json.dumps(checkpoint, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    def test_discover_structure_returns_manifest_with_hashes(self):
        manifest = self._manifest()
        self.assertEqual(manifest["mechanism_path"], "orchestration")
        self.assertEqual(manifest["candidate_count"], 1)
        self.assertEqual(manifest["candidates"][0]["path"], "orchestration/workflow.md")
        self.assertEqual(
            manifest["candidates"][0]["sha256"],
            hashlib.sha256(b"before workflow\n").hexdigest(),
        )

    def test_discover_structure_blocks_missing_target(self):
        with self.assertRaises(Blocked) as ctx:
            discover_structure.discover(self.workspace, "missing")
        self.assertEqual(ctx.exception.reason_code, "missing_target")

    def test_discover_structure_blocks_path_escape(self):
        with self.assertRaises(Blocked) as ctx:
            discover_structure.discover(self.workspace, "../outside")
        self.assertEqual(ctx.exception.reason_code, "target_outside_approved_set")

    def test_render_upgrade_requires_isolation_reason_for_isolated_template(self):
        manifest = self._manifest()
        proposal = self._proposal()
        with self.assertRaises(Blocked) as ctx:
            render_upgrade.validate_proposal(
                self.workspace,
                manifest,
                proposal,
                template_id="isolated-three-agent",
                apply_mode="side-by-side",
                output_root="orchestration-v2",
                documentation_path="orchestration-v2/ARCHITECTURE.md",
                isolation_reason=None,
            )
        self.assertEqual(ctx.exception.reason_code, "invalid_template")

    def test_render_upgrade_accepts_isolated_template_with_reason(self):
        manifest = self._manifest()
        proposal = self._proposal()
        rendered = render_upgrade.validate_proposal(
            self.workspace,
            manifest,
            proposal,
            template_id="isolated-three-agent",
            apply_mode="side-by-side",
            output_root="orchestration-v2",
            documentation_path="orchestration-v2/ARCHITECTURE.md",
            isolation_reason="separate tool grants required",
        )
        self.assertTrue(rendered["actions"])

    def test_render_upgrade_blocks_side_by_side_action_outside_output_root(self):
        manifest = self._manifest()
        proposal = self._proposal()
        proposal["actions"][1]["path"] = "elsewhere/workflow.md"
        with self.assertRaises(Blocked) as ctx:
            render_upgrade.validate_proposal(
                self.workspace,
                manifest,
                proposal,
                template_id="portable-single-agent",
                apply_mode="side-by-side",
                output_root="orchestration-v2",
                documentation_path="orchestration-v2/ARCHITECTURE.md",
                isolation_reason=None,
            )
        self.assertEqual(ctx.exception.reason_code, "target_outside_approved_set")

    def test_render_upgrade_blocks_in_place_create_outside_documentation_path(self):
        manifest = self._manifest()
        proposal = {
            "actions": [
                {
                    "action": "create",
                    "path": "orchestration/ARCHITECTURE.md",
                    "content": "# Architecture\n",
                    "rationale": "document the proposed architecture",
                    "trace_ids": ["doc-1"],
                },
                {
                    "action": "create",
                    "path": "orchestration/extra.md",
                    "content": "not allowed\n",
                    "rationale": "extra file",
                    "trace_ids": ["gap-1"],
                },
            ]
        }
        with self.assertRaises(Blocked) as ctx:
            render_upgrade.validate_proposal(
                self.workspace,
                manifest,
                proposal,
                template_id="portable-single-agent",
                apply_mode="in-place",
                output_root=None,
                documentation_path="orchestration/ARCHITECTURE.md",
                isolation_reason=None,
            )
        self.assertEqual(ctx.exception.reason_code, "target_outside_approved_set")

    def test_render_upgrade_blocks_stale_source_hash(self):
        manifest = self._manifest()
        proposal = {
            "actions": [
                {
                    "action": "create",
                    "path": "orchestration/ARCHITECTURE.md",
                    "content": "# Architecture\n",
                    "rationale": "document the proposed architecture",
                    "trace_ids": ["doc-1"],
                },
                {
                    "action": "update",
                    "path": "orchestration/workflow.md",
                    "content": "after workflow\n",
                    "source_sha256": "0" * 64,
                    "rationale": "normalize workflow",
                    "trace_ids": ["finding-1"],
                },
            ]
        }
        with self.assertRaises(Blocked) as ctx:
            render_upgrade.validate_proposal(
                self.workspace,
                manifest,
                proposal,
                template_id="portable-single-agent",
                apply_mode="in-place",
                output_root=None,
                documentation_path="orchestration/ARCHITECTURE.md",
                isolation_reason=None,
            )
        self.assertEqual(ctx.exception.reason_code, "stale_target")

    def test_render_upgrade_blocks_destination_collision(self):
        manifest = self._manifest()
        proposal = self._proposal()
        (self.workspace / "orchestration-v2").mkdir()
        with self.assertRaises(Blocked) as ctx:
            render_upgrade.validate_proposal(
                self.workspace,
                manifest,
                proposal,
                template_id="portable-single-agent",
                apply_mode="side-by-side",
                output_root="orchestration-v2",
                documentation_path="orchestration-v2/ARCHITECTURE.md",
                isolation_reason=None,
            )
        self.assertEqual(ctx.exception.reason_code, "destination_exists")

    def test_upgrade_state_create_blocks_concurrent_pending_run(self):
        qc_checkpoint = self.state_dir / "checkpoint-qc-run.json"
        qc_checkpoint.write_text(
            json.dumps({"status": "pending_approval", "run_id": "qc-run"}),
            encoding="utf-8",
        )
        manifest = self._manifest()
        args = mock.Mock(
            workspace=str(self.workspace),
            state_dir=str(self.state_dir),
            run_id="upgrade-run",
            profile="core",
            language="en",
            template_id="portable-single-agent",
            apply_mode="side-by-side",
            output_root="orchestration-v2",
            documentation_path="orchestration-v2/ARCHITECTURE.md",
            isolation_reason=None,
            manifest_json=self._write_json(manifest),
            findings_json=self._write_json([]),
            gaps_json=self._write_json([]),
            proposal_json=self._write_json(self._proposal()),
            report=self._write_text("upgrade report"),
        )
        with self.assertRaises(Blocked) as ctx:
            upgrade_state.create(args)
        self.assertEqual(ctx.exception.reason_code, "concurrent_run_active")

    def test_upgrade_state_decide_decline_aborts_checkpoint(self):
        path = self._create_checkpoint()
        result = upgrade_state.decide(path, "decline")
        self.assertEqual(result["status"], "aborted")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "aborted")

    def test_upgrade_state_decide_approve_records_approval(self):
        path = self._create_checkpoint()
        result = upgrade_state.decide(path, "approve")
        self.assertEqual(result["status"], "pending_approval")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["approval"]["decision"], "approve")

    def test_apply_upgrade_consumes_approved_checkpoint(self):
        path = self._create_checkpoint()
        upgrade_state.decide(path, "approve")
        result = apply_upgrade.apply(self.workspace, path)
        self.assertEqual(result["status"], "consumed")
        created = self.workspace / "orchestration-v2" / "workflow.md"
        self.assertTrue(created.is_file())
        self.assertEqual(created.read_text(encoding="utf-8"), "after workflow\n")
        payload = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(payload["status"], "consumed")

    def test_apply_upgrade_blocks_without_approval(self):
        path = self._create_checkpoint()
        with self.assertRaises(Blocked) as ctx:
            apply_upgrade.apply(self.workspace, path)
        self.assertEqual(ctx.exception.reason_code, "invalid_decision")

    def test_apply_upgrade_rolls_back_on_failure(self):
        path = self._create_checkpoint()
        upgrade_state.decide(path, "approve")
        original = self.workflow.read_text(encoding="utf-8")
        calls = {"count": 0}

        def flaky_atomic(destination: Path, data: bytes) -> None:
            calls["count"] += 1
            if calls["count"] == 2:
                raise OSError("simulated failure")
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)

        with mock.patch.object(apply_upgrade, "_atomic_bytes", side_effect=flaky_atomic):
            with self.assertRaises(Blocked) as ctx:
                apply_upgrade.apply(self.workspace, path)
        self.assertEqual(ctx.exception.reason_code, "capability_insufficient")
        self.assertEqual(self.workflow.read_text(encoding="utf-8"), original)
        self.assertFalse((self.workspace / "orchestration-v2").exists())

    def test_upgrade_state_verify_persists_record(self):
        path = self._create_checkpoint("verify-run")
        upgrade_state.decide(path, "approve")
        apply_upgrade.apply(self.workspace, path)
        findings_path = self._write_json([{"id": "finding-1"}])
        gaps_path = self._write_json([])
        report_path = self._write_text("verification report")
        result = upgrade_state.verify(path, Path(findings_path), Path(gaps_path), Path(report_path))
        self.assertEqual(result["status"], "failed")
        verification = json.loads(Path(result["verification_path"]).read_text(encoding="utf-8"))
        self.assertEqual(verification["run_id"], "verify-run")
        self.assertEqual(verification["report"], "verification report")

    def _write_json(self, payload) -> str:
        handle = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        json.dump(payload, handle)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name

    def _write_text(self, text: str) -> str:
        handle = tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8")
        handle.write(text)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        return handle.name


if __name__ == "__main__":
    unittest.main()
