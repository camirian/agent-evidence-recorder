"""Functional tests for the session ingester, using a SYNTHETIC transcript
fixture (never a real session -- no private content in git)."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from agent_evidence_recorder.ingest_session import ingest_session

_FIXTURE = [
    {
        "type": "user",
        "sessionId": "s1",
        "cwd": "/work/x/repo",
        "gitBranch": "main",
        "version": "2.1.0",
        "timestamp": "2026-06-23T01:00:00Z",
        "message": {"role": "user", "content": "Fix the auth bug and add a test"},
    },
    {
        "type": "assistant",
        "sessionId": "s1",
        "timestamp": "2026-06-23T01:01:00Z",
        "message": {
            "role": "assistant",
            "model": "claude-opus-4-8",
            "stop_reason": "tool_use",
            "content": [
                {"type": "text", "text": "Working on it."},
                {"type": "tool_use", "name": "Bash", "input": {"command": "pytest -q"}},
                {"type": "tool_use", "name": "Write", "input": {"file_path": "/work/x/repo/auth.py", "content": "..."}},
            ],
        },
    },
    {
        # a tool-result user record must NOT be counted as the intent
        "type": "user",
        "sessionId": "s1",
        "timestamp": "2026-06-23T01:01:30Z",
        "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]},
    },
    {"type": "pr-link", "sessionId": "s1", "prNumber": 12, "prUrl": "http://x/12", "prRepository": "o/r"},
]


class IngestSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp(prefix="agent_evidence-ingest-"))
        self.path = self.tmp / "session.jsonl"
        self.path.write_text("\n".join(json.dumps(o) for o in _FIXTURE) + "\n")

    def test_extracts_run_record(self) -> None:
        rec = ingest_session(self.path)
        self.assertEqual(rec["session_id"], "s1")
        self.assertEqual(rec["cwd"], "/work/x/repo")
        self.assertEqual(rec["git_branch"], "main")
        self.assertEqual(rec["intent"], "Fix the auth bug and add a test")
        self.assertEqual(rec["user_turns"], 1)  # tool_result user record excluded
        self.assertEqual(rec["assistant_turns"], 1)
        self.assertEqual(rec["tools"], {"Bash": 1, "Write": 1})
        self.assertEqual(rec["commands"], ["pytest -q"])
        self.assertEqual(rec["files_touched"], ["/work/x/repo/auth.py"])
        self.assertEqual(rec["models"], ["claude-opus-4-8"])
        self.assertEqual(rec["pr_links"][0]["number"], 12)
        self.assertEqual(rec["started_at"], "2026-06-23T01:00:00Z")
        self.assertEqual(rec["ended_at"], "2026-06-23T01:01:30Z")

    def test_redact_hides_free_text(self) -> None:
        rec = ingest_session(self.path, redact=True)
        self.assertEqual(rec["intent"], "[redacted]")
        self.assertEqual(rec["commands"], "[redacted]")
        self.assertEqual(rec["files_touched"], ["[1 files]"])
        self.assertEqual(rec["tools"], {"Bash": 1, "Write": 1})  # counts still present


if __name__ == "__main__":
    unittest.main()
