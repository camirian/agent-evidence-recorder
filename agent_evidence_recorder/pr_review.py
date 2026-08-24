"""Generate a public-safe reviewer packet for a GitHub pull request."""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "agent_evidence_recorder.pr_review.v0"
PR_REVIEW_REQUIRED_ARTIFACTS = {
    "artifact_manifest.json",
    "changed_files.json",
    "commands.log",
    "file_diffs.json",
    "pr_metadata.json",
    "review_outcome.json",
    "review_request.md",
    "reviewer_packet.md",
    "risk_summary.json",
    "run_record.json",
    "status_checks.json",
}
PR_REVIEW_MANIFEST_ARTIFACTS = PR_REVIEW_REQUIRED_ARTIFACTS - {"artifact_manifest.json"}
PR_REVIEW_RUN_OUTPUT_ARTIFACTS = PR_REVIEW_REQUIRED_ARTIFACTS - {"artifact_manifest.json", "run_record.json"}
MUTABLE_REVIEW_OUTCOME_MANIFEST_CHECKS = {
    "manifest:review_outcome.json:sha256",
    "manifest:review_outcome.json:bytes",
}
HIGH_RISK_FILE_FLAGS = {"ci_or_automation", "security_or_policy"}
LARGE_CHANGE_FILE_COUNT = 20
LARGE_CHANGE_LINE_COUNT = 500
MAX_DIFF_FILES = 12
MAX_PATCH_LINES_PER_FILE = 80


class PrReviewError(RuntimeError):
    """Raised when PR review bundle generation cannot continue."""


def fetch_pr_metadata(repo: str, pr_number: int) -> dict[str, Any]:
    fields = ",".join(
        [
            "number",
            "title",
            "url",
            "state",
            "author",
            "baseRefName",
            "headRefName",
            "changedFiles",
            "additions",
            "deletions",
            "reviewDecision",
            "createdAt",
            "updatedAt",
            "body",
            "files",
            "commits",
            "statusCheckRollup",
        ]
    )
    command = ["gh", "pr", "view", str(pr_number), "--repo", repo, "--json", fields]
    try:
        completed = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise PrReviewError("gh CLI is required for pr-review") from exc
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        raise PrReviewError(f"failed to read PR metadata: {detail}") from exc
    metadata = json.loads(completed.stdout)
    metadata["files"] = fetch_pr_files(repo, pr_number)
    return metadata


def fetch_pr_files(repo: str, pr_number: int) -> list[dict[str, Any]]:
    command = ["gh", "api", f"repos/{repo}/pulls/{pr_number}/files"]
    try:
        completed = subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.strip() or exc.stdout.strip()
        raise PrReviewError(f"failed to read PR file metadata: {detail}") from exc
    except FileNotFoundError as exc:
        raise PrReviewError("gh CLI is required for pr-review") from exc
    return json.loads(completed.stdout)


def write_pr_review_bundle(
    metadata: dict[str, Any],
    output_dir: Path,
    *,
    repo: str,
    source_command: list[str] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    source_command = source_command or ["gh", "pr", "view", str(metadata["number"]), "--repo", repo]

    pr_metadata = normalize_pr_metadata(metadata, repo, generated_at)
    changed_files = build_changed_files(metadata)
    file_diffs = build_file_diffs(metadata)
    status_checks = build_status_checks(metadata)
    risk_summary = build_risk_summary(metadata, changed_files, file_diffs, status_checks)
    review_outcome = build_review_outcome_template(pr_metadata, risk_summary, generated_at)
    run_record = build_run_record(pr_metadata, risk_summary, generated_at, source_command)
    review_request = render_review_request(pr_metadata, risk_summary, review_outcome)
    reviewer_packet = render_reviewer_packet(pr_metadata, changed_files, file_diffs, status_checks, risk_summary)
    commands_log = render_commands_log(source_command)

    artifacts: dict[str, str] = {
        "pr_metadata.json": json.dumps(pr_metadata, indent=2, sort_keys=True) + "\n",
        "changed_files.json": json.dumps(changed_files, indent=2, sort_keys=True) + "\n",
        "file_diffs.json": json.dumps(file_diffs, indent=2, sort_keys=True) + "\n",
        "status_checks.json": json.dumps(status_checks, indent=2, sort_keys=True) + "\n",
        "risk_summary.json": json.dumps(risk_summary, indent=2, sort_keys=True) + "\n",
        "review_outcome.json": json.dumps(review_outcome, indent=2, sort_keys=True) + "\n",
        "run_record.json": json.dumps(run_record, indent=2, sort_keys=True) + "\n",
        "review_request.md": review_request,
        "reviewer_packet.md": reviewer_packet,
        "commands.log": commands_log,
    }
    for name, contents in artifacts.items():
        (output_dir / name).write_text(contents, encoding="utf-8")

    manifest = build_manifest(output_dir, artifacts.keys(), generated_at)
    (output_dir / "artifact_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "output_dir": str(output_dir),
        "artifacts": sorted([*artifacts, "artifact_manifest.json"]),
        "final_status": run_record["final_status"],
    }


def verify_pr_review_bundle(bundle_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    add("bundle_directory_present", bundle_dir.is_dir(), str(bundle_dir))
    if not bundle_dir.is_dir():
        return {"passed": False, "checks": checks}

    present = {path.name for path in bundle_dir.iterdir() if path.is_file()}
    missing = sorted(PR_REVIEW_REQUIRED_ARTIFACTS - present)
    add("required_artifacts_present", not missing, ",".join(missing))

    manifest = read_bundle_json(bundle_dir / "artifact_manifest.json", add)
    run_record = read_bundle_json(bundle_dir / "run_record.json", add)
    pr_metadata = read_bundle_json(bundle_dir / "pr_metadata.json", add)
    changed_files = read_bundle_json(bundle_dir / "changed_files.json", add)
    file_diffs = read_bundle_json(bundle_dir / "file_diffs.json", add)
    status_checks = read_bundle_json(bundle_dir / "status_checks.json", add)
    risk_summary = read_bundle_json(bundle_dir / "risk_summary.json", add)
    review_outcome = read_bundle_json(bundle_dir / "review_outcome.json", add)
    review_request = read_bundle_text(bundle_dir / "review_request.md", add)
    reviewer_packet = read_bundle_text(bundle_dir / "reviewer_packet.md", add)
    commands_log = read_bundle_text(bundle_dir / "commands.log", add)

    if manifest:
        verify_manifest(bundle_dir, manifest, add)
    if run_record:
        verify_run_record(run_record, add)
    if pr_metadata:
        add("pr_metadata_schema", pr_metadata.get("schema_version") == SCHEMA_VERSION, pr_metadata.get("schema_version", ""))
        add("pr_metadata_public_boundary", bool(pr_metadata.get("repo") and pr_metadata.get("number")), "")
    if changed_files:
        verify_changed_files(changed_files, add)
    if file_diffs:
        verify_file_diffs(file_diffs, add)
    if status_checks:
        verify_status_checks(status_checks, add)
    if risk_summary:
        verify_risk_summary(risk_summary, add)
    if review_outcome:
        verify_review_outcome(review_outcome, add)
    if review_request:
        add(
            "review_request_has_sections",
            all(
                section in review_request
                for section in (
                    "# PR Review Request",
                    "## What To Inspect",
                    "## Question To Answer",
                    "## Where To Record The Outcome",
                    "## Useful Response Format",
                )
            ),
            "",
        )
    if reviewer_packet:
        add(
            "reviewer_packet_has_sections",
            all(
                section in reviewer_packet
                for section in (
                    "## Risk Summary",
                    "## Review Decision Checklist",
                    "## Changed Files",
                    "## Diff Excerpts",
                    "## Status Checks",
                )
            ),
            "",
        )
    if commands_log:
        add("commands_log_records_source", "source_command:" in commands_log, "")

    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def verify_recorded_review_outcome(bundle_dir: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    bundle_report = verify_pr_review_bundle(bundle_dir)
    bundle_failures = [check for check in bundle_report["checks"] if not check["passed"]]
    blocking_bundle_failures = [
        check for check in bundle_failures if check["name"] not in MUTABLE_REVIEW_OUTCOME_MANIFEST_CHECKS
    ]
    add(
        "bundle_contract_valid_except_review_outcome_manifest",
        not blocking_bundle_failures,
        ",".join(check["name"] for check in blocking_bundle_failures),
    )

    review_outcome = read_bundle_json(bundle_dir / "review_outcome.json", add)
    risk_summary = read_bundle_json(bundle_dir / "risk_summary.json", add)
    if not review_outcome:
        return {"passed": False, "checks": checks}

    allowed_decisions = set(review_outcome.get("allowed_decisions") or [])
    reviewer_decision = str(review_outcome.get("reviewer_decision") or "")
    reviewer_notes = str(review_outcome.get("reviewer_notes") or "").strip()
    evidence_references = review_outcome.get("evidence_references") or []
    high_risk = bool(
        risk_summary
        and (
            risk_summary.get("risk_level") == "needs_review"
            or bool(risk_summary.get("risk_reasons") or [])
            or review_outcome.get("recommended_starting_decision") != "accept"
        )
    )

    add("reviewer_decision_recorded", bool(reviewer_decision), reviewer_decision)
    add("reviewer_decision_allowed", reviewer_decision in allowed_decisions, reviewer_decision)
    add(
        "reviewer_notes_required_for_non_accept",
        reviewer_decision == "accept" or bool(reviewer_notes),
        reviewer_decision,
    )
    add(
        "reviewer_notes_required_for_risky_accept",
        reviewer_decision != "accept" or not high_risk or bool(reviewer_notes),
        reviewer_decision,
    )
    add("evidence_references_present", bool(evidence_references), "")
    invalid_references = [
        reference
        for reference in evidence_references
        if not isinstance(reference, str)
        or not reference
        or Path(reference).is_absolute()
        or ".." in Path(reference).parts
    ]
    missing_references = [
        reference
        for reference in evidence_references
        if isinstance(reference, str)
        and reference
        and not Path(reference).is_absolute()
        and ".." not in Path(reference).parts
        and not (bundle_dir / reference).is_file()
    ]
    add("evidence_references_relative", not invalid_references, ",".join(invalid_references))
    add("evidence_references_exist", not missing_references, ",".join(missing_references))

    return {"passed": all(check["passed"] for check in checks), "checks": checks}


def inspect_pr_review_bundle(bundle_dir: Path) -> str:
    report = verify_pr_review_bundle(bundle_dir)
    run_record = load_optional_bundle_json(bundle_dir / "run_record.json")
    pr_metadata = load_optional_bundle_json(bundle_dir / "pr_metadata.json")
    risk_summary = load_optional_bundle_json(bundle_dir / "risk_summary.json")
    status_checks = load_optional_bundle_json(bundle_dir / "status_checks.json")
    file_diffs = load_optional_bundle_json(bundle_dir / "file_diffs.json")
    review_outcome = load_optional_bundle_json(bundle_dir / "review_outcome.json")

    failed = [check for check in report["checks"] if not check["passed"]]
    repair_hints = pr_review_bundle_repair_hints(failed)
    risk_reasons = risk_summary.get("risk_reasons") or []
    risk_flags = risk_summary.get("risk_flags") or []
    adversarial_traps = risk_summary.get("adversarial_traps") or []
    status_summary = status_checks.get("summary") or {}
    status_check_entries = status_checks.get("checks") or []
    diff_summary = file_diffs.get("summary") or {}
    output_files = [
        "review_request.md",
        "reviewer_packet.md",
        "review_outcome.json",
        "risk_summary.json",
        "file_diffs.json",
        "status_checks.json",
    ]

    lines = [
        f"PR review bundle: {pr_metadata.get('repo', 'unknown repo')} #{pr_metadata.get('number', 'unknown')}",
        f"Title: {pr_metadata.get('title', '') or 'unknown'}",
        f"Bundle verification: {'passed' if report['passed'] else 'failed'}",
        f"Final status: {run_record.get('final_status', 'unknown')}",
        f"Risk level: {risk_summary.get('risk_level', 'unknown')}",
        f"Recommended starting decision: {review_outcome.get('recommended_starting_decision', 'unknown')}",
        "Status checks: "
        f"total={status_summary.get('total', 0)}; "
        f"results={format_counts(status_summary.get('results') or {})}; "
        f"risk flags={format_list(status_summary.get('risk_flags') or [])}",
        (
            status_check_interpretation(status_checks)
            if status_summary
            else "- Interpretation: status-check evidence is unavailable."
        ),
        f"Risk flags: {format_list(risk_flags)}",
        "Diff excerpts observed/omitted/truncated: "
        f"{diff_summary.get('files_with_patch', 0)}/"
        f"{diff_summary.get('files_omitted', 0)}/"
        f"{diff_summary.get('patches_truncated', 0)}",
        "",
        "Risk reasons:",
        *(f"- {reason}" for reason in risk_reasons),
    ]
    if not risk_reasons:
        lines.append("- none")

    lines.extend(["", "PR-review traps:"])
    if adversarial_traps:
        lines.extend(f"- {trap}" for trap in adversarial_traps)
    else:
        lines.append("- none")

    lines.extend(["", "Status check details:"])
    if status_check_entries:
        lines.extend(format_status_check_detail(check) for check in status_check_entries)
    else:
        lines.append("- none reported")

    lines.extend(
        [
            "",
            "Next action:",
            pr_review_next_action(report["passed"], failed, risk_reasons, review_outcome),
            "",
            "Open next:",
            *(
                [f"- {name}" for name in output_files if (bundle_dir / name).is_file()]
                or ["- no reviewer artifacts available yet"]
            ),
            "",
            "Reviewer question:",
            "Would this PR review bundle reduce review burden, or does it add noise?",
        ]
    )
    if repair_hints:
        lines.extend(
            [
                "",
                "Repair before review:",
                *(f"- {hint}" for hint in repair_hints),
            ]
        )
    if failed:
        lines.extend(
            [
                "",
                "Failed verification checks:",
                *(f"- {check['name']}: {check['detail']}" for check in failed),
            ]
        )
    return "\n".join(lines) + "\n"


def format_list(values: list[Any]) -> str:
    return ", ".join(str(value) for value in values) if values else "none"


def format_status_check_detail(check: dict[str, Any]) -> str:
    fields = [f"result={check.get('result', 'unknown')}"]
    if check.get("conclusion"):
        fields.append(f"conclusion={check['conclusion']}")
    if check.get("status"):
        fields.append(f"status={check['status']}")
    if check.get("state"):
        fields.append(f"state={check['state']}")
    fields.append(f"risk flags={format_list(check.get('risk_flags') or [])}")
    return f"- {check.get('name', 'unknown')}: " + "; ".join(fields)


def pr_review_next_action(
    bundle_verified: bool,
    failed_checks: list[dict[str, Any]],
    risk_reasons: list[Any],
    review_outcome: dict[str, Any],
) -> str:
    if not bundle_verified or failed_checks:
        return "Repair the bundle before review; do not use stale or malformed evidence to decide the PR."
    recommended_decision = review_outcome.get("recommended_starting_decision", "unknown")
    if risk_reasons or recommended_decision == "needs_followup":
        return (
            "Open reviewer_packet.md, resolve the listed risk reasons, and record the human decision "
            "in review_outcome.json; successful checks are evidence, not approval."
        )
    return (
        "Open reviewer_packet.md, confirm the diff and check coverage, then record the human decision "
        "in review_outcome.json."
    )


def pr_review_bundle_repair_hints(failed: list[dict[str, Any]]) -> list[str]:
    hints: list[str] = []

    def add_hint(hint: str) -> None:
        if hint not in hints:
            hints.append(hint)

    for check in failed:
        name = str(check.get("name", ""))
        detail = str(check.get("detail", ""))
        if name == "bundle_directory_present":
            add_hint("Create a PR review bundle first, or pass the correct --bundle-dir path.")
        elif name == "required_artifacts_present" and detail:
            add_hint(f"Regenerate or restore missing artifacts: {detail}.")
        elif name.endswith(":present"):
            artifact = name.removesuffix(":present")
            add_hint(f"Regenerate or restore missing artifact: {artifact}.")
        elif name.endswith(":valid_json"):
            artifact = name.removesuffix(":valid_json")
            add_hint(f"Fix invalid JSON or regenerate artifact: {artifact}.")
        elif name.startswith("manifest:") and name.endswith(":sha256"):
            artifact = name.removeprefix("manifest:").removesuffix(":sha256")
            add_hint(f"Regenerate the bundle because manifest hash verification failed for {artifact}.")
        elif name.startswith("manifest:") and name.endswith(":bytes"):
            artifact = name.removeprefix("manifest:").removesuffix(":bytes")
            add_hint(f"Regenerate the bundle because manifest byte-count verification failed for {artifact}.")
        elif name == "manifest_lists_required_artifacts":
            add_hint("Regenerate the bundle so the manifest lists every required artifact.")
        elif name.endswith("_schema"):
            add_hint("Regenerate the bundle with the current recorder version; at least one artifact schema is stale.")
        elif name.endswith("_has_sections"):
            add_hint("Regenerate the bundle so reviewer Markdown includes the required sections.")

    return hints


def load_optional_bundle_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def read_bundle_json(path: Path, add: Any) -> dict[str, Any] | None:
    if not path.is_file():
        add(f"{path.name}:present", False, str(path))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        add(f"{path.name}:valid_json", False, str(exc))
        return None


def read_bundle_text(path: Path, add: Any) -> str | None:
    if not path.is_file():
        add(f"{path.name}:present", False, str(path))
        return None
    return path.read_text(encoding="utf-8")


def verify_manifest(bundle_dir: Path, manifest: dict[str, Any], add: Any) -> None:
    add("manifest_schema", manifest.get("schema_version") == SCHEMA_VERSION, manifest.get("schema_version", ""))
    artifacts = manifest.get("artifacts") or []
    manifest_paths = {artifact.get("relative_path", "") for artifact in artifacts}
    add("manifest_lists_required_artifacts", PR_REVIEW_MANIFEST_ARTIFACTS <= manifest_paths, ",".join(sorted(PR_REVIEW_MANIFEST_ARTIFACTS - manifest_paths)))
    for artifact in artifacts:
        relative_path = artifact.get("relative_path", "")
        path = bundle_dir / relative_path
        if not relative_path or Path(relative_path).is_absolute() or ".." in Path(relative_path).parts:
            add(f"manifest:{relative_path}:relative_path", False, relative_path)
            continue
        if not path.is_file():
            add(f"manifest:{relative_path}:file_present", False, relative_path)
            continue
        add(f"manifest:{relative_path}:sha256", sha256_file(path) == artifact.get("sha256"), relative_path)
        add(f"manifest:{relative_path}:bytes", path.stat().st_size == artifact.get("bytes"), relative_path)


def verify_run_record(run_record: dict[str, Any], add: Any) -> None:
    add("run_record_schema", run_record.get("schema_version") == SCHEMA_VERSION, run_record.get("schema_version", ""))
    add("run_record_adapter", run_record.get("adapter") == "github_pr_review", run_record.get("adapter", ""))
    outputs = set(run_record.get("output_artifacts") or [])
    add("run_record_outputs_required_artifacts", PR_REVIEW_RUN_OUTPUT_ARTIFACTS <= outputs, ",".join(sorted(PR_REVIEW_RUN_OUTPUT_ARTIFACTS - outputs)))
    add("run_record_boundary_public_metadata", "public GitHub PR metadata only" in run_record.get("boundary", ""), run_record.get("boundary", ""))
    add("run_record_final_status_allowed", run_record.get("final_status") in {"accepted_for_review", "needs_human_review"}, run_record.get("final_status", ""))


def verify_changed_files(changed_files: dict[str, Any], add: Any) -> None:
    add("changed_files_schema", changed_files.get("schema_version") == SCHEMA_VERSION, changed_files.get("schema_version", ""))
    files = changed_files.get("files")
    add("changed_files_list", isinstance(files, list), type(files).__name__)
    if isinstance(files, list):
        add("changed_files_paths_relative", all(file_info.get("path") and not Path(file_info.get("path", "")).is_absolute() for file_info in files), "")


def verify_file_diffs(file_diffs: dict[str, Any], add: Any) -> None:
    add("file_diffs_schema", file_diffs.get("schema_version") == SCHEMA_VERSION, file_diffs.get("schema_version", ""))
    limits = file_diffs.get("limits") or {}
    summary = file_diffs.get("summary") or {}
    files = file_diffs.get("files") or []
    add("file_diffs_limits_present", {"max_files", "max_patch_lines_per_file"} <= set(limits), "")
    add("file_diffs_summary_present", {"files_with_patch", "files_without_patch", "files_omitted", "patches_truncated"} <= set(summary), "")
    add("file_diffs_file_limit_respected", len(files) <= limits.get("max_files", MAX_DIFF_FILES), str(len(files)))
    add("file_diffs_patch_limit_respected", all(len(file_info.get("patch_excerpt") or []) <= limits.get("max_patch_lines_per_file", MAX_PATCH_LINES_PER_FILE) for file_info in files), "")
    add("file_diffs_paths_relative", all(file_info.get("path") and not Path(file_info.get("path", "")).is_absolute() for file_info in files), "")


def verify_status_checks(status_checks: dict[str, Any], add: Any) -> None:
    add("status_checks_schema", status_checks.get("schema_version") == SCHEMA_VERSION, status_checks.get("schema_version", ""))
    summary = status_checks.get("summary") or {}
    checks = status_checks.get("checks")
    add("status_checks_summary_present", {"total", "results", "risk_flags"} <= set(summary), "")
    add("status_checks_list", isinstance(checks, list), type(checks).__name__)
    if isinstance(checks, list):
        add("status_checks_total_matches", summary.get("total") == len(checks), str(summary.get("total")))


def verify_risk_summary(risk_summary: dict[str, Any], add: Any) -> None:
    add("risk_summary_schema", risk_summary.get("schema_version") == SCHEMA_VERSION, risk_summary.get("schema_version", ""))
    required = {
        "risk_level",
        "risk_flags",
        "risk_reasons",
        "adversarial_traps",
        "status_check_results",
        "file_diff_summary",
    }
    add("risk_summary_required_fields", required <= set(risk_summary), ",".join(sorted(required - set(risk_summary))))
    add("risk_summary_level_allowed", risk_summary.get("risk_level") in {"low", "needs_review"}, risk_summary.get("risk_level", ""))


def verify_review_outcome(review_outcome: dict[str, Any], add: Any) -> None:
    add("review_outcome_schema", review_outcome.get("schema_version") == SCHEMA_VERSION, review_outcome.get("schema_version", ""))
    required = {
        "status",
        "allowed_decisions",
        "recommended_starting_decision",
        "reviewer_decision",
        "reviewer_notes",
        "decision_prompts",
        "evidence_references",
    }
    add("review_outcome_required_fields", required <= set(review_outcome), ",".join(sorted(required - set(review_outcome))))
    add("review_outcome_status_unrecorded", review_outcome.get("status") == "unrecorded", review_outcome.get("status", ""))
    add(
        "review_outcome_allowed_decisions",
        {"accept", "reject", "request_changes", "needs_followup"} <= set(review_outcome.get("allowed_decisions") or []),
        ",".join(review_outcome.get("allowed_decisions") or []),
    )
    add("review_outcome_prompts_present", bool(review_outcome.get("decision_prompts")), "")
    add("review_outcome_references_packet", "reviewer_packet.md" in set(review_outcome.get("evidence_references") or []), "")


def normalize_pr_metadata(metadata: dict[str, Any], repo: str, generated_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "repo": repo,
        "number": metadata["number"],
        "title": metadata.get("title", ""),
        "url": metadata.get("url", ""),
        "state": metadata.get("state", ""),
        "author": (metadata.get("author") or {}).get("login", ""),
        "base_ref": metadata.get("baseRefName", ""),
        "head_ref": metadata.get("headRefName", ""),
        "changed_files": metadata.get("changedFiles", 0),
        "additions": metadata.get("additions", 0),
        "deletions": metadata.get("deletions", 0),
        "review_decision": metadata.get("reviewDecision", ""),
        "created_at": metadata.get("createdAt", ""),
        "updated_at": metadata.get("updatedAt", ""),
        "body": metadata.get("body") or "",
        "commit_count": len(metadata.get("commits") or []),
        "status_check_count": len(metadata.get("statusCheckRollup") or []),
    }


def build_changed_files(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "files": [
            {
                "path": file_path(file_info),
                "additions": file_info.get("additions", 0),
                "deletions": file_info.get("deletions", 0),
                "risk_flags": file_risk_flags(file_path(file_info)),
            }
            for file_info in metadata.get("files", [])
        ],
    }


def file_path(file_info: dict[str, Any]) -> str:
    return file_info.get("path") or file_info.get("filename") or ""


def build_file_diffs(metadata: dict[str, Any]) -> dict[str, Any]:
    files = metadata.get("files") or []
    entries = [normalize_file_diff(file_info) for file_info in files[:MAX_DIFF_FILES]]
    omitted_files = max(0, len(files) - len(entries))
    return {
        "schema_version": SCHEMA_VERSION,
        "limits": {
            "max_files": MAX_DIFF_FILES,
            "max_patch_lines_per_file": MAX_PATCH_LINES_PER_FILE,
        },
        "summary": {
            "files_with_patch": sum(1 for entry in entries if entry["patch_present"]),
            "files_without_patch": sum(1 for entry in entries if not entry["patch_present"]),
            "files_omitted": omitted_files,
            "patches_truncated": sum(1 for entry in entries if entry["patch_truncated"]),
        },
        "files": entries,
    }


def normalize_file_diff(file_info: dict[str, Any]) -> dict[str, Any]:
    patch = file_info.get("patch") or ""
    lines = patch.splitlines()
    excerpt = lines[:MAX_PATCH_LINES_PER_FILE]
    return {
        "path": file_path(file_info),
        "status": file_info.get("status", ""),
        "additions": file_info.get("additions", 0),
        "deletions": file_info.get("deletions", 0),
        "changes": file_info.get("changes", file_info.get("additions", 0) + file_info.get("deletions", 0)),
        "patch_present": bool(patch),
        "patch_excerpt": excerpt,
        "patch_line_count": len(lines),
        "patch_truncated": len(lines) > len(excerpt),
    }


def build_status_checks(metadata: dict[str, Any]) -> dict[str, Any]:
    checks = [
        normalize_status_check(check)
        for check in metadata.get("statusCheckRollup") or []
    ]
    summary = summarize_status_checks(checks)
    return {
        "schema_version": SCHEMA_VERSION,
        "summary": summary,
        "checks": checks,
    }


def normalize_status_check(check: dict[str, Any]) -> dict[str, Any]:
    conclusion = normalized_text(check.get("conclusion"))
    status = normalized_text(check.get("status"))
    state = normalized_text(check.get("state"))
    normalized_result = conclusion or state or status or "unknown"
    return {
        "name": check.get("name") or check.get("context") or check.get("workflowName") or "unnamed check",
        "conclusion": conclusion,
        "status": status,
        "state": state,
        "result": normalized_result,
        "url": check.get("url") or check.get("detailsUrl") or "",
        "risk_flags": status_check_risk_flags(normalized_result),
    }


def normalized_text(value: Any) -> str:
    return str(value or "").strip().lower()


def status_check_risk_flags(result: str) -> list[str]:
    if not result:
        return ["unknown_status"]
    if result in {"success"}:
        return []
    if result in {"failure", "failed", "error", "cancelled", "timed_out", "action_required"}:
        return ["status_check_failed"]
    if result in {"pending", "queued", "in_progress", "waiting", "requested"}:
        return ["status_check_incomplete"]
    if result in {"neutral", "skipped", "stale", "unknown"}:
        return ["status_check_needs_interpretation"]
    return ["status_check_needs_interpretation"]


def summarize_status_checks(checks: list[dict[str, Any]]) -> dict[str, Any]:
    results: dict[str, int] = {}
    risk_flags = sorted({flag for check in checks for flag in check["risk_flags"]})
    for check in checks:
        result = check["result"]
        results[result] = results.get(result, 0) + 1
    return {
        "total": len(checks),
        "results": results,
        "risk_flags": risk_flags,
    }


def build_risk_summary(
    metadata: dict[str, Any],
    changed_files: dict[str, Any],
    file_diffs: dict[str, Any],
    status_checks: dict[str, Any],
) -> dict[str, Any]:
    files = changed_files["files"]
    flags = sorted({flag for file_info in files for flag in file_info["risk_flags"]})
    high_risk_flags = sorted(set(flags) & HIGH_RISK_FILE_FLAGS)
    review_decision = metadata.get("reviewDecision") or ""
    reported_changed_files = metadata.get("changedFiles", 0)
    additions = metadata.get("additions", 0)
    deletions = metadata.get("deletions", 0)
    risk_reasons = pr_risk_reasons(metadata, files, high_risk_flags, file_diffs, status_checks, review_decision)
    adversarial_traps = pr_adversarial_traps(risk_reasons)
    risk_level = "needs_review" if risk_reasons else "low"
    return {
        "schema_version": SCHEMA_VERSION,
        "risk_level": risk_level,
        "risk_flags": flags,
        "risk_reasons": risk_reasons,
        "adversarial_traps": adversarial_traps,
        "review_decision": review_decision,
        "status_check_count": status_checks["summary"]["total"],
        "status_check_results": status_checks["summary"]["results"],
        "status_check_risk_flags": status_checks["summary"]["risk_flags"],
        "file_diff_summary": file_diffs["summary"],
        "changed_file_count": len(files),
        "reported_changed_file_count": reported_changed_files,
        "additions": additions,
        "deletions": deletions,
        "recommended_action": "inspect reviewer_packet.md before trusting this PR",
    }


def build_review_outcome_template(
    pr_metadata: dict[str, Any],
    risk_summary: dict[str, Any],
    generated_at: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": "unrecorded",
        "repo": pr_metadata["repo"],
        "pr_number": pr_metadata["number"],
        "pr_url": pr_metadata["url"],
        "allowed_decisions": ["accept", "reject", "request_changes", "needs_followup"],
        "recommended_starting_decision": "needs_followup"
        if risk_summary["risk_level"] == "needs_review"
        else "accept",
        "reviewer_decision": "",
        "reviewer_notes": "",
        "decision_prompts": decision_prompts_for_outcome(risk_summary),
        "evidence_references": [
            "reviewer_packet.md",
            "risk_summary.json",
            "status_checks.json",
            "file_diffs.json",
            "changed_files.json",
            "pr_metadata.json",
        ],
    }


def decision_prompts_for_outcome(risk_summary: dict[str, Any]) -> list[str]:
    prompts = [
        "Does the PR intent match the changed files and bounded diff excerpts?",
        "Do status checks provide enough evidence for the changed behavior?",
    ]
    prompts.extend(
        f"Resolve {reason}: {decision_prompt_for_reason(reason)}"
        for reason in risk_summary["risk_reasons"]
    )
    prompts.append("Record the smallest defensible outcome: accept, reject, request_changes, or needs_followup.")
    return prompts


def build_run_record(
    pr_metadata: dict[str, Any],
    risk_summary: dict[str, Any],
    generated_at: str,
    source_command: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "adapter": "github_pr_review",
        "provenance": "github_pr_review",
        "intent": f"Review PR #{pr_metadata['number']}: {pr_metadata['title']}",
        "source_command": source_command,
        "input_artifacts": ["GitHub PR metadata from gh CLI"],
        "output_artifacts": [
            "pr_metadata.json",
            "changed_files.json",
            "file_diffs.json",
            "status_checks.json",
            "risk_summary.json",
            "review_outcome.json",
            "review_request.md",
            "reviewer_packet.md",
            "commands.log",
            "artifact_manifest.json",
        ],
        "boundary": "public GitHub PR metadata only; no local secrets or private repository contents",
        "final_status": "needs_human_review"
        if risk_summary["risk_level"] == "needs_review"
        else "accepted_for_review",
    }


def build_manifest(output_dir: Path, artifact_names: Any, generated_at: str) -> dict[str, Any]:
    artifacts = []
    for name in sorted(artifact_names):
        path = output_dir / name
        artifacts.append(
            {
                "relative_path": name,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "classification": "public_metadata",
            }
        )
    return {"schema_version": SCHEMA_VERSION, "generated_at": generated_at, "artifacts": artifacts}


def render_review_request(
    pr_metadata: dict[str, Any],
    risk_summary: dict[str, Any],
    review_outcome: dict[str, Any],
) -> str:
    risk_reasons = "\n".join(f"- `{reason}`" for reason in risk_summary["risk_reasons"])
    risk_reasons = risk_reasons or "- No PR metadata risk reasons detected."
    return "\n".join(
        [
            f"# PR Review Request: {pr_metadata['repo']} #{pr_metadata['number']}",
            "",
            f"Title: {pr_metadata['title']}",
            f"URL: {pr_metadata['url']}",
            "",
            "## What To Inspect",
            "",
            "- `reviewer_packet.md` - one-page review queue item",
            "- `review_outcome.json` - unrecorded outcome worksheet",
            "- `risk_summary.json` - machine-readable risk reasons and trap classes",
            "- `file_diffs.json` - bounded public diff excerpts",
            "- `status_checks.json` - public status-check metadata",
            "",
            "## Question To Answer",
            "",
            "Would this PR review bundle reduce review burden, or does it add noise?",
            "",
            "If it adds noise, identify the first unsupported, noisy, or missing field.",
            "",
            "## Current Risk Reasons",
            "",
            risk_reasons,
            "",
            "## Where To Record The Outcome",
            "",
            "`review_outcome.json` is intentionally generated with `status: \"unrecorded\"`.",
            f"Recommended starting decision: `{review_outcome['recommended_starting_decision']}`.",
            "",
            "Allowed reviewer decisions:",
            "",
            *[f"- `{decision}`" for decision in review_outcome["allowed_decisions"]],
            "",
            "## Useful Response Format",
            "",
            "```text",
            "Does this reduce review burden? yes / no / unclear",
            "First unsupported, noisy, or missing thing:",
            "Smallest suggested change:",
            "Severity: blocker / important / minor",
            "```",
            "",
        ]
    )


def file_risk_flags(path: str) -> list[str]:
    flags: list[str] = []
    lowered = path.lower()
    if lowered.startswith(".github/") or "workflow" in lowered:
        flags.append("ci_or_automation")
    if any(part in lowered for part in ("security", "auth", "policy", "secret")):
        flags.append("security_or_policy")
    if lowered.endswith((".py", ".js", ".ts", ".go", ".rs", ".java")):
        flags.append("source_code")
    if lowered.endswith((".md", ".rst", ".txt")):
        flags.append("documentation")
    return flags


def pr_risk_reasons(
    metadata: dict[str, Any],
    files: list[dict[str, Any]],
    high_risk_flags: list[str],
    file_diffs: dict[str, Any],
    status_checks: dict[str, Any],
    review_decision: str,
) -> list[str]:
    reasons: list[str] = []
    reported_changed_files = metadata.get("changedFiles", 0)
    additions = metadata.get("additions", 0)
    deletions = metadata.get("deletions", 0)
    if high_risk_flags:
        reasons.append("high_risk_file_class_changed")
    status_summary = status_checks["summary"]
    if status_summary["total"] == 0:
        reasons.append("status_checks_missing")
    elif status_summary["risk_flags"]:
        reasons.append("status_checks_not_successful")
    if review_decision in {"CHANGES_REQUESTED", "REVIEW_REQUIRED"}:
        reasons.append("review_decision_requires_attention")
    if intent_is_vague(metadata.get("title", ""), metadata.get("body") or ""):
        reasons.append("intent_too_vague_for_review")
    if reported_changed_files > len(files):
        reasons.append("changed_file_metadata_incomplete")
    if file_diffs["summary"]["files_without_patch"] or file_diffs["summary"]["files_omitted"]:
        reasons.append("diff_context_incomplete")
    if reported_changed_files > LARGE_CHANGE_FILE_COUNT or additions + deletions > LARGE_CHANGE_LINE_COUNT:
        reasons.append("large_change_set")
    return reasons


def intent_is_vague(title: str, body: str) -> bool:
    title_words = [word for word in title.strip().split() if word]
    body_words = [word for word in body.strip().split() if word]
    generic_titles = {
        "update",
        "updates",
        "fix",
        "fixes",
        "changes",
        "misc",
        "cleanup",
        "wip",
    }
    return (
        len(title_words) < 3
        or title.strip().lower() in generic_titles
        or len(body_words) < 5
    )


def pr_adversarial_traps(risk_reasons: list[str]) -> list[str]:
    trap_by_reason = {
        "status_checks_missing": "missing_checks_requires_review",
        "status_checks_not_successful": "non_successful_checks_require_review",
        "review_decision_requires_attention": "review_required_blocks_trust",
        "intent_too_vague_for_review": "vague_pr_intent_blocks_review_judgment",
        "changed_file_metadata_incomplete": "incomplete_file_metadata_requires_review",
        "diff_context_incomplete": "incomplete_diff_context_requires_review",
        "large_change_set": "large_diff_requires_review",
        "high_risk_file_class_changed": "sensitive_pr_surface_requires_review",
    }
    return sorted({trap_by_reason[reason] for reason in risk_reasons if reason in trap_by_reason})


def render_reviewer_packet(
    pr_metadata: dict[str, Any],
    changed_files: dict[str, Any],
    file_diffs: dict[str, Any],
    status_checks: dict[str, Any],
    risk_summary: dict[str, Any],
) -> str:
    file_lines = "\n".join(
        f"- `{file_info['path']}` (+{file_info['additions']}/-{file_info['deletions']})"
        + (f" flags: {', '.join(file_info['risk_flags'])}" if file_info["risk_flags"] else "")
        for file_info in changed_files["files"]
    )
    file_lines = file_lines or "- No changed files reported by GitHub metadata."
    reason_lines = "\n".join(f"- `{reason}`" for reason in risk_summary["risk_reasons"])
    reason_lines = reason_lines or "- No PR metadata risk reasons detected."
    trap_lines = "\n".join(f"- `{trap}`" for trap in risk_summary["adversarial_traps"])
    trap_lines = trap_lines or "- No PR-review trap classes detected."
    checklist_lines = render_decision_checklist(risk_summary, file_diffs, status_checks)
    diff_lines = render_file_diff_lines(file_diffs)
    status_check_lines = render_status_check_lines(status_checks)
    return "\n".join(
        [
            f"# PR Review Packet: {pr_metadata['repo']} #{pr_metadata['number']}",
            "",
            f"Title: {pr_metadata['title']}",
            f"URL: {pr_metadata['url']}",
            f"State: {pr_metadata['state']}",
            f"Author: {pr_metadata['author']}",
            f"Base/head: `{pr_metadata['base_ref']}` <- `{pr_metadata['head_ref']}`",
            "",
            "## Risk Summary",
            "",
            f"- Risk level: `{risk_summary['risk_level']}`",
            f"- Review decision: `{risk_summary['review_decision'] or 'none'}`",
            f"- Status checks observed: {risk_summary['status_check_count']}",
            f"- Status check results: {format_counts(risk_summary['status_check_results'])}",
            f"- Diff excerpts observed/omitted/truncated: {risk_summary['file_diff_summary']['files_with_patch']}/{risk_summary['file_diff_summary']['files_omitted']}/{risk_summary['file_diff_summary']['patches_truncated']}",
            f"- Changed files observed/reported: {risk_summary['changed_file_count']}/{risk_summary['reported_changed_file_count']}",
            f"- Additions/deletions: +{risk_summary['additions']}/-{risk_summary['deletions']}",
            f"- Risk flags: {', '.join(risk_summary['risk_flags']) or 'none'}",
            "",
            "## Risk Reasons",
            "",
            reason_lines,
            "",
            "## PR-Review Trap Classes",
            "",
            trap_lines,
            "",
            "## Review Decision Checklist",
            "",
            checklist_lines,
            "",
            "## Changed Files",
            "",
            file_lines,
            "",
            "## Diff Excerpts",
            "",
            diff_lines,
            "",
            "## Status Checks",
            "",
            status_check_lines,
            "",
            "## Reviewer Questions",
            "",
            "- Does the PR title/body state an intent specific enough to compare against the file list?",
            "- Do changed files match the stated intent?",
            "- Do the bounded diff excerpts support the stated intent?",
            "- Are CI, automation, security, auth, or policy files changed?",
            "- Are status checks present and sufficient for the change type?",
            "- What rollback boundary is realistic for this PR?",
            "",
        ]
    )


def render_decision_checklist(
    risk_summary: dict[str, Any],
    file_diffs: dict[str, Any],
    status_checks: dict[str, Any],
) -> str:
    lines = [
        "- [ ] Compare the PR title/body against `pr_metadata.json`, `changed_files.json`, and the diff excerpts.",
    ]
    if risk_summary["risk_reasons"]:
        lines.extend(
            f"- [ ] Resolve `{reason}`: {decision_prompt_for_reason(reason)}"
            for reason in risk_summary["risk_reasons"]
        )
    else:
        lines.append("- [ ] Confirm no metadata risk reason is hiding a product, security, or test-coverage concern.")

    status_summary = status_checks["summary"]
    if status_summary["total"] == 0:
        lines.append("- [ ] Decide whether missing status checks are acceptable before trusting the run.")
    elif status_summary["risk_flags"]:
        lines.append("- [ ] Inspect non-successful or incomplete status checks before accepting the PR.")
    else:
        lines.append("- [ ] Confirm successful status checks cover the changed behavior, not only import or smoke paths.")

    diff_summary = file_diffs["summary"]
    if diff_summary["files_without_patch"] or diff_summary["files_omitted"] or diff_summary["patches_truncated"]:
        lines.append("- [ ] Open the PR on GitHub for any missing, omitted, or truncated diff context.")
    else:
        lines.append("- [ ] Inspect each bounded diff excerpt and decide whether it is enough for this review.")

    lines.append("- [ ] Record one outcome: accept, reject, request changes, or request a narrower follow-up run.")
    return "\n".join(lines)


def decision_prompt_for_reason(reason: str) -> str:
    prompts = {
        "high_risk_file_class_changed": "inspect CI, automation, security, auth, or policy changes directly.",
        "status_checks_missing": "require a human decision because no check evidence was reported.",
        "status_checks_not_successful": "read failed, pending, skipped, or ambiguous check results.",
        "review_decision_requires_attention": "honor existing requested changes or required review state.",
        "intent_too_vague_for_review": "ask for a narrower PR intent before trusting metadata alignment.",
        "changed_file_metadata_incomplete": "compare GitHub's reported file count with the observed file list.",
        "diff_context_incomplete": "inspect missing patches or omitted files outside the bounded packet.",
        "large_change_set": "split or perform a deeper review before trusting the bundle.",
    }
    return prompts.get(reason, "inspect the underlying artifact before accepting the PR.")


def render_file_diff_lines(file_diffs: dict[str, Any]) -> str:
    if not file_diffs["files"]:
        return "- No file diffs reported by GitHub metadata."
    sections = []
    for file_info in file_diffs["files"]:
        header = f"### `{file_info['path']}`"
        meta = (
            f"- Status: `{file_info['status'] or 'unknown'}`; "
            f"additions/deletions: +{file_info['additions']}/-{file_info['deletions']}; "
            f"patch lines shown/total: {len(file_info['patch_excerpt'])}/{file_info['patch_line_count']}"
        )
        if not file_info["patch_present"]:
            body = "_No patch excerpt was reported by GitHub metadata._"
        else:
            body = "\n".join(["```diff", *file_info["patch_excerpt"], "```"])
            if file_info["patch_truncated"]:
                body += "\n\n_Patch excerpt truncated._"
        sections.append("\n".join([header, "", meta, "", body]))
    if file_diffs["summary"]["files_omitted"]:
        sections.append(f"_Omitted {file_diffs['summary']['files_omitted']} file(s) beyond the configured limit._")
    return "\n\n".join(sections)


def render_status_check_lines(status_checks: dict[str, Any]) -> str:
    if not status_checks["checks"]:
        return "- No status checks reported by GitHub metadata."
    lines = [status_check_interpretation(status_checks)]
    for check in status_checks["checks"]:
        fields = [f"result: `{check['result']}`"]
        if check["conclusion"]:
            fields.append(f"conclusion: `{check['conclusion']}`")
        if check["status"]:
            fields.append(f"status: `{check['status']}`")
        if check["state"]:
            fields.append(f"state: `{check['state']}`")
        if check["risk_flags"]:
            fields.append(f"flags: {', '.join(check['risk_flags'])}")
        if check["url"]:
            fields.append(f"url: {check['url']}")
        lines.append(f"- `{check['name']}` " + "; ".join(fields))
    return "\n".join(lines)


def status_check_interpretation(status_checks: dict[str, Any]) -> str:
    summary = status_checks["summary"]
    if summary["total"] == 0:
        return "- Interpretation: no status-check evidence was reported."
    if summary["risk_flags"]:
        return "- Interpretation: at least one reported check is failed, incomplete, or ambiguous."
    return "- Interpretation: reported checks are successful, but they are not proof that the changed behavior was reviewed."


def format_counts(counts: dict[str, int]) -> str:
    if not counts:
        return "none"
    return ", ".join(f"{name}={count}" for name, count in sorted(counts.items()))


def render_commands_log(source_command: list[str]) -> str:
    return "source_command: " + " ".join(source_command) + "\n"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
