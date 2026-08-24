"""Validate and score public-safe synthetic agent run receipts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA_VERSION = "agent_evidence_recorder.agent_run_receipt.v0.1"
DEFAULT_RECEIPT_DIR = Path("samples") / "agent-run-receipts"
REQUIRED_FIELDS = {
    "schema_version",
    "receipt_id",
    "run_id",
    "repo",
    "tool",
    "model",
    "task_summary",
    "task_class",
    "prompt_tokens_estimated",
    "completion_tokens_estimated",
    "total_tokens_estimated",
    "estimated_cost_usd",
    "cost_source",
    "cost_confidence",
    "files_changed",
    "commands_run",
    "tests_run",
    "artifacts_created",
    "verification_status",
    "verification_refs",
    "evidence_packet_ref",
    "review_packet_ref",
    "artifact_manifest_ref",
    "waste_flags",
    "token_efficiency_score",
    "verified_output_per_1m_tokens",
    "next_run_recommendations",
    "non_claims",
    "privacy_boundary",
    "prompt_body_policy",
}
ALLOWED_VERIFICATION_STATUSES = {"verified", "unknown", "failed", "stale", "needs_review"}
ALLOWED_COST_CONFIDENCE = {"unknown", "low", "medium", "high"}
PROMPT_BODY_POLICY = "excluded_by_default"
PRIVACY_BOUNDARY = "public_synthetic_fixture_only"
ADVICE_NON_CLAIMS = {
    "not a billing ledger",
    "not a provider usage report",
    "not a scientific benchmark",
    "not a compliance score",
    "not an ROI claim",
    "not telemetry",
    "not a model comparison",
}
PRIVATE_MARKERS = {
    "/" + "home" + "/",
    "/" + "Users" + "/",
    "." + "env",
    "cred" + "ential",
    "private " + "key",
    "class" + "ified",
    "export-" + "controlled",
}
BASE_NON_CLAIMS = [
    "not a billing ledger",
    "not a provider usage report",
    "not a scientific benchmark",
    "not a compliance score",
    "not an ROI claim",
    "not telemetry",
    "not a model comparison",
]


def clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, value))


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def unsafe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value:
        return "empty"
    if value.startswith(("~", "/", "\\")):
        return "absolute_or_home"
    if "\\" in value:
        return "backslash"
    if len(value) > 2 and value[1] == ":":
        return "drive_absolute"
    parts = PurePosixPath(value).parts
    if any(part in {"", ".", ".."} for part in parts):
        return "traversal"
    return ""


def public_text_issues(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    lowered = text.lower()
    return [marker for marker in sorted(PRIVATE_MARKERS) if marker.lower() in lowered]


def score_receipt(receipt: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    total_tokens = int(receipt.get("total_tokens_estimated") or 0)
    verification_status = str(receipt.get("verification_status", "unknown"))
    files_changed = len(receipt.get("files_changed") or [])
    commands_run = len(receipt.get("commands_run") or [])
    tests_run = len(receipt.get("tests_run") or [])
    artifacts_created = len(receipt.get("artifacts_created") or [])
    waste_flags = list(receipt.get("waste_flags") or [])

    if total_tokens <= 0:
        warnings.append("missing_or_zero_token_estimate")
    if verification_status != "verified":
        warnings.append("verification_not_confirmed")
    if not receipt.get("evidence_packet_ref"):
        warnings.append("missing_evidence_packet_ref")
    if not receipt.get("review_packet_ref"):
        warnings.append("missing_review_packet_ref")
    if not receipt.get("artifact_manifest_ref"):
        warnings.append("missing_artifact_manifest_ref")
    if not tests_run:
        warnings.append("no_tests_recorded")
    if not files_changed and not artifacts_created:
        warnings.append("no_verified_output_recorded")

    output_units = files_changed * 18 + tests_run * 12 + artifacts_created * 8
    command_penalty = max(0, commands_run - 8) * 2
    token_penalty = min(25, total_tokens // 50_000)
    waste_penalty = len(waste_flags) * 14

    if verification_status == "verified":
        raw_score = 35 + output_units - command_penalty - token_penalty - waste_penalty
    elif verification_status == "unknown":
        raw_score = 18 + min(output_units, 10) - waste_penalty
    elif verification_status == "needs_review":
        raw_score = 24 + min(output_units, 16) - waste_penalty
    else:
        raw_score = 8 + min(output_units, 8) - waste_penalty

    token_efficiency_score = round(clamp(float(raw_score)), 2)
    verified_units = output_units if verification_status == "verified" else 0
    verified_output_per_1m_tokens = 0.0
    if total_tokens > 0:
        verified_output_per_1m_tokens = round((verified_units / total_tokens) * 1_000_000, 2)

    return {
        "receipt_id": receipt.get("receipt_id", ""),
        "schema_version": "agent_evidence_recorder.agent_run_receipt_score.v0.1",
        "score_breakdown": {
            "artifacts_created": artifacts_created,
            "commands_run": commands_run,
            "files_changed": files_changed,
            "tests_run": tests_run,
            "total_tokens_estimated": total_tokens,
            "verification_status": verification_status,
            "waste_flags": waste_flags,
        },
        "token_efficiency_score": token_efficiency_score,
        "verified_output_per_1m_tokens": verified_output_per_1m_tokens,
        "warnings": warnings,
    }


def verified_receipt() -> dict[str, Any]:
    return {
        "artifact_manifest_ref": "agent-run-receipt.codex.artifact_manifest.json",
        "artifacts_created": ["agent_run_receipt.json", "evidence_packet.md", "review_packet.md"],
        "commands_run": [
            "python3 -m unittest tests.test_agent_run_receipt",
            "python3 -m agent_evidence_recorder verify-agent-run-receipts",
            "git diff --check",
        ],
        "completion_tokens_estimated": 3000,
        "cost_confidence": "low",
        "cost_source": "static_fixture_estimate",
        "estimated_cost_usd": 0.09,
        "evidence_packet_ref": "agent-run-receipt.codex.evidence_packet.md",
        "files_changed": ["agent_evidence_recorder/agent_run_receipt.py", "tests/test_agent_run_receipt.py"],
        "model": "synthetic-model-estimate",
        "next_run_recommendations": [
            "Keep receipt scoring deterministic.",
            "Compare receipt warnings against reviewer packet gaps before trusting the score.",
        ],
        "non_claims": BASE_NON_CLAIMS,
        "privacy_boundary": PRIVACY_BOUNDARY,
        "prompt_body_policy": PROMPT_BODY_POLICY,
        "prompt_tokens_estimated": 12000,
        "receipt_id": "agent-run-receipt-codex",
        "repo": "agent_evidence-recorder-public-sample",
        "review_packet_ref": "agent-run-receipt.codex.review_packet.md",
        "run_id": "synthetic-agent-run-verified-001",
        "schema_version": SCHEMA_VERSION,
        "task_class": "verified_coding_run",
        "task_summary": "Synthetic agent run adds a deterministic receipt validator and local tests.",
        "tests_run": [
            "tests.test_agent_run_receipt.AgentRunReceiptTests.test_tracked_receipts_verify",
            "tests.test_agent_run_receipt.AgentRunReceiptTests.test_score_is_deterministic",
        ],
        "tool": "synthetic-coding-agent",
        "total_tokens_estimated": 15000,
        "verification_refs": ["agent-run-receipt.codex.verification.json"],
        "verification_status": "verified",
        "waste_flags": [],
    }


def unverified_receipt() -> dict[str, Any]:
    return {
        "artifact_manifest_ref": "agent-run-receipt.unverified.artifact_manifest.json",
        "artifacts_created": ["draft_receipt.json"],
        "commands_run": [
            "python3 -m agent_evidence_recorder.agent_run_receipt score samples/agent-run-receipts/agent-run-receipt.unverified.json"
        ],
        "completion_tokens_estimated": 5000,
        "cost_confidence": "low",
        "cost_source": "static_fixture_estimate",
        "estimated_cost_usd": 0.11,
        "evidence_packet_ref": "agent-run-receipt.unverified.evidence_packet.md",
        "files_changed": ["docs/draft_receipt_note.md"],
        "model": "synthetic-model-estimate",
        "next_run_recommendations": [
            "Run focused verification before adding new output.",
            "Keep unknown verification status until evidence refs exist.",
        ],
        "non_claims": BASE_NON_CLAIMS,
        "privacy_boundary": PRIVACY_BOUNDARY,
        "prompt_body_policy": PROMPT_BODY_POLICY,
        "prompt_tokens_estimated": 13000,
        "receipt_id": "agent-run-receipt-unverified",
        "repo": "agent_evidence-recorder-public-sample",
        "review_packet_ref": "agent-run-receipt.unverified.review_packet.md",
        "run_id": "synthetic-agent-run-unverified-001",
        "schema_version": SCHEMA_VERSION,
        "task_class": "unverified_output",
        "task_summary": "Synthetic agent run produced a draft artifact without completed verification.",
        "tests_run": [],
        "tool": "synthetic-coding-agent",
        "total_tokens_estimated": 18000,
        "verification_refs": [],
        "verification_status": "unknown",
        "waste_flags": ["missing_verification"],
    }


def noop_receipt() -> dict[str, Any]:
    return {
        "artifact_manifest_ref": "agent-run-receipt.noop.artifact_manifest.json",
        "artifacts_created": [],
        "commands_run": ["git status --short", "rg task docs"],
        "completion_tokens_estimated": 2000,
        "cost_confidence": "low",
        "cost_source": "static_fixture_estimate",
        "estimated_cost_usd": 0.05,
        "evidence_packet_ref": "agent-run-receipt.noop.evidence_packet.md",
        "files_changed": [],
        "model": "synthetic-model-estimate",
        "next_run_recommendations": [
            "Stop the run earlier when no bounded output is forming.",
            "Define one file ownership target before spending more tokens.",
        ],
        "non_claims": BASE_NON_CLAIMS,
        "privacy_boundary": PRIVACY_BOUNDARY,
        "prompt_body_policy": PROMPT_BODY_POLICY,
        "prompt_tokens_estimated": 7000,
        "receipt_id": "agent-run-receipt-noop",
        "repo": "agent_evidence-recorder-public-sample",
        "review_packet_ref": "agent-run-receipt.noop.review_packet.md",
        "run_id": "synthetic-agent-run-noop-001",
        "schema_version": SCHEMA_VERSION,
        "task_class": "noop_run",
        "task_summary": "Synthetic agent run consumed tokens but produced no verified output.",
        "tests_run": [],
        "tool": "synthetic-coding-agent",
        "total_tokens_estimated": 9000,
        "verification_refs": [],
        "verification_status": "needs_review",
        "waste_flags": ["no_verified_change", "prompt_too_broad"],
    }


def receipt_with_score(receipt: dict[str, Any]) -> dict[str, Any]:
    scored = dict(receipt)
    score = score_receipt(scored)
    scored["token_efficiency_score"] = score["token_efficiency_score"]
    scored["verified_output_per_1m_tokens"] = score["verified_output_per_1m_tokens"]
    return scored


def write_agent_run_receipt_examples(root: Path | None = None) -> dict[str, Any]:
    root = root or Path.cwd()
    receipt_dir = root / DEFAULT_RECEIPT_DIR
    receipt_dir.mkdir(parents=True, exist_ok=True)
    examples = {
        "codex": receipt_with_score(verified_receipt()),
        "noop": receipt_with_score(noop_receipt()),
        "unverified": receipt_with_score(unverified_receipt()),
    }

    write_text(
        receipt_dir / "agent-run-receipt.codex.evidence_packet.md",
        "\n".join(
            [
                "# Agent Run Receipt Evidence Packet: Verified Synthetic Run",
                "",
                "- Receipt: `agent-run-receipt-codex`",
                "- Run: `synthetic-agent-run-verified-001`",
                "- Evidence boundary: public synthetic fixture only.",
                "- Verification status: `verified`",
                "- Verified outputs: two changed files, two local tests, and three review artifacts.",
                "- Prompt body policy: `excluded_by_default`",
                "",
                "This packet is a synthetic review fixture. It does not contain prompt bodies,",
                "provider billing data, telemetry, customer data, or live adapter output.",
                "",
            ]
        ),
    )
    write_text(
        receipt_dir / "agent-run-receipt.codex.review_packet.md",
        "\n".join(
            [
                "# Agent Run Receipt Review Packet: Verified Synthetic Run",
                "",
                "## Reviewer Questions",
                "",
                "- Do the verification refs support the claimed verified status?",
                "- Is the token estimate clearly marked as an estimate?",
                "- Are the output claims limited to changed files, tests, and review artifacts?",
                "",
                "## Boundary",
                "",
                "- Prompt body policy: `excluded_by_default`",
                "- Privacy boundary: `public_synthetic_fixture_only`",
                "- Provider billing imported: `false`",
                "- Telemetry collected: `false`",
                "",
            ]
        ),
    )
    write_json(
        receipt_dir / "agent-run-receipt.codex.verification.json",
        {
            "checks": [
                {"name": "unit_tests_recorded", "passed": True},
                {"name": "review_packet_present", "passed": True},
            ],
            "passed": True,
            "schema_version": "agent_evidence_recorder.agent_run_receipt_verification_fixture.v0.1",
        },
    )

    write_text(
        receipt_dir / "agent-run-receipt.unverified.evidence_packet.md",
        "\n".join(
            [
                "# Agent Run Receipt Evidence Packet: Unverified Synthetic Run",
                "",
                "- Receipt: `agent-run-receipt-unverified`",
                "- Run: `synthetic-agent-run-unverified-001`",
                "- Evidence boundary: public synthetic fixture only.",
                "- Verification status: `unknown`",
                "- Prompt body policy: `excluded_by_default`",
                "",
                "This fixture records output activity without completed verification. The receipt",
                "must not promote the run to verified.",
                "",
            ]
        ),
    )
    write_text(
        receipt_dir / "agent-run-receipt.unverified.review_packet.md",
        "\n".join(
            [
                "# Agent Run Receipt Review Packet: Unverified Synthetic Run",
                "",
                "## Reviewer Questions",
                "",
                "- What verification command is missing?",
                "- Should the next run spend tokens on verification before additional changes?",
                "",
                "## Boundary",
                "",
                "- Prompt body policy: `excluded_by_default`",
                "- Privacy boundary: `public_synthetic_fixture_only`",
                "- Provider billing imported: `false`",
                "- Telemetry collected: `false`",
                "",
            ]
        ),
    )

    write_text(
        receipt_dir / "agent-run-receipt.noop.evidence_packet.md",
        "\n".join(
            [
                "# Agent Run Receipt Evidence Packet: No-Op Synthetic Run",
                "",
                "- Receipt: `agent-run-receipt-noop`",
                "- Run: `synthetic-agent-run-noop-001`",
                "- Evidence boundary: public synthetic fixture only.",
                "- Verification status: `needs_review`",
                "- Prompt body policy: `excluded_by_default`",
                "",
                "This fixture records a token-consuming run that produced no verified output.",
                "",
            ]
        ),
    )
    write_text(
        receipt_dir / "agent-run-receipt.noop.review_packet.md",
        "\n".join(
            [
                "# Agent Run Receipt Review Packet: No-Op Synthetic Run",
                "",
                "## Reviewer Questions",
                "",
                "- Was the task too broad for a bounded run?",
                "- Should the next run start with a smaller acceptance criterion?",
                "",
                "## Boundary",
                "",
                "- Prompt body policy: `excluded_by_default`",
                "- Privacy boundary: `public_synthetic_fixture_only`",
                "- Provider billing imported: `false`",
                "- Telemetry collected: `false`",
                "",
            ]
        ),
    )

    for label, receipt in examples.items():
        write_json(receipt_dir / f"agent-run-receipt.{label}.json", receipt)
        entries = [
            {
                "artifact_role": "evidence_packet",
                "classification": "synthetic_fixture",
                "relative_path": receipt["evidence_packet_ref"],
            },
            {
                "artifact_role": "review_packet",
                "classification": "synthetic_fixture",
                "relative_path": receipt["review_packet_ref"],
            },
        ]
        for verification_ref in receipt["verification_refs"]:
            entries.append(
                {
                    "artifact_role": "verification_ref",
                    "classification": "synthetic_fixture",
                    "relative_path": verification_ref,
                }
            )
        write_json(
            receipt_dir / f"agent-run-receipt.{label}.artifact_manifest.json",
            {
                "entries": entries,
                "schema_version": "agent_evidence_recorder.agent_run_receipt_manifest_fixture.v0.1",
            },
        )
    return {
        "receipt_dir": DEFAULT_RECEIPT_DIR.as_posix(),
        "receipts": [
            {"receipt_id": receipt["receipt_id"], "verification_status": receipt["verification_status"]}
            for receipt in examples.values()
        ],
        "verified": verify_receipts(receipt_dir)["passed"],
    }


def verify_receipt(path: Path) -> dict[str, Any]:
    receipt = read_json(path)
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    missing = REQUIRED_FIELDS - set(receipt)
    add("required_fields_present", not missing, ",".join(sorted(missing)))
    add("schema_version_current", receipt.get("schema_version") == SCHEMA_VERSION, str(receipt.get("schema_version")))
    add(
        "verification_status_allowed",
        receipt.get("verification_status") in ALLOWED_VERIFICATION_STATUSES,
        str(receipt.get("verification_status")),
    )
    add(
        "cost_confidence_allowed",
        receipt.get("cost_confidence") in ALLOWED_COST_CONFIDENCE,
        str(receipt.get("cost_confidence")),
    )
    add("cost_source_is_estimate", str(receipt.get("cost_source", "")).endswith("_estimate"), str(receipt.get("cost_source")))
    add("prompt_body_excluded", receipt.get("prompt_body_policy") == PROMPT_BODY_POLICY, str(receipt.get("prompt_body_policy")))
    add("privacy_boundary_public_synthetic", receipt.get("privacy_boundary") == PRIVACY_BOUNDARY, str(receipt.get("privacy_boundary")))
    add("non_claims_cover_boundary", ADVICE_NON_CLAIMS <= set(receipt.get("non_claims") or []), ",".join(receipt.get("non_claims") or []))

    numeric_errors: list[str] = []
    for field in ("prompt_tokens_estimated", "completion_tokens_estimated", "total_tokens_estimated", "estimated_cost_usd"):
        value = receipt.get(field)
        if not isinstance(value, (int, float)) or value < 0:
            numeric_errors.append(field)
    expected_total = (receipt.get("prompt_tokens_estimated") or 0) + (receipt.get("completion_tokens_estimated") or 0)
    if receipt.get("total_tokens_estimated") != expected_total:
        numeric_errors.append("total_tokens_estimated_sum")
    add("token_and_cost_estimates_nonnegative", not numeric_errors, ",".join(numeric_errors))

    path_errors: list[str] = []
    for field in ("evidence_packet_ref", "review_packet_ref", "artifact_manifest_ref"):
        rel = receipt.get(field)
        reason = unsafe_relative_path(rel)
        if reason:
            path_errors.append(f"{field}:{rel}:{reason}")
            continue
        target = path.parent / str(rel)
        if not target.is_file():
            path_errors.append(f"{field}:{rel}:missing")
    for rel in receipt.get("verification_refs") or []:
        reason = unsafe_relative_path(rel)
        if reason:
            path_errors.append(f"verification_refs:{rel}:{reason}")
        elif not (path.parent / str(rel)).is_file():
            path_errors.append(f"verification_refs:{rel}:missing")
    add("artifact_refs_exist_and_are_relative", not path_errors, ";".join(path_errors))

    if receipt.get("verification_status") == "verified":
        add("verified_receipts_have_verification_refs", bool(receipt.get("verification_refs")), "verified requires refs")
    else:
        add(
            "missing_verification_not_promoted",
            receipt.get("token_efficiency_score", 101) <= 35 and receipt.get("verified_output_per_1m_tokens", 1) == 0,
            "unverified receipts must stay low-score with zero verified output rate",
        )

    score = score_receipt(receipt)
    add("score_matches_deterministic_scorer", receipt.get("token_efficiency_score") == score["token_efficiency_score"], json.dumps(score, sort_keys=True))
    add(
        "verified_output_rate_matches_deterministic_scorer",
        receipt.get("verified_output_per_1m_tokens") == score["verified_output_per_1m_tokens"],
        json.dumps(score, sort_keys=True),
    )

    text_issue_markers: list[str] = []
    paths_to_scan = [path]
    for field in ("evidence_packet_ref", "review_packet_ref", "artifact_manifest_ref"):
        rel = receipt.get(field)
        if isinstance(rel, str) and not unsafe_relative_path(rel):
            target = path.parent / rel
            if target.is_file():
                paths_to_scan.append(target)
    for target in paths_to_scan:
        for marker in public_text_issues(target):
            text_issue_markers.append(f"{target.name}:{marker}")
    add("public_surface_markers_absent", not text_issue_markers, ";".join(text_issue_markers))

    passed = all(check["passed"] for check in checks)
    return {
        "checks": checks,
        "passed": passed,
        "receipt_id": receipt.get("receipt_id", ""),
        "score": score,
    }


def verify_receipts(root: Path | None = None) -> dict[str, Any]:
    root = root or DEFAULT_RECEIPT_DIR
    expected = {
        "agent-run-receipt.codex.json",
        "agent-run-receipt.noop.json",
        "agent-run-receipt.unverified.json",
    }
    paths = [root / name for name in sorted(expected)]
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str = "") -> None:
        checks.append({"name": name, "passed": passed, "detail": detail})

    present = {path.name for path in root.glob("agent-run-receipt.*.json") if path.is_file()}
    add("expected_receipts_present", expected <= present, ",".join(sorted(present)))
    reports = []
    for path in paths:
        report = verify_receipt(path)
        reports.append(report)
        for check in report["checks"]:
            checks.append({**check, "name": f"{path.name}:{check['name']}"})
    passed = all(check["passed"] for check in checks)
    return {"checks": checks, "passed": passed, "receipt_count": len(paths), "reports": reports}


def main() -> int:
    parser = argparse.ArgumentParser(prog="agent-run-receipt")
    subcommands = parser.add_subparsers(dest="command", required=True)
    score_parser = subcommands.add_parser("score", help="score one agent run receipt")
    score_parser.add_argument("receipt", type=Path)
    verify_parser = subcommands.add_parser("verify", help="verify tracked agent run receipt examples")
    verify_parser.add_argument("--receipt-dir", type=Path, default=DEFAULT_RECEIPT_DIR)
    args = parser.parse_args()

    if args.command == "score":
        print(json.dumps(score_receipt(read_json(args.receipt)), indent=2, sort_keys=True))
        return 0
    if args.command == "verify":
        report = verify_receipts(args.receipt_dir)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
