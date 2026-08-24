"""Verify public-safe synthetic Agent Evidence Recorder sample artifacts."""

from __future__ import annotations

import json
import re
import subprocess
from hashlib import sha256
from pathlib import Path, PurePosixPath

from agent_evidence_recorder.pr_review import verify_pr_review_bundle

REQUIRED_RUN_RECORD_FIELDS = {
    "run_id",
    "intent",
    "producer",
    "adapter",
    "provenance",
    "replay_command",
    "input_artifacts",
    "output_artifacts",
    "generation_steps",
    "tool_or_model_steps",
    "environment_boundary",
    "execution_limits",
    "effect_boundary",
    "failure_capture",
    "verification_notes",
    "final_status",
}
REQUIRED_MANIFEST_FIELDS = {
    "root_label",
    "relative_path",
    "artifact_role",
    "classification",
    "sha256",
    "byte_size",
    "generated_by",
    "included_in_replay",
    "included_in_rollback",
}
ALLOWED_ROOT_LABELS = {"target_repo", "run_store"}
ALLOWED_CLASSIFICATIONS = {
    "input",
    "generated",
    "derived_report",
    "review_surface",
    "verification_output",
    "excluded_recursive_artifact",
}
REQUIRED_RUN_ARTIFACTS = {
    "run_record.json",
    "artifact_manifest.json",
    "trace.jsonl",
    "commands.log",
    "git.diff",
    "sample_verification.json",
    "sample_policy.json",
    "policy_gate_report.json",
    "human_escalation_record.json",
    "loop_stage_summary.json",
    "kill_switch_boundary.md",
    "evidence_packet.md",
    "review_packet.md",
    "rollback.sh",
}
ALLOWED_LOOP_STAGES = {"purpose", "sense", "interpret", "decide", "orchestrate", "learn"}
EXPECTED_RUN_STATUSES = {
    "agent_evidence-sample-run": "accepted",
    "agent_evidence-sample-run-rejected": "rejected",
    "agent_evidence-sample-run-escalated": "needs_human_review",
    "agent_evidence-sample-run-blocked": "blocked",
    "agent_evidence-sample-run-vague": "needs_human_review",
    "agent_evidence-sample-run-live-envelope": "blocked",
}
EXPECTED_RUN_PROVENANCE = {
    "agent_evidence-sample-run": "synthetic_sample",
    "agent_evidence-sample-run-rejected": "synthetic_sample",
    "agent_evidence-sample-run-escalated": "synthetic_sample",
    "agent_evidence-sample-run-blocked": "synthetic_sample",
    "agent_evidence-sample-run-vague": "synthetic_sample",
    "agent_evidence-sample-run-live-envelope": "synthetic_live_envelope",
}
ALLOWED_RUN_PROVENANCE = {"synthetic_sample", "synthetic_live_envelope", "github_pr_review"}
ALLOWED_FILE_EFFECTS = {"read_file", "create_file", "modify_file", "no_op"}
DISALLOWED_NON_FILE_EFFECTS = {
    "network_call",
    "external_api_call",
    "deploy",
    "publish",
    "browser_automation",
    "cloud_operation",
    "hardware_access",
    "payment",
}
PR_REVIEW_SAMPLE_ID = "agent_evidence-pr-review-sample"
PR_REVIEW_LOW_RISK_DOCS_ID = "agent_evidence-pr-review-low-risk-docs"
PR_REVIEW_ADVERSARIAL_ID = "agent_evidence-pr-review-adversarial"
REQUIRED_PR_REVIEW_SAMPLE_ARTIFACTS = {
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
    "sample_verification.json",
    "status_checks.json",
}
REQUIRED_ADVERSARIAL_TRAPS = {
    "verification_failed_but_evidence_retained": {
        "failure_class": "verification_failure",
        "expected_policy_status": "verification_failed",
        "expected_final_status": "rejected",
    },
    "policy_sensitive_file_changed": {
        "failure_class": "policy_sensitive_change",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    "verification_passed_but_forbidden_effect_requested": {
        "failure_class": "forbidden_effect",
        "expected_policy_status": "blocked",
        "expected_final_status": "blocked",
    },
    "rollback_claim_limited_to_recorded_diff": {
        "failure_class": "rollback_overclaim",
        "expected_policy_status": "blocked",
        "expected_final_status": "blocked",
    },
    "trust_not_granted_by_verification_alone": {
        "failure_class": "verification_overtrust",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    "vague_intent_blocks_review_judgment": {
        "failure_class": "vague_intent",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    "unrelated_diff_requires_review": {
        "failure_class": "unrelated_diff",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    "weak_provenance_requires_review": {
        "failure_class": "weak_provenance",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    "stale_evidence_requires_review": {
        "failure_class": "stale_evidence",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
}
ALLOWED_ADVERSARIAL_SEVERITIES = {"blocker", "important", "minor"}
SKIPPED_PUBLIC_SURFACE_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    "build",
    "dist",
}
SKIPPED_PUBLIC_SURFACE_SUFFIXES = {
    ".pyc",
    ".pyo",
}


def skipped_public_surface_path(relative_path: Path) -> bool:
    return (
        any(part in SKIPPED_PUBLIC_SURFACE_PARTS or part.endswith("-vault") for part in relative_path.parts)
        or relative_path.suffix in SKIPPED_PUBLIC_SURFACE_SUFFIXES
    )


def blocked_terms() -> list[str]:
    return [
        "/" + "home" + "/",
        "/" + "Users" + "/",
        "onyx-" + "citadel",
        "strategy-" + "vault",
        "_" + "scratch",
        "Hermetic" + "_QA_Artifacts",
    ]


def unsupported_phrases() -> list[str]:
    return [
        "guaran" + "teed " + "rollback",
        "provides " + "complete " + "rollback",
        "deterministic model " + "reasoning",
        "is " + "production " + "safe",
        "production-" + "safe",
        "safe " + "for " + "production",
        "affili" + "ated",
        "endors" + "ed",
    ]


def key_like_patterns() -> list[re.Pattern[str]]:
    return [
        re.compile(r"gh[opsru]_[A-Za-z0-9_]{8,}"),
        re.compile(r"sk-[A-Za-z0-9]{8,}"),
        re.compile(r"-----BEGIN [A-Z ]{0,24}KEY-----"),
    ]


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def relative_artifact_path(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return str(value.get("relative_path", ""))
    return ""


def sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def unsafe_artifact_path_reason(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "empty"
    if value.startswith(("~", "/", "\\")):
        return "absolute_or_home"
    if "\\" in value:
        return "backslash"
    if re.match(r"^[A-Za-z]:", value):
        return "drive_absolute"
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        return "traversal"
    if "/" + "home" + "/" in value or "/" + "Users" + "/" in value:
        return "machine_local"
    return ""


def resolve_manifest_entry(samples: Path, run_dir: Path, entry: dict) -> Path | None:
    roots = {
        "target_repo": samples / "sample-target-repo",
        "run_store": run_dir,
    }
    root = roots.get(str(entry.get("root_label", "")))
    rel = str(entry.get("relative_path", ""))
    if root is None or unsafe_artifact_path_reason(rel):
        return None
    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None
    return candidate


def manifest_relative_for_run_record(run_dir: Path, section: str, relative_path: str) -> tuple[str, str] | None:
    prefixes = {
        "input_artifacts": ("target_repo", "samples/sample-target-repo/"),
        "output_artifacts": ("run_store", f"samples/{run_dir.name}/"),
    }
    root_label, prefix = prefixes[section]
    if not relative_path.startswith(prefix):
        return None
    return root_label, relative_path.removeprefix(prefix)


def public_surface_issues(paths: list[Path]) -> list[str]:
    issues: list[str] = []
    needles = blocked_terms() + unsupported_phrases()
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for needle in needles:
            if needle.lower() in text.lower():
                issues.append(f"{path}: blocked phrase {needle}")
        for pattern in key_like_patterns():
            if pattern.findall(text):
                issues.append(f"{path}: key-shaped value")
    return issues


def tracked_public_surface_paths(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        relative_paths = [Path(line) for line in result.stdout.splitlines() if line.strip()]
    except (FileNotFoundError, subprocess.CalledProcessError):
        relative_paths = [
            path.relative_to(root)
            for path in root.rglob("*")
            if path.is_file()
            and not skipped_public_surface_path(path.relative_to(root))
        ]

    paths: list[Path] = []
    for relative_path in relative_paths:
        if skipped_public_surface_path(relative_path):
            continue
        path = root / relative_path
        if path.is_file():
            paths.append(path)
    return paths


def verify_run(run_dir: Path, expected_status: str) -> list[dict]:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": f"{run_dir.name}:{name}", "passed": passed, "detail": detail})

    add("directory_present", run_dir.is_dir(), str(run_dir))
    if not run_dir.is_dir():
        return checks

    artifact_names = {path.name for path in run_dir.iterdir() if path.is_file()}
    add("required_artifacts_present", REQUIRED_RUN_ARTIFACTS <= artifact_names, ",".join(sorted(artifact_names)))

    run_record = read_json(run_dir / "run_record.json")
    missing = REQUIRED_RUN_RECORD_FIELDS - set(run_record)
    add("run_record_required_fields", not missing, ",".join(sorted(missing)))
    add("synthetic_adapter_truth", run_record.get("adapter") == "synthetic_sample", str(run_record.get("adapter")))
    add(
        "provenance_enum",
        run_record.get("provenance") in ALLOWED_RUN_PROVENANCE,
        str(run_record.get("provenance")),
    )
    expected_provenance = EXPECTED_RUN_PROVENANCE.get(run_dir.name)
    add("provenance_expected", run_record.get("provenance") == expected_provenance, str(run_record.get("provenance")))
    add("final_status_expected", run_record.get("final_status") == expected_status, str(run_record.get("final_status")))
    execution_limits = run_record.get("execution_limits") or {}
    cost_budget = execution_limits.get("cost_budget") or {}
    add(
        "execution_timeout_recorded",
        isinstance(execution_limits.get("timeout_seconds"), int) and execution_limits.get("timeout_seconds") > 0,
        str(execution_limits.get("timeout_seconds")),
    )
    add(
        "execution_cost_budget_recorded",
        cost_budget.get("maximum") == 0 and cost_budget.get("actual") == 0,
        json.dumps(cost_budget, sort_keys=True),
    )
    add(
        "execution_provider_account_not_required",
        cost_budget.get("provider_account_required") is False,
        str(cost_budget.get("provider_account_required")),
    )

    boundary = run_record.get("effect_boundary") or {}
    observed_effects = boundary.get("observed_effects") or []
    requested_non_file_effects = boundary.get("requested_non_file_effects") or []
    effect_errors: list[str] = []
    if boundary.get("schema_version") != "agent_evidence_recorder.effect_boundary.v0":
        effect_errors.append(f"schema_version:{boundary.get('schema_version')}")
    if boundary.get("boundary_type") != "file_scoped_synthetic":
        effect_errors.append(f"boundary_type:{boundary.get('boundary_type')}")
    if set(boundary.get("allowed_effects") or []) != ALLOWED_FILE_EFFECTS:
        effect_errors.append(f"allowed_effects:{boundary.get('allowed_effects')}")
    if not DISALLOWED_NON_FILE_EFFECTS <= set(boundary.get("disallowed_effects") or []):
        effect_errors.append(f"disallowed_effects:{boundary.get('disallowed_effects')}")
    if boundary.get("non_file_effects_allowed") is not False:
        effect_errors.append(f"non_file_effects_allowed:{boundary.get('non_file_effects_allowed')}")
    if boundary.get("provider_calls_allowed") is not False:
        effect_errors.append(f"provider_calls_allowed:{boundary.get('provider_calls_allowed')}")
    if boundary.get("external_effects_rollbackable") is not False:
        effect_errors.append(f"external_effects_rollbackable:{boundary.get('external_effects_rollbackable')}")
    if boundary.get("rollback_scope") != "recorded_git_diff_only":
        effect_errors.append(f"rollback_scope:{boundary.get('rollback_scope')}")
    for index, effect in enumerate(observed_effects):
        effect_type = str(effect.get("effect_type", ""))
        path = str(effect.get("path", ""))
        reason = unsafe_artifact_path_reason(path)
        if effect_type not in ALLOWED_FILE_EFFECTS - {"no_op"}:
            effect_errors.append(f"observed:{index}:effect_type:{effect_type}")
        if effect.get("file_scoped") is not True:
            effect_errors.append(f"observed:{index}:file_scoped:{effect.get('file_scoped')}")
        if reason:
            effect_errors.append(f"observed:{index}:path:{path}:{reason}")
        if effect.get("rollback_scope") != "recorded_git_diff":
            effect_errors.append(f"observed:{index}:rollback_scope:{effect.get('rollback_scope')}")
    for index, effect in enumerate(requested_non_file_effects):
        effect_type = str(effect.get("effect_type", ""))
        if effect_type not in DISALLOWED_NON_FILE_EFFECTS:
            effect_errors.append(f"requested:{index}:effect_type:{effect_type}")
        if effect.get("status") != "blocked":
            effect_errors.append(f"requested:{index}:status:{effect.get('status')}")
    add("effect_boundary_contract", not effect_errors, ";".join(effect_errors))

    failure_capture = run_record.get("failure_capture") or {}
    required_failure_fields = {
        "timeout_observed",
        "cost_budget_exceeded",
        "provider_refusal_observed",
        "partial_output_observed",
        "verifier_failure_observed",
        "failure_class",
        "recorded_evidence",
    }
    missing_failure_fields = required_failure_fields - set(failure_capture)
    add(
        "failure_capture_required_fields",
        not missing_failure_fields,
        ",".join(sorted(missing_failure_fields)),
    )
    expected_failure_class = {
        "accepted": "none",
        "rejected": "verifier_failure",
        "needs_human_review": None,
        "blocked": {"forbidden_effect_requested", "input_rejected"},
    }[expected_status]
    if expected_status == "needs_human_review":
        allowed = {"policy_review_required", "review_judgment_blocked"}
        add(
            "failure_capture_class_expected",
            failure_capture.get("failure_class") in allowed,
            str(failure_capture.get("failure_class")),
        )
    elif expected_status == "blocked":
        add(
            "failure_capture_class_expected",
            failure_capture.get("failure_class") in expected_failure_class,
            str(failure_capture.get("failure_class")),
        )
    else:
        add(
            "failure_capture_class_expected",
            failure_capture.get("failure_class") == expected_failure_class,
            str(failure_capture.get("failure_class")),
        )
    add(
        "failure_capture_verifier_failure_matches_status",
        bool(failure_capture.get("verifier_failure_observed")) == (expected_status == "rejected"),
        str(failure_capture.get("verifier_failure_observed")),
    )

    path_errors: list[str] = []
    for section in ("input_artifacts", "output_artifacts"):
        for artifact in run_record.get(section, []):
            rel = relative_artifact_path(artifact)
            reason = unsafe_artifact_path_reason(rel)
            if reason:
                path_errors.append(f"{section}:{rel}:{reason}")
    add("run_record_paths_relative", not path_errors, ",".join(path_errors))

    manifest = read_json(run_dir / "artifact_manifest.json")
    manifest_errors: list[str] = []
    manifest_entries = [entry for entry in manifest.get("entries", []) if isinstance(entry, dict)]
    manifest_entry_keys: set[tuple[str, str]] = set()
    manifest_integrity_errors: list[str] = []
    rollback_entries: list[str] = []
    samples = run_dir.parent
    for index, entry in enumerate(manifest_entries):
        missing_entry_fields = REQUIRED_MANIFEST_FIELDS - set(entry)
        if missing_entry_fields:
            manifest_errors.append(f"{index}:missing:{sorted(missing_entry_fields)}")
        root_label = str(entry.get("root_label", ""))
        if root_label not in ALLOWED_ROOT_LABELS:
            manifest_errors.append(f"{index}:root_label:{root_label}")
        if entry.get("classification") not in ALLOWED_CLASSIFICATIONS:
            manifest_errors.append(f"{index}:classification:{entry.get('classification')}")
        rel = str(entry.get("relative_path", ""))
        reason = unsafe_artifact_path_reason(rel)
        if reason:
            manifest_errors.append(f"{index}:path:{rel}:{reason}")
        else:
            manifest_entry_keys.add((root_label, rel))
        if entry.get("included_in_rollback") is True:
            rollback_entries.append(f"{root_label}:{rel}")

        path = resolve_manifest_entry(samples, run_dir, entry)
        if path is None:
            manifest_integrity_errors.append(f"{index}:unresolved:{root_label}:{rel}")
            continue
        if not path.is_file():
            manifest_integrity_errors.append(f"{index}:missing_file:{root_label}:{rel}")
            continue
        if entry.get("byte_size") != path.stat().st_size:
            manifest_integrity_errors.append(f"{index}:byte_size:{root_label}:{rel}")
        if entry.get("sha256") != sha256_file(path):
            manifest_integrity_errors.append(f"{index}:sha256:{root_label}:{rel}")
    add("manifest_contract", not manifest_errors, ";".join(manifest_errors))
    add("manifest_integrity", not manifest_integrity_errors, ";".join(manifest_integrity_errors))

    coverage_errors: list[str] = []
    for section in ("input_artifacts", "output_artifacts"):
        for artifact in run_record.get(section, []):
            rel = relative_artifact_path(artifact)
            expected_manifest_key = manifest_relative_for_run_record(run_dir, section, rel)
            if expected_manifest_key is None:
                coverage_errors.append(f"{section}:unscoped:{rel}")
            elif expected_manifest_key not in manifest_entry_keys:
                coverage_errors.append(f"{section}:missing_manifest:{rel}")
    add("run_record_artifacts_manifested", not coverage_errors, ";".join(coverage_errors))
    add("rollback_boundary_limited", rollback_entries == ["run_store:git.diff"], ",".join(rollback_entries))

    report = read_json(run_dir / "sample_verification.json")
    add("sample_verification_passed", report.get("passed") is True, str(report.get("passed")))

    policy_gate = read_json(run_dir / "policy_gate_report.json")
    expected_policy_status = {
        "accepted": "passed",
        "rejected": "verification_failed",
        "needs_human_review": "needs_human_review",
        "blocked": "blocked",
    }[expected_status]
    add(
        "policy_gate_status_expected",
        policy_gate.get("final_policy_status") == expected_policy_status,
        str(policy_gate.get("final_policy_status")),
    )
    add(
        "policy_gate_effect_boundary_matches_run_record",
        policy_gate.get("effect_boundary") == boundary,
        "policy gate effect boundary drifted from run record",
    )

    escalation_record = read_json(run_dir / "human_escalation_record.json")
    should_require_human = expected_status in {"needs_human_review", "blocked"}
    add(
        "human_escalation_expected",
        (escalation_record.get("required_reviewer_action") != "none") == should_require_human,
        str(escalation_record.get("required_reviewer_action")),
    )

    loop_stage = read_json(run_dir / "loop_stage_summary.json")
    add("loop_stage_allowed", loop_stage.get("loop_stage") in ALLOWED_LOOP_STAGES, str(loop_stage.get("loop_stage")))

    review_packet = (run_dir / "review_packet.md").read_text(encoding="utf-8")
    run_provenance = run_record.get("provenance", "")
    workflow_type = run_record.get("workflow_type", "")
    should_require_human = expected_status in {"needs_human_review", "blocked"}
    add(
        "review_packet_mentions_provenance",
        f"- Provenance: `{run_provenance}`" in review_packet,
        run_provenance,
    )
    add(
        "review_packet_mentions_workflow",
        f"- Workflow: `{workflow_type}`" in review_packet,
        workflow_type,
    )
    add(
        "review_packet_provider_call_invariant",
        "- Provider calls executed: `false`" in review_packet,
        "missing provider-call false assertion",
    )
    add(
        "review_packet_reviewer_outcome_required",
        f"- Reviewer outcome required: `{str(should_require_human).lower()}`" in review_packet,
        str(should_require_human),
    )
    add(
        "review_packet_effect_boundary",
        f"- Effect boundary: `{boundary.get('boundary_type', '')}`" in review_packet,
        str(boundary.get("boundary_type", "")),
    )
    add(
        "review_packet_non_file_effects_blocked",
        "- Non-file effects allowed: `false`" in review_packet,
        "missing non-file-effects false assertion",
    )
    add(
        "review_packet_effect_rollback_scope",
        f"- Rollback scope: `{boundary.get('rollback_scope', '')}`" in review_packet,
        str(boundary.get("rollback_scope", "")),
    )
    if workflow_type == "live_preflight_envelope":
        live_envelope = run_record.get("live_envelope") or {}
        add(
            "review_packet_live_preflight_context",
            "## Live Preflight Evidence (Synthetic)" in review_packet,
            workflow_type,
        )
        add(
            "review_packet_live_preflight_redaction_count",
            f"- Redaction count: `{live_envelope.get('redaction_count', '')}`" in review_packet,
            str(live_envelope.get("redaction_count", "")),
        )
        blocked_by_input = live_envelope.get("provider_request_sent") is False
        add(
            "review_packet_live_preflight_blocked",
            f"- Provider request blocked in preflight: `{str(blocked_by_input).lower()}`" in review_packet,
            str(blocked_by_input),
        )
        add(
            "review_packet_live_preflight_artifacts",
            (
                "samples/agent_evidence-sample-run-live-envelope/live_request_envelope.json" in review_packet
                and "samples/agent_evidence-sample-run-live-envelope/live_redaction_report.json" in review_packet
                and "samples/agent_evidence-sample-run-live-envelope/provider_request_rejection_record.json" in review_packet
            ),
            "live_request_envelope.json, live_redaction_report.json, provider_request_rejection_record.json",
        )

    issue_paths = [path for path in run_dir.iterdir() if path.is_file()]
    surface_issues = public_surface_issues(issue_paths)
    add("public_surface_terms_absent", not surface_issues, ";".join(surface_issues))
    return checks


def verify_adversarial_corpus(samples: Path) -> list[dict]:
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": f"adversarial_corpus:{name}", "passed": passed, "detail": detail})

    corpus_path = samples / "adversarial-corpus.json"
    add("present", corpus_path.is_file(), "samples/adversarial-corpus.json")
    if not corpus_path.is_file():
        return checks

    corpus = read_json(corpus_path)
    traps = {
        trap.get("trap_id"): trap
        for trap in corpus.get("traps", [])
        if isinstance(trap, dict) and trap.get("trap_id")
    }
    missing = set(REQUIRED_ADVERSARIAL_TRAPS) - set(traps)
    add("required_traps_present", not missing, ",".join(sorted(missing)))

    invalid: list[str] = []
    for trap_id, expected in REQUIRED_ADVERSARIAL_TRAPS.items():
        trap = traps.get(trap_id, {})
        if trap.get("failure_class") != expected["failure_class"]:
            invalid.append(f"{trap_id}:failure_class:{trap.get('failure_class')}")
        if trap.get("expected_policy_status") != expected["expected_policy_status"]:
            invalid.append(f"{trap_id}:policy:{trap.get('expected_policy_status')}")
        if trap.get("expected_final_status") != expected["expected_final_status"]:
            invalid.append(f"{trap_id}:status:{trap.get('expected_final_status')}")
        run_id = str(trap.get("run_id", ""))
        if run_id not in EXPECTED_RUN_STATUSES:
            invalid.append(f"{trap_id}:run_id:{run_id}")
        if trap.get("severity") not in ALLOWED_ADVERSARIAL_SEVERITIES:
            invalid.append(f"{trap_id}:severity:{trap.get('severity')}")
    add("trap_contract_expected", not invalid, ";".join(invalid))

    covered_statuses = {trap.get("expected_final_status") for trap in traps.values()}
    add(
        "negative_statuses_covered",
        {"rejected", "needs_human_review", "blocked"} <= covered_statuses,
        ",".join(sorted(str(status) for status in covered_statuses)),
    )

    blocker_traps = [trap_id for trap_id, trap in traps.items() if trap.get("severity") == "blocker"]
    add("blocker_traps_present", bool(blocker_traps), ",".join(sorted(blocker_traps)))
    return checks


def verify_pr_review_sample(samples: Path) -> list[dict]:
    checks: list[dict] = []
    bundle_dir = samples / PR_REVIEW_SAMPLE_ID

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": f"{PR_REVIEW_SAMPLE_ID}:{name}", "passed": passed, "detail": detail})

    add("directory_present", bundle_dir.is_dir(), f"samples/{PR_REVIEW_SAMPLE_ID}")
    if not bundle_dir.is_dir():
        return checks

    artifact_names = {path.name for path in bundle_dir.iterdir() if path.is_file()}
    missing = REQUIRED_PR_REVIEW_SAMPLE_ARTIFACTS - artifact_names
    add("required_artifacts_present", not missing, ",".join(sorted(missing)))

    bundle_report = verify_pr_review_bundle(bundle_dir)
    add("bundle_verification_passed", bundle_report["passed"], json.dumps([check for check in bundle_report["checks"] if not check["passed"]], sort_keys=True))

    sample_report = read_json(bundle_dir / "sample_verification.json")
    add("sample_verification_passed", sample_report.get("passed") is True, str(sample_report.get("passed")))

    run_record = read_json(bundle_dir / "run_record.json")
    add("adapter_truth", run_record.get("adapter") == "github_pr_review", str(run_record.get("adapter")))
    add("provenance_truth", run_record.get("provenance") == "github_pr_review", str(run_record.get("provenance")))
    add("final_status_expected", run_record.get("final_status") == "needs_human_review", str(run_record.get("final_status")))
    add("public_boundary", "public GitHub PR metadata only" in run_record.get("boundary", ""), run_record.get("boundary", ""))

    risk_summary = read_json(bundle_dir / "risk_summary.json")
    add("status_checks_missing_trap", "missing_checks_requires_review" in risk_summary.get("adversarial_traps", []), ",".join(risk_summary.get("adversarial_traps", [])))

    review_outcome = read_json(bundle_dir / "review_outcome.json")
    add("review_outcome_unrecorded", review_outcome.get("status") == "unrecorded", str(review_outcome.get("status")))
    add("review_outcome_needs_followup_start", review_outcome.get("recommended_starting_decision") == "needs_followup", str(review_outcome.get("recommended_starting_decision")))
    add("review_outcome_references_packet", "reviewer_packet.md" in review_outcome.get("evidence_references", []), ",".join(review_outcome.get("evidence_references", [])))

    review_request = (bundle_dir / "review_request.md").read_text(encoding="utf-8")
    add("review_request_question_present", "Would this PR review bundle reduce review burden" in review_request, "")
    add("review_request_points_to_outcome", "review_outcome.json" in review_request, "")

    surface_issues = public_surface_issues([path for path in bundle_dir.iterdir() if path.is_file()])
    add("public_surface_terms_absent", not surface_issues, ";".join(surface_issues))
    return checks


def verify_pr_review_adversarial(samples: Path) -> list[dict]:
    checks: list[dict] = []
    bundle_dir = samples / PR_REVIEW_ADVERSARIAL_ID

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": f"{PR_REVIEW_ADVERSARIAL_ID}:{name}", "passed": passed, "detail": detail})

    add("directory_present", bundle_dir.is_dir(), f"samples/{PR_REVIEW_ADVERSARIAL_ID}")
    if not bundle_dir.is_dir():
        return checks

    artifact_names = {path.name for path in bundle_dir.iterdir() if path.is_file()}
    missing = REQUIRED_PR_REVIEW_SAMPLE_ARTIFACTS - artifact_names
    add("required_artifacts_present", not missing, ",".join(sorted(missing)))

    bundle_report = verify_pr_review_bundle(bundle_dir)
    add("bundle_verification_passed", bundle_report["passed"], json.dumps([check for check in bundle_report["checks"] if not check["passed"]], sort_keys=True))

    sample_report = read_json(bundle_dir / "sample_verification.json")
    add("sample_verification_passed", sample_report.get("passed") is True, str(sample_report.get("passed")))

    run_record = read_json(bundle_dir / "run_record.json")
    add("provenance_truth", run_record.get("provenance") == "github_pr_review", str(run_record.get("provenance")))
    add("final_status_expected", run_record.get("final_status") == "needs_human_review", str(run_record.get("final_status")))

    status_checks = read_json(bundle_dir / "status_checks.json")
    add("status_checks_successful", status_checks.get("summary", {}).get("results") == {"success": 2}, json.dumps(status_checks.get("summary", {}).get("results"), sort_keys=True))
    add("status_checks_no_risk_flags", not status_checks.get("summary", {}).get("risk_flags"), ",".join(status_checks.get("summary", {}).get("risk_flags", [])))

    risk_summary = read_json(bundle_dir / "risk_summary.json")
    risk_reasons = set(risk_summary.get("risk_reasons", []))
    traps = set(risk_summary.get("adversarial_traps", []))
    add("high_risk_surface_requires_review", "high_risk_file_class_changed" in risk_reasons, ",".join(sorted(risk_reasons)))
    add("vague_intent_requires_review", "intent_too_vague_for_review" in risk_reasons, ",".join(sorted(risk_reasons)))
    add("sensitive_surface_trap_present", "sensitive_pr_surface_requires_review" in traps, ",".join(sorted(traps)))
    add("vague_intent_trap_present", "vague_pr_intent_blocks_review_judgment" in traps, ",".join(sorted(traps)))

    review_outcome = read_json(bundle_dir / "review_outcome.json")
    add("review_outcome_needs_followup_start", review_outcome.get("recommended_starting_decision") == "needs_followup", str(review_outcome.get("recommended_starting_decision")))

    surface_issues = public_surface_issues([path for path in bundle_dir.iterdir() if path.is_file()])
    add("public_surface_terms_absent", not surface_issues, ";".join(surface_issues))
    return checks


def verify_pr_review_low_risk_docs(samples: Path) -> list[dict]:
    checks: list[dict] = []
    bundle_dir = samples / PR_REVIEW_LOW_RISK_DOCS_ID

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": f"{PR_REVIEW_LOW_RISK_DOCS_ID}:{name}", "passed": passed, "detail": detail})

    add("directory_present", bundle_dir.is_dir(), f"samples/{PR_REVIEW_LOW_RISK_DOCS_ID}")
    if not bundle_dir.is_dir():
        return checks

    artifact_names = {path.name for path in bundle_dir.iterdir() if path.is_file()}
    missing = REQUIRED_PR_REVIEW_SAMPLE_ARTIFACTS - artifact_names
    add("required_artifacts_present", not missing, ",".join(sorted(missing)))

    bundle_report = verify_pr_review_bundle(bundle_dir)
    add("bundle_verification_passed", bundle_report["passed"], json.dumps([check for check in bundle_report["checks"] if not check["passed"]], sort_keys=True))

    sample_report = read_json(bundle_dir / "sample_verification.json")
    add("sample_verification_passed", sample_report.get("passed") is True, str(sample_report.get("passed")))

    run_record = read_json(bundle_dir / "run_record.json")
    add("final_status_expected", run_record.get("final_status") == "accepted_for_review", str(run_record.get("final_status")))
    add("provenance_truth", run_record.get("provenance") == "github_pr_review", str(run_record.get("provenance")))

    risk_summary = read_json(bundle_dir / "risk_summary.json")
    add("risk_level_low", risk_summary.get("risk_level") == "low", str(risk_summary.get("risk_level")))
    add("risk_reasons_empty", risk_summary.get("risk_reasons") == [], ",".join(risk_summary.get("risk_reasons", [])))
    add("status_checks_successful", risk_summary.get("status_check_results") == {"success": 1}, json.dumps(risk_summary.get("status_check_results"), sort_keys=True))

    review_outcome = read_json(bundle_dir / "review_outcome.json")
    add("review_outcome_accept_start", review_outcome.get("recommended_starting_decision") == "accept", str(review_outcome.get("recommended_starting_decision")))

    changed_files = read_json(bundle_dir / "changed_files.json")
    paths = [file.get("path") for file in changed_files.get("files", []) if isinstance(file, dict)]
    add("docs_only_change", paths == ["QUICKSTART.md"], ",".join(str(path) for path in paths))

    surface_issues = public_surface_issues([path for path in bundle_dir.iterdir() if path.is_file()])
    add("public_surface_terms_absent", not surface_issues, ";".join(surface_issues))
    return checks


def verify_samples(root: Path | None = None) -> dict:
    root = (root or Path.cwd()).resolve()
    samples = root / "samples"
    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    add("samples_directory_present", samples.is_dir(), "samples")
    add("target_fixture_present", (samples / "sample-target-repo" / "calculator.py").is_file())
    for run_id, expected_status in EXPECTED_RUN_STATUSES.items():
        checks.extend(verify_run(samples / run_id, expected_status))
    checks.extend(verify_pr_review_sample(samples))
    checks.extend(verify_pr_review_low_risk_docs(samples))
    checks.extend(verify_pr_review_adversarial(samples))
    checks.extend(verify_adversarial_corpus(samples))
    surface_issues = public_surface_issues(tracked_public_surface_paths(root))
    add("tracked_public_surface_terms_absent", not surface_issues, ";".join(surface_issues))

    passed = all(check["passed"] for check in checks)
    report = {"passed": passed, "checks": checks}
    if not passed:
        failed = [check for check in checks if not check["passed"]]
        raise SystemExit(json.dumps({"failed": failed}, indent=2, sort_keys=True))
    return report


def main() -> int:
    report = verify_samples()
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
