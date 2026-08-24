"""Functional tests for the independent verifier (the doer != verifier core).

These are real tests, not lint: each builds a throwaway git repo, makes a base
commit and a head commit, and asserts Agent Evidence's verdict on the change.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent_evidence_recorder.verify_run import verify_run


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True)


def _head(repo: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()


class VerifyRunTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="agent_evidence-test-"))
        self.repo = self.tmp
        _git(self.repo, "init", "-q")
        _git(self.repo, "config", "user.email", "t@example.com")
        _git(self.repo, "config", "user.name", "t")
        (self.repo / "calc.py").write_text("def add(a, b):\n    return a + b\n")
        (self.repo / "test_calc.py").write_text(
            "from calc import add\nassert add(2, 3) == 5\nprint('ok')\n"
        )
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", "base")
        self.base = _head(self.repo)
        self.test_cmd = [sys.executable, "test_calc.py"]

    def tearDown(self) -> None:
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _commit(self, message: str) -> None:
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-q", "-m", message)

    def test_clean_change_is_trustworthy(self) -> None:
        (self.repo / "calc.py").write_text(
            "def add(a, b):\n    return a + b\n\ndef sub(a, b):\n    return a - b\n"
        )
        self._commit("add sub()")
        report = verify_run(self.repo, self.base, "HEAD", self.test_cmd)
        self.assertEqual(report["verdict"], "trustworthy", report["reasons"])
        self.assertTrue(report["passed"])

    def test_broken_change_is_broken(self) -> None:
        (self.repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")  # wrong
        self._commit("break add()")
        report = verify_run(self.repo, self.base, "HEAD", self.test_cmd)
        self.assertEqual(report["verdict"], "broken")
        self.assertFalse(report["tests_passed"])

    def test_gamed_tests_are_caught(self) -> None:
        # The killer case: agent breaks the code AND removes the assertion so the
        # suite still "passes". Self-report says done; Agent Evidence must not agree.
        (self.repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")  # wrong
        (self.repo / "test_calc.py").write_text("from calc import add\nprint('ok')\n")  # assert removed
        self._commit("weaken test to go green")
        report = verify_run(self.repo, self.base, "HEAD", self.test_cmd)
        self.assertTrue(report["tampering"]["detected"])
        self.assertEqual(report["verdict"], "needs_review")
        self.assertFalse(report["passed"])

    def test_deleted_test_file_flagged(self) -> None:
        (self.repo / "test_calc.py").unlink()
        (self.repo / "smoke.py").write_text("print('ok')\n")  # so a cmd still exists
        self._commit("delete the test")
        report = verify_run(self.repo, self.base, "HEAD", [sys.executable, "smoke.py"])
        kinds = {s["kind"] for s in report["tampering"]["signals"]}
        self.assertIn("deleted_test_files", kinds)
        self.assertEqual(report["verdict"], "needs_review")


if __name__ == "__main__":
    unittest.main()
