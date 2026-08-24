"""Functional tests for the fleet triage view, using synthetic session fixtures."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_evidence_recorder.fleet import format_fleet, level, scan_runs


def _session(records: list[dict]) -> str:
    return "\n".join(json.dumps(r) for r in records) + "\n"


def _assistant(tool_uses: list[dict], stop_reason: str = "end_turn") -> dict:
    return {
        "type": "assistant",
        "timestamp": "2026-06-23T02:00:00Z",
        "message": {
            "role": "assistant",
            "model": "claude-opus-4-8",
            "stop_reason": stop_reason,
            "content": [{"type": "tool_use", **tu} for tu in tool_uses],
        },
    }


class FleetTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="agent_evidence-fleet-"))
        self.proj = self.tmp / "projects"
        (self.proj / "a").mkdir(parents=True)
        (self.proj / "b").mkdir(parents=True)
        (self.proj / "c").mkdir(parents=True)

        user = lambda txt, cwd: {  # noqa: E731
            "type": "user", "cwd": cwd, "gitBranch": "main",
            "timestamp": "2026-06-23T01:59:00Z",
            "message": {"role": "user", "content": txt},
        }

        # clean: changed code AND ran tests, ended cleanly
        (self.proj / "a" / "s.jsonl").write_text(_session([
            user("add feature", "/r/clean"),
            _assistant([
                {"name": "Write", "input": {"file_path": "/r/clean/app.py", "content": "x"}},
                {"name": "Bash", "input": {"command": "pytest -q"}},
            ]),
        ]))
        # suspect: changed code, NO tests, did not end cleanly
        (self.proj / "b" / "s.jsonl").write_text(_session([
            user("quick fix", "/r/suspect"),
            _assistant([
                {"name": "Write", "input": {"file_path": "/r/suspect/core.py", "content": "x"}},
                {"name": "Bash", "input": {"command": "git commit -am wip"}},
            ], stop_reason="tool_use"),
        ]))
        # look: edited a test file but ran tests and ended cleanly
        (self.proj / "c" / "s.jsonl").write_text(_session([
            user("update tests", "/r/look"),
            _assistant([
                {"name": "Edit", "input": {"file_path": "/r/look/tests/test_x.py", "content": "x"}},
                {"name": "Bash", "input": {"command": "pytest -q"}},
            ]),
        ]))

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_ranks_by_suspicion(self) -> None:
        items = scan_runs(self.proj, since_hours=None)
        self.assertEqual(len(items), 3)
        repos = [Path(i["record"]["cwd"]).name for i in items]
        self.assertEqual(repos[0], "suspect")  # most suspicious first
        self.assertEqual(level(items[0]["suspicion"]), "SUSPECT")
        # clean run scores 0
        clean = next(i for i in items if Path(i["record"]["cwd"]).name == "clean")
        self.assertEqual(clean["suspicion"], 0)
        self.assertEqual(level(clean["suspicion"]), "clean")
        # suspect run has the "no tests" reason
        suspect = items[0]
        self.assertTrue(any("ran no tests" in r for r in suspect["reasons"]))
        self.assertTrue(any("did not end cleanly" in r for r in suspect["reasons"]))

    def test_suspect_runs_get_paste_ready_verify_command(self) -> None:
        items = scan_runs(self.proj, since_hours=None)
        suspect = items[0]  # /r/suspect, suspicion >= 3
        self.assertGreaterEqual(suspect["suspicion"], 1)
        cmd = suspect["verify_command"]
        # real repo path filled in; base/test-cmd left as honest placeholders
        self.assertIn("--repo /r/suspect", cmd)
        self.assertIn("<PASTE_PRE_RUN_REF>", cmd)
        self.assertIn("<PASTE_TEST_CMD>", cmd)
        # clean run (suspicion 0) carries no command
        clean = next(i for i in items if Path(i["record"]["cwd"]).name == "clean")
        self.assertNotIn("verify_command", clean)
        # the board shows the command for suspects
        self.assertIn("verify: agent_evidence-recorder verify-run", format_fleet(items))

    def test_redacted_verify_command_hides_repo_path(self) -> None:
        items = scan_runs(self.proj, since_hours=None)
        out = format_fleet(items, redact=True)
        self.assertIn("--repo <repo>", out)  # placeholder, not the real path
        self.assertNotIn("/r/suspect", out)  # real path never leaks

    def test_redacted_output_hides_repo_and_intent(self) -> None:
        items = scan_runs(self.proj, since_hours=None)
        out = format_fleet(items, redact=True)
        self.assertIn("repo-1", out)
        self.assertNotIn("suspect", out)  # real repo name masked
        self.assertNotIn("quick fix", out)  # intent masked


if __name__ == "__main__":
    unittest.main()
