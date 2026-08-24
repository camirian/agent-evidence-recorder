"""Agent Evidence fleet: triage many agent runs at once -- "which of last night's
runs do I actually need to look at?"

Scans Claude Code session transcripts, ingests each into a run record, and ranks
them by a deterministic SUSPICION score built from signals the agent can't
narrate around: did it run tests after changing code? did it finish cleanly? how
big was the surface? did it touch test files? This is TRIAGE, not proof -- pair
the suspicious few with `verify-run` for the hard verdict.

stdlib only. `--redact` masks repo/branch/intent so the triage board can be
shared safely.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from agent_evidence_recorder.ingest_session import ingest_session

_TEST_CMD_RE = re.compile(
    r"\b(pytest|unittest|jest|vitest|go test|cargo test|npm (run )?test|yarn test|"
    r"make test|tox|rspec|phpunit|dotnet test|gradle\b.*test|mvn\b.*test|ctest)\b"
)
_CODE_EXT = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".c",
    ".cc", ".cpp", ".h", ".hpp", ".cs", ".php", ".swift", ".kt", ".scala", ".sh",
}
_TEST_PATH_RE = re.compile(
    r"(^|/)tests?/|(^|/)test_[^/]*$|_test\.[A-Za-z0-9]+$|"
    r"\.test\.[A-Za-z0-9]+$|\.spec\.[A-Za-z0-9]+$|Test[^/]*\.[A-Za-z0-9]+$"
)


def _score(record: dict) -> tuple[int, list[str]]:
    score = 0
    reasons: list[str] = []
    files = [f for f in (record.get("files_touched") or []) if isinstance(f, str)]
    code = [f for f in files if Path(f).suffix in _CODE_EXT]
    test_files = [f for f in files if _TEST_PATH_RE.search(f)]
    commands = record.get("commands")
    ran_tests = (
        any(_TEST_CMD_RE.search(c) for c in commands) if isinstance(commands, list) else False
    )

    if code and not ran_tests:
        score += 3
        reasons.append(f"changed {len(code)} code file(s) but ran no tests")
    stop = record.get("last_stop_reason")
    if stop not in ("end_turn", "stop_sequence", None):
        score += 2
        reasons.append(f"did not end cleanly (stop_reason={stop})")
    if len(files) > 20:
        score += 2
        reasons.append(f"large surface ({len(files)} files)")
    if test_files:
        score += 1
        reasons.append(f"edited {len(test_files)} test file(s) -- confirm not weakened")
    if not files and record.get("assistant_turns", 0) > 0 and record.get("tools"):
        score += 1
        reasons.append("no files changed")
    return score, reasons


def level(score: int) -> str:
    return "SUSPECT" if score >= 3 else ("LOOK" if score >= 1 else "clean")


def verify_run_command(record: dict, redact: bool = False) -> str:
    """A paste-ready `verify-run` invocation for one run.

    We fill in ONLY what the transcript reliably gives us -- the repo path
    (record["cwd"]) -- and leave the base ref and test command as explicit
    placeholders. The pre-run base ref and the project's test command cannot be
    inferred from a session transcript, and inventing them would produce a
    fabricated verdict, which violates the doer != verifier principle. So we
    hand the reviewer an honest command to complete, never a fake one.
    """
    repo = "<repo>" if redact else (record.get("cwd") or "<repo>")
    return (
        f"agent_evidence-recorder verify-run --repo {repo} "
        f"--base <PASTE_PRE_RUN_REF> --test-cmd '<PASTE_TEST_CMD>'"
    )


def scan_runs(projects_dir, since_hours: float | None = 24) -> list[dict]:
    projects_dir = Path(projects_dir).expanduser()
    cutoff = time.time() - since_hours * 3600 if since_hours else None
    items: list[dict] = []
    for jsonl in projects_dir.rglob("*.jsonl"):
        try:
            if cutoff and jsonl.stat().st_mtime < cutoff:
                continue
            record = ingest_session(jsonl)
        except Exception:
            continue
        score, reasons = _score(record)
        item = {"path": str(jsonl), "record": record, "suspicion": score, "reasons": reasons}
        if score >= 1:
            item["verify_command"] = verify_run_command(record)
        items.append(item)
    items.sort(key=lambda i: (i["suspicion"], i["record"].get("ended_at") or ""), reverse=True)
    return items


def format_fleet(items: list[dict], redact: bool = False) -> str:
    if not items:
        return "no runs found in the window."
    lines = [f"{len(items)} run(s), most suspicious first:\n"]
    for index, item in enumerate(items, 1):
        rec = item["record"]
        repo = "repo-%d" % index if redact else (Path(rec["cwd"]).name if rec.get("cwd") else "?")
        branch = "[redacted]" if redact else (rec.get("git_branch") or "?")
        when = (rec.get("ended_at") or "")[:16].replace("T", " ")
        tools = " ".join(f"{k}×{v}" for k, v in (rec.get("tools") or {}).items()) or "-"
        top = item["reasons"][0] if item["reasons"] else "looks clean"
        lines.append(
            f"  [{level(item['suspicion']):>7}] {item['suspicion']:>2}  "
            f"{repo}@{branch}  {when}  {tools}\n"
            f"            → {top}"
        )
        if not redact and rec.get("intent"):
            lines.append(f'            intent: "{rec["intent"][:80]}"')
        if item["suspicion"] >= 1:
            lines.append(f"            verify: {verify_run_command(rec, redact=redact)}")
    lines.append(
        "\nTriage only. The verify lines above are paste-ready: fill in the"
        " pre-run base ref\nand your test command to get the independent verdict"
        " (the agent never attests\nto its own success)."
    )
    return "\n".join(lines)
