"""Regression tests for release boundary checks."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agent_evidence_recorder.release_boundary import check_release_boundary


class ReleaseBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path(tempfile.mkdtemp(prefix="agent_evidence-release-boundary-"))
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))

    def write(self, relative_path: str, text: str = "public-safe synthetic source\n") -> Path:
        path = self.temp_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_accepts_public_safe_source_candidate(self) -> None:
        self.write("README.md", "Synthetic-only local sample. No package publishing from this candidate.\n")
        self.write("pyproject.toml", "[project]\nname = \"agent_evidence-recorder\"\n")
        self.write("agent_evidence_recorder/__init__.py", "\"\"\"Public-safe source package.\"\"\"\n")

        report = check_release_boundary(self.temp_root)

        self.assertTrue(report["passed"], report)
        self.assertEqual(report["issue_count"], 0)
        self.assertEqual(report["scanned"]["files"], 3)

    def test_rejects_release_boundary_violations(self) -> None:
        self.write("build/output.txt")
        self.write("__pycache__/module.pyc")
        self.write("docs/" + "launch" + "-plan.md")
        self.write("local" + "-artifacts/report.md")
        self.write(
            "README.md",
            "Agent Evidence Recorder is "
            + "production"
            + "-safe and provides "
            + "complete"
            + " rollback.\n",
        )

        report = check_release_boundary(self.temp_root)

        self.assertFalse(report["passed"])
        categories = {issue["category"] for issue in report["issues"]}
        self.assertIn("build_output", categories)
        self.assertIn("cache_or_test_state", categories)
        self.assertIn("seller_admin_material", categories)
        self.assertIn("private_or_local_material", categories)
        self.assertIn("unsupported_public_claim", categories)

    def test_rejects_pr_review_approval_overclaims(self) -> None:
        self.write(
            "README.md",
            "The PR review bundle automatically "
            + "approves pull "
            + "requests and replaces "
            + "human "
            + "reviewers.\n",
        )

        report = check_release_boundary(self.temp_root)

        self.assertFalse(report["passed"])
        categories = {issue["category"] for issue in report["issues"]}
        self.assertIn("unsupported_public_claim", categories)

    def test_report_is_json_serializable(self) -> None:
        self.write("README.md")
        report = check_release_boundary(self.temp_root)

        encoded = json.dumps(report, sort_keys=True)

        self.assertIn("agent_evidence_recorder.release_boundary.v0", encoded)


if __name__ == "__main__":
    unittest.main()
