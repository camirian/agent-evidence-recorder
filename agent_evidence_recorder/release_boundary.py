"""Check public release artifact boundaries for Agent Evidence Recorder."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

SCHEMA_VERSION = "agent_evidence_recorder.release_boundary.v0"

SKIPPED_PARTS = {".git"}
CACHE_PARTS = {
    "__pycache__",
    ".cache",
    ".mypy_cache",
    ".nox",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "htmlcov",
}
BUILD_PARTS = {"build", "dist"}
VENV_PARTS = {".env", ".venv", "env", "venv"}
BUILD_SUFFIXES = {".pyc", ".pyo", ".tar", ".tar.gz", ".tgz", ".whl", ".zip"}
BINARY_SUFFIXES = {".dll", ".dylib", ".exe", ".so"}

SELLER_ADMIN_PATH_TERMS = [
    "admin",
    "gum" + "road",
    "launch" + " plan",
    "monetization",
    "payment",
    "pricing" + " strategy",
    "product" + " listing",
    "seller",
    "str" + "ipe",
]
PRIVATE_PATH_TERMS = [
    "scratch",
    "client" + " notes",
    "customer" + " notes",
    "employer" + " notes",
    "local" + " artifacts",
    "local" + " reports",
    "private" + " planning",
    "strategy" + " vault",
]
SELLER_ADMIN_TEXT_TERMS = [
    "gum" + "road",
    "launch" + " plan",
    "monetization" + " notes",
    "payment" + " setup",
    "product" + " listing",
    "seller" + " dashboard",
    "str" + "ipe",
]
PRIVATE_TEXT_PATTERNS = [
    re.compile("/" + "home" + "/", re.IGNORECASE),
    re.compile("/" + "Users" + "/", re.IGNORECASE),
    re.compile(r"\b" + "client" + r" notes\b", re.IGNORECASE),
    re.compile(r"\b" + "customer" + r" notes\b", re.IGNORECASE),
    re.compile(r"\b" + "employer" + r" notes\b", re.IGNORECASE),
    re.compile(r"\b" + "private" + r" strategy\b", re.IGNORECASE),
    re.compile(r"\b" + "strategy" + r"[-_ ]vault\b", re.IGNORECASE),
]
UNSUPPORTED_CLAIM_PATTERNS = [
    re.compile(
        r"\b(is|are|provides|provide|guarantees|guarantee|delivers)\s+"
        + "(production" + r"[- ]ready|production[- ]safe|safe for "
        + "production|customer[- ]ready)"
        + r"\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(provides|provide|guarantees|guarantee|delivers)\s+"
        + "complete"
        + r"\s+rollback\b",
        re.IGNORECASE,
    ),
    re.compile(r"\b" + "guaranteed" + r"\s+rollback\b", re.IGNORECASE),
    re.compile(r"\b" + "certification" + r"[- ]ready\b", re.IGNORECASE),
    re.compile(r"\b" + "certified" + r"\s+for\s+compliance\b", re.IGNORECASE),
    re.compile(r"\b" + "compliance" + r"[- ]certified\b", re.IGNORECASE),
    re.compile(r"\b" + "legally" + r"\s+reviewed\b", re.IGNORECASE),
    re.compile(r"\b(automatically\s+approves|auto[- ]approves)\b", re.IGNORECASE),
    re.compile(r"\bapproves\s+(pull\s+requests|prs)\b", re.IGNORECASE),
    re.compile(r"\breplaces\s+(human\s+)?review(ers?)?\b", re.IGNORECASE),
]
KEY_LIKE_PATTERNS = [
    re.compile(r"gh[opsru]_[A-Za-z0-9_]{8,}"),
    re.compile(r"sk-[A-Za-z0-9]{8,}"),
    re.compile(r"-----BEGIN [A-Z ]{0,24}KEY-----"),
]


def check_release_boundary(root: Path) -> dict:
    """Return a deterministic report for a candidate public release tree."""
    root = root.resolve()
    issues: list[dict] = []
    scanned_files = 0
    scanned_directories = 0

    if not root.exists():
        issues.append(issue("missing_path", root, root, "candidate path does not exist"))
        return report(root, scanned_files, scanned_directories, issues)
    if not root.is_dir():
        issues.append(issue("not_directory", root, root, "candidate path must be an extracted directory"))
        return report(root, scanned_files, scanned_directories, issues)

    for path in sorted(root.rglob("*")):
        relative_path = path.relative_to(root)
        if skipped_path(relative_path):
            continue
        if path.is_dir():
            scanned_directories += 1
            issues.extend(path_issues(root, path))
            continue
        if not path.is_file():
            issues.append(issue("unsupported_file_type", root, path, "only regular files are expected"))
            continue
        scanned_files += 1
        issues.extend(path_issues(root, path))
        issues.extend(content_issues(root, path))

    return report(root, scanned_files, scanned_directories, issues)


def skipped_path(relative_path: Path) -> bool:
    return any(part in SKIPPED_PARTS for part in relative_path.parts)


def path_issues(root: Path, path: Path) -> list[dict]:
    relative = path.relative_to(root)
    parts = {part.lower() for part in relative.parts}
    normalized = re.sub(r"[-_/ .]+", " ", relative.as_posix().lower())
    suffixes = suffix_set(path)
    issues: list[dict] = []

    if parts & CACHE_PARTS:
        issues.append(issue("cache_or_test_state", root, path, "cache or test state must not ship"))
    if parts & BUILD_PARTS or suffixes & BUILD_SUFFIXES:
        issues.append(issue("build_output", root, path, "build outputs must not ship inside the candidate"))
    if parts & VENV_PARTS:
        issues.append(issue("local_environment", root, path, "local environment files must not ship"))
    if suffixes & BINARY_SUFFIXES:
        issues.append(issue("binary_artifact", root, path, "source-only candidate contains a binary artifact"))
    if any(term in normalized for term in SELLER_ADMIN_PATH_TERMS):
        issues.append(issue("seller_admin_material", root, path, "seller or admin material is outside the release boundary"))
    if any(term in normalized for term in PRIVATE_PATH_TERMS):
        issues.append(issue("private_or_local_material", root, path, "private or local report material is outside the release boundary"))
    return issues


def content_issues(root: Path, path: Path) -> list[dict]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return [issue("unreadable_file", root, path, f"could not read file: {exc}")]
    if b"\0" in raw:
        return [issue("binary_artifact", root, path, "source-only candidate contains non-text bytes")]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return [issue("binary_artifact", root, path, "source-only candidate must be UTF-8 text")]

    issues: list[dict] = []
    normalized_text = re.sub(r"[-_/ .]+", " ", text.lower())
    if any(term in normalized_text for term in SELLER_ADMIN_TEXT_TERMS):
        issues.append(issue("seller_admin_material", root, path, "seller or admin material is outside the release boundary"))
    if any(pattern.search(text) for pattern in PRIVATE_TEXT_PATTERNS):
        issues.append(issue("private_or_local_material", root, path, "private material, local paths, or local reports are outside the release boundary"))
    if any(pattern.search(text) for pattern in UNSUPPORTED_CLAIM_PATTERNS):
        issues.append(issue("unsupported_public_claim", root, path, "public claim exceeds the documented synthetic/local boundary"))
    for pattern in KEY_LIKE_PATTERNS:
        if pattern.search(text):
            issues.append(issue("access_material", root, path, "key-shaped access material must not ship"))
            break
    return issues


def suffix_set(path: Path) -> set[str]:
    suffixes = set(path.suffixes)
    name = path.name.lower()
    if name.endswith(".tar.gz"):
        suffixes.add(".tar.gz")
    return {suffix.lower() for suffix in suffixes}


def issue(category: str, root: Path, path: Path, detail: str) -> dict:
    try:
        relative = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        relative = path.as_posix()
    return {
        "severity": "blocker",
        "category": category,
        "path": relative or ".",
        "detail": detail,
    }


def report(root: Path, scanned_files: int, scanned_directories: int, issues: Iterable[dict]) -> dict:
    ordered_issues = sorted(issues, key=lambda item: (item["category"], item["path"], item["detail"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "path": str(root),
        "passed": not ordered_issues,
        "scanned": {
            "files": scanned_files,
            "directories": scanned_directories,
        },
        "issue_count": len(ordered_issues),
        "issues": ordered_issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m agent_evidence_recorder.release_boundary")
    parser.add_argument("path", type=Path, help="extracted release artifact or staged candidate tree")
    args = parser.parse_args(argv)

    boundary_report = check_release_boundary(args.path)
    print(json.dumps(boundary_report, indent=2, sort_keys=True))
    return 0 if boundary_report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
