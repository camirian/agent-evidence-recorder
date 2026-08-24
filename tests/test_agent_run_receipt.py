"""Regression tests for synthetic agent run receipts."""

from __future__ import annotations

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agent_evidence_recorder.agent_run_receipt import (
    DEFAULT_RECEIPT_DIR,
    read_json,
    score_receipt,
    verify_receipt,
    verify_receipts,
    write_json,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class AgentRunReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path(tempfile.mkdtemp(prefix="agent_evidence-agent-receipt-test-"))
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))
        self.receipt_dir = self.temp_root / "receipts"
        shutil.copytree(REPO_ROOT / DEFAULT_RECEIPT_DIR, self.receipt_dir)

    def test_tracked_receipts_verify(self) -> None:
        report = verify_receipts(REPO_ROOT / DEFAULT_RECEIPT_DIR)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["receipt_count"], 3)

    def test_score_is_deterministic(self) -> None:
        receipt = read_json(self.receipt_dir / "agent-run-receipt.codex.json")
        first = score_receipt(receipt)
        second = score_receipt(copy.deepcopy(receipt))
        self.assertEqual(first, second)
        self.assertEqual(first["token_efficiency_score"], 100.0)
        self.assertEqual(first["verified_output_per_1m_tokens"], 5600.0)

    def test_missing_required_field_fails(self) -> None:
        path = self.receipt_dir / "agent-run-receipt.codex.json"
        receipt = read_json(path)
        receipt.pop("prompt_body_policy")
        write_json(path, receipt)

        report = verify_receipt(path)
        self.assertFalse(report["passed"], report)
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("required_fields_present", failed)

    def test_unknown_verification_stays_low_score(self) -> None:
        path = self.receipt_dir / "agent-run-receipt.unverified.json"
        report = verify_receipt(path)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["score"]["token_efficiency_score"], 14.0)
        self.assertEqual(report["score"]["verified_output_per_1m_tokens"], 0.0)

    def test_noop_run_is_penalized(self) -> None:
        path = self.receipt_dir / "agent-run-receipt.noop.json"
        report = verify_receipt(path)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["score"]["token_efficiency_score"], 0.0)
        self.assertIn("no_verified_change", report["score"]["score_breakdown"]["waste_flags"])

    def test_missing_reference_fails(self) -> None:
        path = self.receipt_dir / "agent-run-receipt.codex.json"
        receipt = read_json(path)
        receipt["evidence_packet_ref"] = "missing-evidence.md"
        write_json(path, receipt)

        report = verify_receipt(path)
        self.assertFalse(report["passed"], report)
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("artifact_refs_exist_and_are_relative", failed)

    def test_prompt_body_policy_is_enforced(self) -> None:
        path = self.receipt_dir / "agent-run-receipt.codex.json"
        receipt = read_json(path)
        receipt["prompt_body_policy"] = "stored"
        write_json(path, receipt)

        report = verify_receipt(path)
        self.assertFalse(report["passed"], report)
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("prompt_body_excluded", failed)

    def test_private_surface_marker_fails(self) -> None:
        path = self.receipt_dir / "agent-run-receipt.codex.json"
        receipt = read_json(path)
        receipt["task_summary"] = "Synthetic run accidentally records " + "/" + "home" + "/example/path."
        write_json(path, receipt)

        report = verify_receipt(path)
        self.assertFalse(report["passed"], report)
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("public_surface_markers_absent", failed)

    def test_score_mismatch_fails(self) -> None:
        path = self.receipt_dir / "agent-run-receipt.codex.json"
        receipt = read_json(path)
        receipt["token_efficiency_score"] = 1.0
        write_json(path, receipt)

        report = verify_receipt(path)
        self.assertFalse(report["passed"], report)
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("score_matches_deterministic_scorer", failed)


if __name__ == "__main__":
    unittest.main()
