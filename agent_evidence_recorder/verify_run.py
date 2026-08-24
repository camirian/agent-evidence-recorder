"""Agent Evidence verify-run: an INDEPENDENT, deterministic verdict on an agent's work.

Core principle (validated repeatedly in discovery): separate the doer from the
verifier. The coding agent must never be the one to attest that its own run
succeeded ("if the agent can both run the test and report the result, you've
already lost"). Agent Evidence re-checks the work on things the agent cannot narrate
around:

  1. tests run by US in a CLEAN `git worktree` checkout (kills the
     uncommitted-local-state false-pass)
  2. the real diff's blast radius (a "small fix" touching 30 files is a flag)
  3. test tampering (did the suite go green because tests were deleted / had
     assertions removed / got skipped?)

stdlib only. No LLM in the verdict -> same inputs produce the same verdict.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from pathlib import Path

# Assertion-ish lines, across common ecosystems (python/js/go/c++/rust-ish).
_ASSERTION_RE = re.compile(
    r"\b(assert|assertEqual|assertTrue|assertFalse|assertRaises|expect\(|"
    r"ASSERT_|EXPECT_|require\.|t\.Error|t\.Fatal|should\b|chai\.)"
)
# Markers that silence a test.
_SKIP_RE = re.compile(
    r"(pytest\.mark\.(skip|xfail)|@unittest\.skip|@skip\b|\.skip\(|\.only\(|"
    r"xfail|it\.skip|describe\.skip|test\.skip|t\.Skip\()"
)
# Paths that look like tests.
_TEST_PATH_RE = re.compile(
    r"(^|/)tests?/|(^|/)test_[^/]*$|_test\.[A-Za-z0-9]+$|"
    r"\.test\.[A-Za-z0-9]+$|\.spec\.[A-Za-z0-9]+$|Test[^/]*\.[A-Za-z0-9]+$"
)


def _git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path))


def _blast_radius(repo: Path, base_ref: str, head_ref: str) -> dict:
    out = _git(repo, "diff", "--numstat", f"{base_ref}..{head_ref}")
    files: list[dict] = []
    insertions = deletions = 0
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 3:
            continue
        added, removed, name = parts
        a = int(added) if added.isdigit() else 0  # "-" for binary files
        d = int(removed) if removed.isdigit() else 0
        insertions += a
        deletions += d
        files.append({"path": name, "insertions": a, "deletions": d})
    return {
        "files_changed": len(files),
        "insertions": insertions,
        "deletions": deletions,
        "files": files,
    }


def _tampering(repo: Path, base_ref: str, head_ref: str) -> dict:
    signals: list[dict] = []

    # Deleted test files.
    name_status = _git(repo, "diff", "--name-status", f"{base_ref}..{head_ref}")
    deleted_tests = [
        parts[-1]
        for line in name_status.splitlines()
        if (parts := line.split("\t")) and len(parts) >= 2
        and parts[0].startswith("D") and _is_test_path(parts[-1])
    ]
    if deleted_tests:
        signals.append({"kind": "deleted_test_files", "detail": deleted_tests})

    # Removed assertions / added skips, but only inside test files.
    diff = _git(repo, "diff", f"{base_ref}..{head_ref}")
    removed_assertions = added_assertions = added_skips = 0
    current_is_test = False
    for line in diff.splitlines():
        if line.startswith("diff --git"):
            current_is_test = False
            continue
        if line.startswith("+++ "):
            target = line[6:] if line.startswith("+++ b/") else line[4:]
            current_is_test = _is_test_path(target)
            continue
        if line.startswith("--- "):
            continue
        if not current_is_test:
            continue
        if line.startswith("-") and not line.startswith("---"):
            if _ASSERTION_RE.search(line):
                removed_assertions += 1
        elif line.startswith("+") and not line.startswith("+++"):
            if _ASSERTION_RE.search(line):
                added_assertions += 1
            if _SKIP_RE.search(line):
                added_skips += 1

    if removed_assertions > added_assertions:
        signals.append(
            {
                "kind": "weakened_assertions",
                "detail": {"removed": removed_assertions, "added": added_assertions},
            }
        )
    if added_skips:
        signals.append({"kind": "added_skips", "detail": {"count": added_skips}})

    return {"detected": bool(signals), "signals": signals}


def _run_tests_clean(
    repo: Path, head_ref: str, test_command, timeout: int
) -> tuple[int, str]:
    """Run the test command in a fresh, clean checkout we control -- never the
    agent's working tree (which may carry uncommitted state that fakes a pass)."""
    tmp = Path(tempfile.mkdtemp(prefix="agent_evidence-verify-"))
    worktree = tmp / "wt"
    try:
        _git(repo, "worktree", "add", "--detach", str(worktree), head_ref)
        proc = subprocess.run(
            test_command,
            cwd=str(worktree),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=isinstance(test_command, str),
        )
        tail = (proc.stdout + proc.stderr)[-2000:]
        return proc.returncode, tail
    finally:
        _git(repo, "worktree", "remove", "--force", str(worktree), check=False)
        shutil.rmtree(tmp, ignore_errors=True)


def verify_run(
    repo,
    base_ref: str,
    head_ref: str = "HEAD",
    test_command=None,
    blast_radius_threshold: int = 20,
    timeout: int = 600,
) -> dict:
    """Produce an independent, deterministic verdict on an agent's change.

    test_command: list[str] (preferred) or a shell string. If omitted, behavior
    cannot be confirmed and the verdict can be at best `needs_review`.
    """
    repo = Path(repo)
    blast = _blast_radius(repo, base_ref, head_ref)
    tamper = _tampering(repo, base_ref, head_ref)

    reasons: list[str] = []
    tests_passed = None
    exit_code = None
    tail = ""

    if test_command:
        exit_code, tail = _run_tests_clean(repo, head_ref, test_command, timeout)
        tests_passed = exit_code == 0
        if not tests_passed:
            reasons.append(f"tests failed in a clean checkout (exit {exit_code})")
    else:
        reasons.append("no test command -- behavior cannot be independently confirmed")

    if tamper["detected"]:
        for sig in tamper["signals"]:
            reasons.append(f"possible test tampering: {sig['kind']}")
    if blast["files_changed"] > blast_radius_threshold:
        reasons.append(
            f"large blast radius: {blast['files_changed']} files changed "
            f"(> {blast_radius_threshold})"
        )

    if tests_passed is False:
        verdict = "broken"
    elif tamper["detected"] or test_command is None or blast["files_changed"] > blast_radius_threshold:
        verdict = "needs_review"
    else:
        verdict = "trustworthy"
        reasons.append(
            "tests pass in a clean checkout; no tampering; blast radius within expectation"
        )

    return {
        "repo": str(repo),
        "base_ref": base_ref,
        "head_ref": head_ref,
        "test_command": test_command,
        "tests_passed": tests_passed,
        "test_exit_code": exit_code,
        "blast_radius": blast,
        "tampering": tamper,
        "verdict": verdict,
        "reasons": reasons,
        "test_output_tail": tail,
        "passed": verdict == "trustworthy",
    }
