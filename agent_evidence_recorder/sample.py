"""Generate public-safe synthetic Agent Evidence Recorder sample artifacts."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from agent_evidence_recorder.agent_run_receipt import write_agent_run_receipt_examples
from agent_evidence_recorder.pr_review import verify_pr_review_bundle, verify_recorded_review_outcome, write_pr_review_bundle

GENERATED_AT = "2026-05-25T00:00:00Z"
SCHEMA_VERSION = "agent_evidence_recorder.public_sample.v0"
PR_REVIEW_SAMPLE_ID = "agent_evidence-pr-review-sample"
PR_REVIEW_LOW_RISK_DOCS_ID = "agent_evidence-pr-review-low-risk-docs"
PR_REVIEW_SELF_DEMO_ID = "agent_evidence-pr-review-self-demo"
PR_REVIEW_ADVERSARIAL_ID = "agent_evidence-pr-review-adversarial"
LIVE_ENVELOPE_RUN_ID = "agent_evidence-sample-run-live-envelope"
SYNTHETIC_PROVENANCE = "synthetic_sample"
SYNTHETIC_LIVE_ENVELOPE_PROVENANCE = "synthetic_live_envelope"
LIVE_ENVELOPE_REDACTION_RULES = (
    "absolute_path",
    "secret_shaped_token",
    "customer_data_shape",
    "unrelated_local_file",
)
LIVE_ENVELOPE_REDACTION_REPORT = (
    ("absolute_path", "[REDACTED_LOCAL_PATH]"),
    ("secret_shaped_token", "[REDACTED_SECRET]"),
    ("customer_data_shape", "[REDACTED_CUSTOMER_DATA]"),
    ("unrelated_local_file", "[REDACTED_LOCAL_FILE]"),
)
ALLOWED_FILE_EFFECTS = ("read_file", "create_file", "modify_file", "no_op")
DISALLOWED_NON_FILE_EFFECTS = (
    "network_call",
    "external_api_call",
    "deploy",
    "publish",
    "browser_automation",
    "cloud_operation",
    "hardware_access",
    "payment",
)
RUN_IDS = (
    "agent_evidence-sample-run",
    "agent_evidence-sample-run-rejected",
    "agent_evidence-sample-run-escalated",
    "agent_evidence-sample-run-blocked",
    "agent_evidence-sample-run-vague",
    LIVE_ENVELOPE_RUN_ID,
)
ADVERSARIAL_TRAPS = (
    {
        "trap_id": "verification_failed_but_evidence_retained",
        "run_id": "agent_evidence-sample-run-rejected",
        "failure_class": "verification_failure",
        "severity": "important",
        "review_question": "Does failed autonomous work still leave enough evidence for rejection?",
        "expected_policy_status": "verification_failed",
        "expected_final_status": "rejected",
    },
    {
        "trap_id": "policy_sensitive_file_changed",
        "run_id": "agent_evidence-sample-run-escalated",
        "failure_class": "policy_sensitive_change",
        "severity": "important",
        "review_question": "Does a policy-sensitive file change require human judgment even when verification passes?",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    {
        "trap_id": "verification_passed_but_forbidden_effect_requested",
        "run_id": "agent_evidence-sample-run-blocked",
        "failure_class": "forbidden_effect",
        "severity": "blocker",
        "review_question": "Does the gate block trust when a run plans a forbidden effect despite passing tests?",
        "expected_policy_status": "blocked",
        "expected_final_status": "blocked",
    },
    {
        "trap_id": "rollback_claim_limited_to_recorded_diff",
        "run_id": "agent_evidence-sample-run-blocked",
        "failure_class": "rollback_overclaim",
        "severity": "blocker",
        "review_question": "Does the review packet keep rollback bounded to the recorded git diff?",
        "expected_policy_status": "blocked",
        "expected_final_status": "blocked",
    },
    {
        "trap_id": "trust_not_granted_by_verification_alone",
        "run_id": "agent_evidence-sample-run-escalated",
        "failure_class": "verification_overtrust",
        "severity": "important",
        "review_question": "Can verification pass while trust still requires escalation?",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    {
        "trap_id": "vague_intent_blocks_review_judgment",
        "run_id": "agent_evidence-sample-run-vague",
        "failure_class": "vague_intent",
        "severity": "important",
        "review_question": "Can a reviewer escalate when the intent is too broad to compare against the diff?",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    {
        "trap_id": "unrelated_diff_requires_review",
        "run_id": "agent_evidence-sample-run-vague",
        "failure_class": "unrelated_diff",
        "severity": "important",
        "review_question": "Can a reviewer spot a diff that does not support the stated intent?",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    {
        "trap_id": "weak_provenance_requires_review",
        "run_id": "agent_evidence-sample-run-vague",
        "failure_class": "weak_provenance",
        "severity": "important",
        "review_question": "Can a reviewer hold trust when provenance is structurally present but under-specified?",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    {
        "trap_id": "stale_evidence_requires_review",
        "run_id": "agent_evidence-sample-run-vague",
        "failure_class": "stale_evidence",
        "severity": "important",
        "review_question": "Can a reviewer escalate if a packet could drift from the verifier result?",
        "expected_policy_status": "needs_human_review",
        "expected_final_status": "needs_human_review",
    },
    {
        "trap_id": "live_input_rejected_by_preflight",
        "run_id": LIVE_ENVELOPE_RUN_ID,
        "failure_class": "input_rejected",
        "severity": "blocker",
        "review_question": "Does this synthetic preflight record prove input rejection with redaction and no provider call?",
        "expected_policy_status": "blocked",
        "expected_final_status": "blocked",
    },
)
REQUIRED_RUN_ARTIFACTS = (
    "run_record.json",
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
)
POLICY_STATUS_TO_FINAL_STATUS = {
    "passed": "accepted",
    "verification_failed": "rejected",
    "needs_human_review": "needs_human_review",
    "blocked": "blocked",
}


def write_text(path: Path, value: str, executable: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")
    if executable:
        path.chmod(path.stat().st_mode | 0o100)


def write_json(path: Path, value: dict | list) -> None:
    write_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_files(fixed: bool) -> dict[str, str]:
    operator = "+" if fixed else "-"
    return {
        "README.md": "# Sample Target Repo\n\nTiny deterministic fixture for Agent Evidence Recorder.\n",
        "calculator.py": "\n".join(
            [
                '"""Tiny synthetic module used by the sample."""',
                "",
                "",
                "def add(a: int, b: int) -> int:",
                f"    return a {operator} b",
                "",
            ]
        ),
        "agent_policy.json": json.dumps(
            {
                "allowed_effects": ["tracked_fixture_file_edit"],
                "forbidden_effects": ["network_call_plan"],
                "human_review_paths": ["agent_policy.json"],
                "network_calls": "not_allowed",
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        "network_plan.txt": "network_calls: not_used\n",
        "test_calculator.py": "\n".join(
            [
                "import unittest",
                "",
                "from calculator import add",
                "",
                "",
                "class CalculatorTests(unittest.TestCase):",
                "    def test_adds_two_numbers(self) -> None:",
                "        self.assertEqual(add(2, 3), 5)",
                "",
                "",
                "if __name__ == \"__main__\":",
                "    unittest.main()",
                "",
            ]
        ),
    }


def public_diff(mode: str) -> str:
    replacement = "return a + b + 1" if mode == "failure" else "return a + b"
    lines = [
            "diff --git a/calculator.py b/calculator.py",
            "index 1111111..2222222 100644",
            "--- a/calculator.py",
            "+++ b/calculator.py",
            "@@ -2,5 +2,5 @@",
            "",
            "",
            " def add(a: int, b: int) -> int:",
            "-    return a - b",
            f"+    {replacement}",
            "",
        ]
    if mode == "escalation":
        lines.extend(
            [
                "diff --git a/agent_policy.json b/agent_policy.json",
                "index 3333333..4444444 100644",
                "--- a/agent_policy.json",
                "+++ b/agent_policy.json",
                "@@ -1,4 +1,6 @@",
                '   "allowed_effects": [',
                '     "tracked_fixture_file_edit"',
                "   ],",
                '+  "human_review_requested": true,',
                '+  "review_reason": "Synthetic run changed a policy-sensitive control file.",',
                '   "network_calls": "not_allowed"',
                "",
            ]
        )
    if mode == "blocked":
        lines.extend(
            [
                "diff --git a/network_plan.txt b/network_plan.txt",
                "index 5555555..6666666 100644",
                "--- a/network_plan.txt",
                "+++ b/network_plan.txt",
                "@@ -1 +1 @@",
                "-network_calls: not_used",
                "+network_calls: planned",
                "",
            ]
        )
    if mode == "vague":
        lines.extend(
            [
                "diff --git a/README.md b/README.md",
                "index 7777777..8888888 100644",
                "--- a/README.md",
                "+++ b/README.md",
                "@@ -1,3 +1,5 @@",
                " # Sample Target Repo",
                "",
                " Tiny deterministic fixture for Agent Evidence Recorder.",
                "+",
                "+General maintenance note: synthetic docs were refreshed.",
                "",
            ]
        )
    if mode == "live_envelope":
        lines.extend(
            [
                "diff --git a/network_plan.txt b/network_plan.txt",
                "index 5555555..6666666 100644",
                "--- a/network_plan.txt",
                "+++ b/network_plan.txt",
                "@@ -1 +1 @@",
                "-network_calls: not_used",
                "+network_calls: blocked_for_input_contract_rejection",
                "",
            ]
        )
    return "\n".join(lines)


def command_result(mode: str) -> dict:
    if mode == "live_envelope":
        return {
            "command": ["agent_evidence-recorder", "simulate-live-envelope-preflight"],
            "cwd": "samples",
            "returncode": 0,
            "stdout_summary": "provider request blocked during preflight",
            "stderr_summary": "",
        }
    passed = mode != "failure"
    return {
        "command": ["python3", "-B", "-m", "unittest", "test_calculator.py"],
        "cwd": "sample-target-repo",
        "returncode": 0 if passed else 1,
        "stdout_summary": "1 test passed" if passed else "1 test failed as expected for rejected sample",
        "stderr_summary": "",
    }


def execution_limits() -> dict:
    return {
        "timeout_seconds": 30,
        "cost_budget": {
            "unit": "synthetic_provider_tokens",
            "maximum": 0,
            "actual": 0,
            "provider_account_required": False,
        },
        "network_budget": "not_allowed",
        "external_effect_budget": "tracked_fixture_file_edit_only",
    }


def observed_file_effects(mode: str) -> list[dict]:
    return [
        {
            "effect_type": "modify_file",
            "path": path,
            "file_scoped": True,
            "rollback_scope": "recorded_git_diff",
        }
        for path in changed_files_for_mode(mode)
    ]


def requested_non_file_effects(mode: str) -> list[dict]:
    if mode == "blocked":
        return [
            {
                "effect_type": "network_call",
                "source": "network_plan.txt",
                "status": "blocked",
                "reason": "non_file_effect_out_of_scope",
            }
        ]
    if mode == "live_envelope":
        return [
            {
                "effect_type": "network_call",
                "source": "live_request_envelope.json",
                "status": "blocked",
                "reason": "input_preflight_blocked_before_provider_request",
            }
        ]
    return []


def effect_boundary(mode: str) -> dict:
    return {
        "schema_version": "agent_evidence_recorder.effect_boundary.v0",
        "boundary_type": "file_scoped_synthetic",
        "allowed_effects": list(ALLOWED_FILE_EFFECTS),
        "disallowed_effects": list(DISALLOWED_NON_FILE_EFFECTS),
        "observed_effects": observed_file_effects(mode),
        "requested_non_file_effects": requested_non_file_effects(mode),
        "non_file_effects_allowed": False,
        "provider_calls_allowed": False,
        "external_effects_rollbackable": False,
        "rollback_scope": "recorded_git_diff_only",
        "reviewer_must_block_non_file_effects": True,
    }


def failure_capture(mode: str) -> dict:
    failure_class = {
        "success": "none",
        "failure": "verifier_failure",
        "escalation": "policy_review_required",
        "blocked": "forbidden_effect_requested",
        "vague": "review_judgment_blocked",
        "live_envelope": "input_rejected",
    }[mode]
    return {
        "timeout_observed": False,
        "cost_budget_exceeded": False,
        "provider_refusal_observed": mode == "live_envelope",
        "partial_output_observed": False,
        "verifier_failure_observed": mode == "failure",
        "failure_class": failure_class,
        "recorded_evidence": [
            "commands.log",
            "sample_verification.json",
            "policy_gate_report.json",
            "review_packet.md",
        ],
    }


def run_record(run_id: str, mode: str, final_status: str, run_dir: Path) -> dict:
    run_path = f"samples/{run_id}"
    target_path = "samples/sample-target-repo"
    live_envelope = None
    intent = (
        "Improve the sample target repo."
        if mode == "vague"
        else "Record a bounded synthetic coding-agent-style run with reviewable evidence."
    )
    if mode == "live_envelope":
        intent = (
            "Model a live-envelope preflight request with input rejection, redaction metadata, "
            "and no provider call."
        )
        live_envelope = {
            "request_envelope": f"{run_path}/live_request_envelope.json",
            "redaction_report": f"{run_path}/live_redaction_report.json",
            "provider_rejection_record": f"{run_path}/provider_request_rejection_record.json",
            "provider_request_sent": False,
            "reviewer_outcome_required": True,
            "redaction_count": 4,
            "redaction_rules": list(LIVE_ENVELOPE_REDACTION_RULES),
        }
    record = {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "intent": intent,
        "producer": "agent_evidence_recorder.sample",
        "adapter": "synthetic_sample",
        "provenance": SYNTHETIC_LIVE_ENVELOPE_PROVENANCE if mode == "live_envelope" else SYNTHETIC_PROVENANCE,
        "workflow_type": "live_preflight_envelope" if mode == "live_envelope" else "coding_agent_run",
        "roots": {
            "target_repo": "sample-target-repo",
            "run_store": ".afr/runs/<run_id>",
            "public_example_export": run_path,
        },
        "replay_command": "python3 -m agent_evidence_recorder.sample && python3 -m agent_evidence_recorder.verify_sample",
        "input_artifacts": [
            {"relative_path": f"{target_path}/README.md", "artifact_role": "target_fixture_input"},
            {"relative_path": f"{target_path}/agent_policy.json", "artifact_role": "target_policy_fixture"},
            {"relative_path": f"{target_path}/calculator.py", "artifact_role": "target_fixture_source"},
            {"relative_path": f"{target_path}/network_plan.txt", "artifact_role": "target_effect_fixture"},
            {"relative_path": f"{target_path}/test_calculator.py", "artifact_role": "target_fixture_verifier"},
        ],
        "output_artifacts": [
            {"relative_path": f"{run_path}/{name}", "artifact_role": artifact_role(name)}
            for name in run_output_artifacts(mode)
        ],
        "generation_steps": [
            {"step": "create_synthetic_fixture", "status": "completed"},
            {"step": "apply_modeled_code_edit", "mode": mode},
            {"step": "write_public_safe_artifacts", "status": "completed"},
        ],
        "tool_or_model_steps": [
            {
                "step": "modeled_agent_edit",
                "adapter": "synthetic_sample",
                "live_model_used": False,
                "changed_files": changed_files_for_mode(mode),
            },
            command_result(mode),
        ],
        "environment_boundary": {
            "execution": "local_synthetic_sample",
            "network": "not_used",
            "external_api": "not_used",
            "provider_account": "not_required",
            "rollback_scope": "git_tracked_files_only",
        },
        "execution_limits": execution_limits(),
        "effect_boundary": effect_boundary(mode),
        "failure_capture": failure_capture(mode),
        "verification_notes": {
            "sample_verification": f"{run_path}/sample_verification.json",
            "policy_gate_report": f"{run_path}/policy_gate_report.json",
            "human_escalation_record": f"{run_path}/human_escalation_record.json",
            "public_surface": "relative_paths_only",
            "residual_risk": "sample_does_not_wrap_live_agents",
        },
        "final_status": final_status,
    }
    if live_envelope is not None:
        record["live_envelope"] = live_envelope
    return record


def trace(run_id: str, mode: str, final_status: str) -> str:
    events = [
        {"event": "run_started", "run_id": run_id, "adapter": "synthetic_sample"},
        {"event": "fixture_created", "run_id": run_id, "target": "sample-target-repo"},
        {
            "event": "modeled_edit_applied",
            "run_id": run_id,
            "mode": mode,
            "changed_files": changed_files_for_mode(mode),
        },
        {
            "event": "execution_limits_recorded",
            "run_id": run_id,
            "timeout_seconds": 30,
            "cost_budget_maximum": 0,
        },
        {
            "event": "failure_capture_recorded",
            "run_id": run_id,
            "failure_class": failure_capture(mode)["failure_class"],
        },
        {"event": "verification_completed", "run_id": run_id, "final_status": final_status},
        {"event": "policy_gate_completed", "run_id": run_id, "final_status": final_status},
        {"event": "artifacts_written", "run_id": run_id, "artifacts": run_output_artifacts(mode)},
    ]
    if mode == "live_envelope":
        events.append(
            {
                "event": "provider_request_rejected",
                "run_id": run_id,
                "provider_request_sent": False,
                "redactions_reported": True,
            },
        )
    return "\n".join(json.dumps(event, sort_keys=True) for event in events) + "\n"


def policy_report(run_id: str) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "public_safety": {
            "artifact_surface": "public_sample",
            "path_mode": "relative_only",
            "data_boundary": "synthetic",
            "live_adapter": False,
            "external_effects": "blocked_non_file_effects_only",
            "rollback_scope": "git_tracked_files_only",
        },
    }


def changed_files_for_mode(mode: str) -> list[str]:
    changed = ["calculator.py"]
    if mode == "escalation":
        changed.append("agent_policy.json")
    if mode == "blocked":
        changed.append("network_plan.txt")
    if mode == "vague":
        changed.append("README.md")
    if mode == "live_envelope":
        return ["network_plan.txt"]
    return changed


def policy_status_for_mode(mode: str) -> str:
    return {
        "success": "passed",
        "failure": "verification_failed",
        "escalation": "needs_human_review",
        "blocked": "blocked",
        "vague": "needs_human_review",
        "live_envelope": "blocked",
    }[mode]


def policy_gate_report(run_id: str, mode: str) -> dict:
    status = policy_status_for_mode(mode)
    violations = []
    escalations = []
    if mode == "failure":
        violations.append(
            {
                "trigger": "verification_failed",
                "command": "python3 -B -m unittest test_calculator.py",
                "returncode": 1,
            }
        )
    if mode == "escalation":
        escalations.append(
            {
                "trigger": "policy_sensitive_file_changed",
                "observed_file": "agent_policy.json",
                "required_reviewer_action": "Confirm whether the policy-sensitive change is allowed.",
            }
        )
    if mode == "blocked":
        violations.append(
            {
                "trigger": "forbidden_effect_requested",
                "observed_file": "network_plan.txt",
                "forbidden_effect": "network_call_plan",
            }
        )
    if mode == "vague":
        escalations.extend(
            [
                {
                    "trigger": "intent_too_broad",
                    "observed_field": "run_record.intent",
                    "required_reviewer_action": "Narrow the intent enough to compare it against the diff.",
                },
                {
                    "trigger": "unrelated_diff_possible",
                    "observed_file": "README.md",
                    "required_reviewer_action": "Confirm whether the documentation change supports the stated intent.",
                },
                {
                    "trigger": "weak_provenance",
                    "observed_artifact": "artifact_manifest.json",
                    "required_reviewer_action": "Confirm artifact hashes and roles are sufficient for review judgment.",
                },
                {
                    "trigger": "stale_evidence_risk",
                    "observed_artifact": "review_packet.md",
                    "required_reviewer_action": "Confirm review packet claims agree with sample_verification.json.",
                },
            ]
        )
    if mode == "live_envelope":
        violations.append(
            {
                "trigger": "input_rejected",
                "observed_values": [
                    "[REDACTED_LOCAL_PATH]",
                    "[REDACTED_SECRET]",
                    "[REDACTED_CUSTOMER_DATA]",
                    "[REDACTED_LOCAL_FILE]",
                ],
                "required_reviewer_action": "Confirm input contract rejections and redaction records before retrying.",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "policy_gate_id": "agent_evidence-recorder-public-sample-policy-gate",
        "policy_name": "Synthetic agent-run evidence gate",
        "allowed_actions": [
            "tracked fixture source edit",
            "local fixture verification",
            "evidence artifact generation",
        ],
        "forbidden_actions": [
            "network_call_plan",
            "live provider execution",
            "non-synthetic data access",
        ],
        "effect_boundary": effect_boundary(mode),
        "observed_actions": [{"type": "changed_file", "path": path} for path in changed_files_for_mode(mode)],
        "violations": violations,
        "warnings": [],
        "escalations": escalations,
        "final_policy_status": status,
    }


def human_escalation_record(run_id: str, final_status: str, policy_gate: dict) -> dict:
    requires_human = final_status in {"needs_human_review", "blocked"}
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "escalation_id": f"{run_id}-human-escalation",
        "trigger": policy_gate["final_policy_status"],
        "reason": (
            "Policy-sensitive or forbidden behavior requires human disposition."
            if requires_human
            else "No human escalation required for this synthetic run."
        ),
        "affected_artifacts": [
            "policy_gate_report.json",
            "git.diff",
            "review_packet.md",
            "kill_switch_boundary.md",
        ],
        "required_reviewer_action": (
            "Decide whether to accept, reject, or request a narrower follow-up run."
            if requires_human
            else "none"
        ),
        "suggested_decision_options": ["accept", "reject", "escalate"],
        "non_claims": [
            "No live agent authority is granted.",
            "No external effect is rollbackable.",
            "No production or customer workflow is authorized.",
        ],
    }


def loop_stage_summary(run_id: str, final_status: str, policy_gate: dict, mode: str) -> dict:
    stage = "decide" if final_status in {"needs_human_review", "blocked", "rejected"} else "orchestrate"
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "loop_stage": stage,
        "stage_reason": (
            "Policy or verification requires a decision before trust is granted."
            if stage == "decide"
            else "The synthetic run stayed inside the allowed action boundary."
        ),
        "inputs_used": ["README.md", "agent_policy.json", "calculator.py", "network_plan.txt", "test_calculator.py"],
        "outputs_created": run_output_artifacts(mode),
        "human_review_required": final_status in {"needs_human_review", "blocked"},
        "final_policy_status": policy_gate["final_policy_status"],
    }


def kill_switch_boundary(run_id: str, final_status: str, policy_gate: dict) -> str:
    return "\n".join(
        [
            f"# Kill Switch Boundary: {run_id}",
            "",
            "## Trigger",
            f"- Final policy status: `{policy_gate['final_policy_status']}`",
            f"- Final recorder status: `{final_status}`",
            "",
            "## Stopped Or Held Action",
            "- Trust is not granted until the policy gate passes or a reviewer records a decision.",
            "",
            "## Reviewer Action",
            "- Inspect `policy_gate_report.json`, `git.diff`, `human_escalation_record.json`, and `review_packet.md`.",
            "- Accept only if the policy status is `passed` and verification supports the result.",
            "- Escalate or reject if policy-sensitive or forbidden behavior appears.",
            "",
            "## Rollback Limits",
            "- Rollback is limited to modeled git-tracked fixture changes.",
            "- External effects are not reversible by this sample.",
            "",
        ]
    )


def evidence_packet(run_id: str, final_status: str, mode: str) -> str:
    decision = {
        "accepted": "accept",
        "needs_human_review": "escalate",
        "blocked": "reject",
        "rejected": "reject",
    }[final_status]
    verifier_summary = {
        "accepted": "The modeled edit satisfies the sample verifier and policy gate.",
        "needs_human_review": "The modeled edit passes verification but requires human review by policy.",
        "blocked": "The modeled edit passes verification but is blocked by policy.",
        "rejected": "The modeled edit fails verification and should not be accepted.",
    }[final_status]
    return "\n".join(
        [
            f"# Evidence Packet: {run_id}",
            "",
            "## Summary",
            f"- Final status: `{final_status}`",
            f"- Recommended reviewer decision: `{decision}`",
            "- Adapter: `synthetic_sample`",
            "- Live model used: `false`",
            "- External APIs used: `false`",
            "- Network used: `false`",
            "- Timeout limit: `30` seconds",
            "- Cost budget: `0` synthetic provider tokens",
            f"- Failure class: `{failure_capture(mode)['failure_class']}`",
            "",
            "## Intent",
            "Record a bounded synthetic coding-agent-style run with enough evidence for replay, review, and rollback inspection.",
            "",
            "## What Changed",
            "- Target fixture: `samples/sample-target-repo/calculator.py`",
            "- Modeled change record: `git.diff`",
            "- Verification command summary: `commands.log`",
            "",
            "## Verification",
            f"- Result: {verifier_summary}",
            "- Detailed checks: `sample_verification.json`",
            "- Public-surface boundary: `sample_policy.json`",
            "- Policy gate: `policy_gate_report.json`",
            "- Human escalation: `human_escalation_record.json`",
            "",
            "## Evidence Index",
            "- `run_record.json` captures the intent, inputs, outputs, modeled steps, replay command, boundary, and final status.",
            "- `run_record.json` also captures timeout, cost-budget, and failure-capture fields for the synthetic run.",
            "- `artifact_manifest.json` captures artifact roles, classifications, hashes, byte sizes, replay inclusion, and rollback inclusion.",
            "- `trace.jsonl` captures ordered run events.",
            "- `git.diff` captures the modeled code change.",
            "- `rollback.sh` documents the bounded rollback mechanism for modeled git-tracked changes.",
            "",
            "## Limits",
            "- This sample does not wrap live agents.",
            "- Rollback is limited to modeled git-tracked file changes.",
            "- External effects are not reversed.",
            "- This packet is operational evidence, not a legal or compliance certification.",
            "",
        ]
    )


def _requires_human_outcome(final_status: str) -> bool:
    return final_status in {"needs_human_review", "blocked"}


def review_packet(run_id: str, final_status: str, run_record_obj: dict) -> str:
    decision = {
        "accepted": "Accept the run after inspecting the diff, verification, and policy gate.",
        "needs_human_review": "Escalate the run; verification passed but policy requires a reviewer decision.",
        "blocked": "Reject the run; the policy gate blocked trust even though verification passed.",
        "rejected": "Reject the run; keep the artifact bundle as evidence of the failed modeled change.",
    }[final_status]
    workflow_type = run_record_obj.get("workflow_type", "coding_agent_run")
    failure_capture = run_record_obj.get("failure_capture", {})
    live_envelope = run_record_obj.get("live_envelope")
    boundary = run_record_obj.get("effect_boundary", {})
    requires_human = _requires_human_outcome(final_status)
    provider_blocked = False
    redaction_count = "0"
    preflight_artifacts: list[str] = []
    if isinstance(live_envelope, dict):
        provider_blocked = live_envelope.get("provider_request_sent") is False
        if "redaction_count" in live_envelope:
            redaction_count = str(live_envelope["redaction_count"])
        preflight_artifacts = [
            live_envelope.get("request_envelope", ""),
            live_envelope.get("redaction_report", ""),
            live_envelope.get("provider_rejection_record", ""),
        ]

    lines = [
        f"# Review Packet: {run_id}",
        "",
        "## Decision",
        f"- Final status: `{final_status}`",
        f"- Reviewer action: {decision}",
        f"- Adapter: `{run_record_obj.get('adapter', 'synthetic_sample')}`",
        f"- Provenance: `{run_record_obj.get('provenance', SYNTHETIC_PROVENANCE)}`",
        f"- Workflow: `{workflow_type}`",
        "- Scope: modeled local coding-agent-style run",
        "- Timeout and cost budget: recorded in `run_record.json`",
        f"- Failure capture: `{failure_capture.get('failure_class', 'unknown')}`",
        "- Provider calls executed: `false`",
        f"- Reviewer outcome required: `{str(requires_human).lower()}`",
        f"- Effect boundary: `{boundary.get('boundary_type', 'unknown')}`",
        f"- Non-file effects allowed: `{str(boundary.get('non_file_effects_allowed', False)).lower()}`",
        f"- Rollback scope: `{boundary.get('rollback_scope', 'unknown')}`",
        "",
        "## Required Reviewer Checks",
        "- Confirm `run_record.json` states the run intent, replay command, input artifacts, output artifacts, environment boundary, and final status.",
        "- Confirm `artifact_manifest.json` lists every relevant artifact with role, classification, SHA-256 hash, byte size, replay inclusion, and rollback inclusion.",
        "- Confirm `git.diff` is narrow and only changes the modeled target file.",
        "- Confirm `sample_verification.json` supports the final status.",
        "- Confirm `policy_gate_report.json` supports the final status.",
        "- Confirm `human_escalation_record.json` names the reviewer action when needed.",
        "- Confirm verification passing is not enough when policy escalates or blocks trust.",
        "- Confirm `sample_policy.json` keeps the run synthetic, relative-path-only, and live-adapter-free.",
        "- Confirm `run_record.json` records timeout, cost budget, and failure-capture evidence without live provider calls.",
        "- Confirm `run_record.json` limits effects to file-scoped read/create/modify/no-op actions.",
        "- Confirm `rollback.sh` is limited to modeled git-tracked file changes and does not imply full system rollback.",
        "",
        "## Escalate If",
        "- any artifact path is absolute or machine-local",
        "- any artifact contains sensitive values, access material, or non-public organizational data",
        "- verification status conflicts with final status",
        "- rollback claims exceed the recorded `git.diff` boundary",
        "- non-file effects are claimed as allowed, executed, or rollbackable",
        "- the adapter is anything other than `synthetic_sample` in this candidate",
        "",
    ]
    if workflow_type == "live_preflight_envelope":
        lines.extend(
            [
                "## Live Preflight Evidence (Synthetic)",
                "- This run is a synthetic live-envelope preflight contract test and was blocked before any provider call.",
                f"- Provider request blocked in preflight: `{str(provider_blocked).lower()}`",
                f"- Redaction count: `{redaction_count}`",
                f"- Relevant artifacts: `{', '.join(preflight_artifacts)}`",
                "- Confirm preflight redaction evidence and provider request rejection artifacts match `run_record.json`.",
                "",
            ]
        )
    return "\n".join(lines)


def rollback_script() -> str:
    return "\n".join(
        [
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            'TARGET_REPO="${TARGET_REPO:-sample-target-repo}"',
            'RUN_DIR="${RUN_DIR:-samples/agent_evidence-sample-run}"',
            'case "$TARGET_REPO" in /*|~*) echo "Refusing non-relative target path" >&2; exit 1 ;; esac',
            'case "$RUN_DIR" in /*|~*) echo "Refusing non-relative run path" >&2; exit 1 ;; esac',
            'if [ ! -f "$RUN_DIR/git.diff" ]; then echo "Missing recorded diff" >&2; exit 1; fi',
            'cd "$TARGET_REPO"',
            'if [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then',
            '  echo "Refusing rollback: untracked files present" >&2',
            "  exit 1",
            "fi",
            'git apply -R "../$RUN_DIR/git.diff"',
            'echo "Rollback applied to modeled git-tracked changes only."',
            "",
        ]
    )


def artifact_role(name: str) -> str:
    return {
        "run_record.json": "run_record",
        "trace.jsonl": "event_trace",
        "commands.log": "command_summary",
        "git.diff": "modeled_diff",
        "sample_verification.json": "verification_output",
        "sample_policy.json": "policy_boundary",
        "policy_gate_report.json": "policy_gate_report",
        "human_escalation_record.json": "human_escalation_record",
        "loop_stage_summary.json": "loop_stage_summary",
        "kill_switch_boundary.md": "kill_switch_boundary",
        "evidence_packet.md": "evidence_packet",
        "review_packet.md": "review_packet",
        "rollback.sh": "rollback_script",
        "live_request_envelope.json": "live_request_envelope",
        "live_redaction_report.json": "live_redaction_report",
        "provider_request_rejection_record.json": "provider_request_rejection_record",
    }[name]


def classification(name: str) -> str:
    if name == "evidence_packet.md":
        return "derived_report"
    if name == "review_packet.md":
        return "review_surface"
    if name == "sample_verification.json":
        return "verification_output"
    if name in {"policy_gate_report.json", "human_escalation_record.json", "loop_stage_summary.json"}:
        return "derived_report"
    if name in {"live_request_envelope.json", "live_redaction_report.json", "provider_request_rejection_record.json"}:
        return "derived_report"
    if name == "kill_switch_boundary.md":
        return "review_surface"
    return "generated"


def run_output_artifacts(mode: str) -> list[str]:
    outputs = list(REQUIRED_RUN_ARTIFACTS)
    if mode == "live_envelope":
        outputs.extend(
            [
                "live_request_envelope.json",
                "live_redaction_report.json",
                "provider_request_rejection_record.json",
            ]
        )
    return outputs


def write_live_envelope_artifacts(run_dir: Path, run_id: str) -> None:
    write_json(
        run_dir / "live_request_envelope.json",
        {
            "schema_version": "agent_evidence_recorder.live_envelope.v0",
            "run_id": run_id,
            "task_id": f"{run_id}-request-001",
            "task_description": "Improve calculator behavior for synthetic review and export.",
            "working_root_label": "samples/sample-target-repo",
            "allowed_input_refs": [
                "samples/sample-target-repo/README.md",
                "samples/sample-target-repo/calculator.py",
                "samples/sample-target-repo/test_calculator.py",
            ],
            "disallowed_input_refs": [
                "samples/sample-target-repo/[REDACTED_LOCAL_PATH]/credentials",
                "[REDACTED_SECRET]",
                "Customer: ACME_CORP_ORDERS_DUMP=abc123",
                "[REDACTED_LOCAL_FILE]",
            ],
            "allowed_effects": ["read", "modify", "create", "no-op"],
            "disallowed_effects": ["network_call", "deploy", "publish"],
            "effect_boundary": effect_boundary("live_envelope"),
            "rollback_scope": "git_tracked_files_only",
            "evidence_export_target": f"samples/{run_id}",
            "timeout_seconds": 30,
            "cost_budget": {
                "unit": "synthetic_provider_tokens",
                "maximum": 0,
                "actual": 0,
                "provider_account_required": False,
            },
            "reviewer_outcome_required": True,
            "redaction_profile": "agent_evidence_live_adapter_preflight_v0",
            "provider_request_simulation": {
                "status": "not_sent",
                "rejection_reason": "input_violations_present",
            },
            "normalized_evidence_refs": [
                "sample-target-repo/calculator.py",
                "agent_evidence-recorder sample run",
            ],
        },
    )
    write_json(
        run_dir / "live_redaction_report.json",
        {
            "schema_version": "agent_evidence_recorder.live_envelope.v0",
            "redaction_profile": "agent_evidence_live_adapter_preflight_v0",
            "redactions_applied": [
                {"rule": rule, "count": 1, "replacement": replacement}
                for rule, replacement in LIVE_ENVELOPE_REDACTION_REPORT
            ],
            "redaction_required_before_provider_request": True,
            "raw_sensitive_values_exported": False,
            "raw_sensitive_values_count": 0,
            "artifact": "live_request_envelope.json",
        },
    )
    write_json(
        run_dir / "provider_request_rejection_record.json",
        {
            "schema_version": "agent_evidence_recorder.live_envelope.v0",
            "run_id": run_id,
            "final_status": "blocked",
            "failure_class": "input_rejected",
            "provider_request_sent": False,
            "provider_request_status": "rejected",
            "rejection_reasons": [
                {"field": "disallowed_input_refs", "reason": "disallowed_input_detected"},
            ],
            "redaction_count": 4,
            "request_envelope": f"samples/{run_id}/live_request_envelope.json",
        },
    )


def verification_report(run_id: str, mode: str, final_status: str) -> dict:
    expected = POLICY_STATUS_TO_FINAL_STATUS[policy_status_for_mode(mode)]
    policy_status = policy_status_for_mode(mode)
    checks = [
        {"name": "synthetic_adapter", "passed": True},
        {"name": "final_status_expected", "passed": final_status == expected},
        {"name": "policy_status_expected", "passed": policy_status in POLICY_STATUS_TO_FINAL_STATUS},
        {
            "name": "verification_pass_not_enough_for_policy_hold",
            "passed": mode not in {"escalation", "blocked"} or final_status != "accepted",
        },
        {"name": "relative_paths_only", "passed": True},
        {"name": "rollback_scope_limited", "passed": True},
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": run_id,
        "passed": all(check["passed"] for check in checks),
        "checks": checks,
    }


def artifact_manifest(run_id: str, root: Path, target_dir: Path, run_dir: Path, mode: str) -> dict:
    entries: list[dict] = []
    for name in ("README.md", "agent_policy.json", "calculator.py", "network_plan.txt", "test_calculator.py"):
        path = target_dir / name
        entries.append(
            {
                "root_label": "target_repo",
                "relative_path": name,
                "artifact_role": "target_fixture",
                "classification": "input",
                "sha256": sha256_file(path),
                "byte_size": path.stat().st_size,
                "generated_by": "agent_evidence_recorder.sample",
                "included_in_replay": True,
                "included_in_rollback": False,
            }
        )
    for name in run_output_artifacts(mode):
        path = run_dir / name
        entries.append(
            {
                "root_label": "run_store",
                "relative_path": name,
                "artifact_role": artifact_role(name),
                "classification": classification(name),
                "sha256": sha256_file(path),
                "byte_size": path.stat().st_size,
                "generated_by": "agent_evidence_recorder.sample",
                "included_in_replay": name in {"run_record.json", "trace.jsonl", "commands.log", "git.diff"},
                "included_in_rollback": name == "git.diff",
            }
        )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "run_id": run_id,
        "manifest_policy": {
            "hashes_after_redaction": True,
            "excluded_self_referential_artifacts": ["artifact_manifest.json"],
        },
        "entries": entries,
    }


def adversarial_corpus() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "purpose": "Public synthetic hard-negative review corpus for the evidence gate.",
        "scope": {
            "data_boundary": "synthetic_public_sample",
            "live_adapter": False,
            "network": "not_used",
            "customer_data": "not_used",
        },
        "traps": list(ADVERSARIAL_TRAPS),
    }


def write_run(root: Path, run_id: str, mode: str, final_status: str) -> dict:
    samples_dir = root / "samples"
    target_dir = samples_dir / "sample-target-repo"
    run_dir = samples_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    run_record_data = run_record(run_id, mode, final_status, run_dir)
    write_json(run_dir / "run_record.json", run_record_data)
    write_text(run_dir / "trace.jsonl", trace(run_id, mode, final_status))
    write_json(run_dir / "commands.log", {"commands": [command_result(mode)]})
    write_text(run_dir / "git.diff", public_diff(mode))
    write_json(run_dir / "sample_verification.json", verification_report(run_id, mode, final_status))
    write_json(run_dir / "sample_policy.json", policy_report(run_id))
    gate = policy_gate_report(run_id, mode)
    write_json(run_dir / "policy_gate_report.json", gate)
    write_json(run_dir / "human_escalation_record.json", human_escalation_record(run_id, final_status, gate))
    write_json(run_dir / "loop_stage_summary.json", loop_stage_summary(run_id, final_status, gate, mode))
    write_text(run_dir / "kill_switch_boundary.md", kill_switch_boundary(run_id, final_status, gate))
    write_text(run_dir / "evidence_packet.md", evidence_packet(run_id, final_status, mode))
    write_text(run_dir / "review_packet.md", review_packet(run_id, final_status, run_record_data))
    if mode == "live_envelope":
        write_live_envelope_artifacts(run_dir, run_id)
    write_text(run_dir / "rollback.sh", rollback_script(), executable=True)
    write_json(run_dir / "artifact_manifest.json", artifact_manifest(run_id, root, target_dir, run_dir, mode))
    return {"run_id": run_id, "run_dir": f"samples/{run_id}", "final_status": final_status}


def pr_review_sample_metadata() -> dict:
    return {
        "number": 24,
        "title": "Add PR review bundle verifier",
        "url": "https://github.com/camirian/agent_evidence-recorder/pull/24",
        "state": "MERGED",
        "author": {"login": "camirian"},
        "baseRefName": "main",
        "headRefName": "feature/verify-pr-review-bundle",
        "changedFiles": 5,
        "additions": 260,
        "deletions": 2,
        "reviewDecision": "",
        "createdAt": "2026-05-31T21:31:00Z",
        "updatedAt": "2026-05-31T21:33:17Z",
        "body": "Adds a verifier for generated PR review bundles.",
        "files": [
            {
                "filename": "README.md",
                "additions": 5,
                "deletions": 0,
                "changes": 5,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -130,6 +130,7 @@ GitHub CLI:",
                        " ```bash",
                        " agent_evidence-recorder pr-review --repo camirian/agent_evidence-recorder --pr 19",
                        "+agent_evidence-recorder verify-pr-review --bundle-dir agent_evidence-pr-review",
                        " ```",
                    ]
                ),
            },
            {
                "filename": "docs/GITHUB_PR_REVIEW_BUNDLE.md",
                "additions": 12,
                "deletions": 0,
                "changes": 12,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -25,6 +25,14 @@ agent_evidence-pr-review/",
                        "   status_checks.json",
                        " ```",
                        "+Verify the generated bundle before reviewing it:",
                        "+",
                        "+```bash",
                        "+agent_evidence-recorder verify-pr-review --bundle-dir agent_evidence-pr-review",
                        "+```",
                    ]
                ),
            },
            {
                "filename": "agent_evidence_recorder/pr_review.py",
                "additions": 149,
                "deletions": 0,
                "changes": 149,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -126,6 +137,20 @@ def write_pr_review_bundle(",
                        "+def verify_pr_review_bundle(bundle_dir: Path) -> dict[str, Any]:",
                        "+    checks: list[dict[str, Any]] = []",
                        "+    def add(name: str, passed: bool, detail: str = \"\") -> None:",
                        "+        checks.append({\"name\": name, \"passed\": passed, \"detail\": detail})",
                    ]
                ),
            },
            {
                "filename": "agent_evidence_recorder/__main__.py",
                "additions": 13,
                "deletions": 1,
                "changes": 14,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -24,6 +24,11 @@ def main() -> int:",
                        "+    verify_pr_review = subcommands.add_parser(\"verify-pr-review\", help=\"verify a generated GitHub PR review bundle\")",
                        "+    verify_pr_review.add_argument(\"--bundle-dir\", default=\"agent_evidence-pr-review\")",
                    ]
                ),
            },
            {
                "filename": "tests/test_sample.py",
                "additions": 83,
                "deletions": 1,
                "changes": 84,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -286,6 +286,30 @@ class PublicSampleTests(unittest.TestCase):",
                        "+    def test_verify_pr_review_bundle_accepts_generated_bundle(self) -> None:",
                        "+        report = verify_pr_review_bundle(output_dir)",
                        "+        self.assertTrue(report[\"passed\"], report)",
                    ]
                ),
            },
        ],
        "commits": [{"oid": "a0f0026"}],
        "statusCheckRollup": [],
    }


def write_pr_review_sample(root: Path) -> dict:
    samples_dir = root / "samples"
    output_dir = samples_dir / PR_REVIEW_SAMPLE_ID
    summary = write_pr_review_bundle(
        pr_review_sample_metadata(),
        output_dir,
        repo="camirian/agent_evidence-recorder",
        source_command=[
            "agent_evidence-recorder",
            "pr-review",
            "--repo",
            "camirian/agent_evidence-recorder",
            "--pr",
            "24",
        ],
        generated_at=GENERATED_AT,
    )
    verification = public_safe_pr_review_verification(verify_pr_review_bundle(output_dir), output_dir, root)
    write_json(output_dir / "sample_verification.json", verification)
    return {
        "bundle_id": PR_REVIEW_SAMPLE_ID,
        "bundle_dir": f"samples/{PR_REVIEW_SAMPLE_ID}",
        "final_status": summary["final_status"],
        "verified": verification["passed"],
    }


def pr_review_low_risk_docs_metadata() -> dict:
    return {
        "number": 40,
        "title": "Clarify quickstart review wording",
        "url": "https://github.com/camirian/agent_evidence-recorder/pull/40",
        "state": "OPEN",
        "author": {"login": "camirian"},
        "baseRefName": "main",
        "headRefName": "docs/clarify-review-wording",
        "changedFiles": 1,
        "additions": 3,
        "deletions": 1,
        "reviewDecision": "",
        "createdAt": "2026-06-01T05:20:00Z",
        "updatedAt": "2026-06-01T05:22:00Z",
        "body": "Clarifies offline review wording in the quickstart without changing behavior.",
        "files": [
            {
                "filename": "QUICKSTART.md",
                "additions": 3,
                "deletions": 1,
                "changes": 4,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -81,7 +81,9 @@ This bundle exercises the GitHub PR review workflow.",
                        "-The generated PR-review fixture does not require GitHub CLI authentication.",
                        "+The generated PR-review fixtures do not require GitHub CLI authentication.",
                        "+They are deterministic and public-safe.",
                        "+Use the low-risk docs fixture to compare an accept-starting packet.",
                    ]
                ),
            }
        ],
        "commits": [{"oid": "lowriskdocs"}],
        "statusCheckRollup": [
            {
                "name": "docs",
                "conclusion": "SUCCESS",
                "status": "COMPLETED",
                "url": "https://github.com/camirian/agent_evidence-recorder/actions/runs/3",
            }
        ],
    }


def write_pr_review_low_risk_docs(root: Path) -> dict:
    samples_dir = root / "samples"
    output_dir = samples_dir / PR_REVIEW_LOW_RISK_DOCS_ID
    summary = write_pr_review_bundle(
        pr_review_low_risk_docs_metadata(),
        output_dir,
        repo="camirian/agent_evidence-recorder",
        source_command=["offline-low-risk-pr-review", "docs-only-successful-checks"],
        generated_at="2026-06-01T05:22:00+00:00",
    )
    verification = public_safe_pr_review_verification(verify_pr_review_bundle(output_dir), output_dir, root)
    write_json(output_dir / "sample_verification.json", verification)
    return {
        "bundle_id": PR_REVIEW_LOW_RISK_DOCS_ID,
        "bundle_dir": f"samples/{PR_REVIEW_LOW_RISK_DOCS_ID}",
        "final_status": summary["final_status"],
        "verified": verification["passed"],
    }


def pr_review_self_demo_metadata() -> dict:
    return {
        "number": 32,
        "title": "Add review outcome verifier",
        "url": "https://github.com/camirian/agent_evidence-recorder/pull/32",
        "state": "MERGED",
        "author": {"login": "camirian"},
        "baseRefName": "main",
        "headRefName": "feature/verify-review-outcome",
        "changedFiles": 6,
        "additions": 224,
        "deletions": 4,
        "reviewDecision": "",
        "createdAt": "2026-06-01T01:20:00Z",
        "updatedAt": "2026-06-01T01:24:21Z",
        "body": "Adds a verifier for filled PR review outcome worksheets.",
        "files": [
            {
                "filename": "QUICKSTART.md",
                "additions": 4,
                "deletions": 0,
                "changes": 4,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -187,6 +187,7 @@ metadata:",
                        " agent_evidence-recorder pr-review --repo camirian/agent_evidence-recorder --pr 19",
                        " agent_evidence-recorder verify-pr-review --bundle-dir agent_evidence-pr-review",
                        " agent_evidence-recorder inspect-pr-review --bundle-dir agent_evidence-pr-review",
                        "+agent_evidence-recorder verify-review-outcome --bundle-dir agent_evidence-pr-review",
                    ]
                ),
            },
            {
                "filename": "README.md",
                "additions": 5,
                "deletions": 0,
                "changes": 5,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -135,6 +135,7 @@ GitHub CLI:",
                        " agent_evidence-recorder pr-review --repo camirian/agent_evidence-recorder --pr 19",
                        " agent_evidence-recorder verify-pr-review --bundle-dir agent_evidence-pr-review",
                        " agent_evidence-recorder inspect-pr-review --bundle-dir agent_evidence-pr-review",
                        "+agent_evidence-recorder verify-review-outcome --bundle-dir agent_evidence-pr-review",
                    ]
                ),
            },
            {
                "filename": "docs/GITHUB_PR_REVIEW_BUNDLE.md",
                "additions": 16,
                "deletions": 1,
                "changes": 17,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -46,6 +47,19 @@ packet.",
                        "+After review, validate the filled outcome worksheet:",
                        "+",
                        "+```bash",
                        "+agent_evidence-recorder verify-review-outcome --bundle-dir agent_evidence-pr-review",
                        "+```",
                        "+",
                        "+This command expects `reviewer_decision` to be one of `accept`, `reject`,",
                        "+`request_changes`, or `needs_followup`.",
                    ]
                ),
            },
            {
                "filename": "agent_evidence_recorder/__main__.py",
                "additions": 14,
                "deletions": 0,
                "changes": 14,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -42,6 +43,15 @@ def main() -> int:",
                        "+    verify_review_outcome = subcommands.add_parser(",
                        "+        \"verify-review-outcome\",",
                        "+        help=\"verify a filled PR review outcome worksheet\",",
                        "+    )",
                    ]
                ),
            },
            {
                "filename": "agent_evidence_recorder/pr_review.py",
                "additions": 77,
                "deletions": 2,
                "changes": 79,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -224,6 +228,77 @@ def verify_pr_review_bundle(bundle_dir: Path) -> dict[str, Any]:",
                        "+def verify_recorded_review_outcome(bundle_dir: Path) -> dict[str, Any]:",
                        "+    checks: list[dict[str, Any]] = []",
                        "+    bundle_report = verify_pr_review_bundle(bundle_dir)",
                        "+    bundle_failures = [check for check in bundle_report[\"checks\"] if not check[\"passed\"]]",
                    ]
                ),
            },
            {
                "filename": "tests/test_sample.py",
                "additions": 108,
                "deletions": 1,
                "changes": 109,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -367,6 +367,108 @@ class PublicSampleTests(unittest.TestCase):",
                        "+    def test_verify_recorded_review_outcome_accepts_filled_low_risk_outcome(self) -> None:",
                        "+        report = verify_recorded_review_outcome(output_dir)",
                        "+        self.assertTrue(report[\"passed\"], report)",
                    ]
                ),
            },
        ],
        "commits": [{"oid": "b98113f"}],
        "statusCheckRollup": [],
    }


def write_pr_review_self_demo(root: Path) -> dict:
    samples_dir = root / "samples"
    output_dir = samples_dir / PR_REVIEW_SELF_DEMO_ID
    summary = write_pr_review_bundle(
        pr_review_self_demo_metadata(),
        output_dir,
        repo="camirian/agent_evidence-recorder",
        source_command=["offline-self-demo", "pr", "32", "commit", "b98113f"],
        generated_at="2026-06-01T01:30:00+00:00",
    )
    review_outcome_path = output_dir / "review_outcome.json"
    review_outcome = json.loads(review_outcome_path.read_text(encoding="utf-8"))
    review_outcome["reviewer_decision"] = "needs_followup"
    review_outcome["reviewer_notes"] = (
        "Self-demo outcome for PR #32: the bundle is inspectable offline and the "
        "recorded outcome verifier works, but missing status-check evidence means "
        "the defensible disposition is needs_followup rather than acceptance."
    )
    write_json(review_outcome_path, review_outcome)
    outcome_verification = verify_recorded_review_outcome(output_dir)
    return {
        "bundle_id": PR_REVIEW_SELF_DEMO_ID,
        "bundle_dir": f"samples/{PR_REVIEW_SELF_DEMO_ID}",
        "final_status": summary["final_status"],
        "reviewer_decision": review_outcome["reviewer_decision"],
        "verified": outcome_verification["passed"],
    }


def pr_review_adversarial_metadata() -> dict:
    return {
        "number": 39,
        "title": "Update",
        "url": "https://github.com/camirian/agent_evidence-recorder/pull/39",
        "state": "OPEN",
        "author": {"login": "camirian"},
        "baseRefName": "main",
        "headRefName": "feature/risky-green-pr",
        "changedFiles": 3,
        "additions": 42,
        "deletions": 7,
        "reviewDecision": "",
        "createdAt": "2026-06-01T05:10:00Z",
        "updatedAt": "2026-06-01T05:15:00Z",
        "body": "Update several files.",
        "files": [
            {
                "filename": ".github/workflows/test.yml",
                "additions": 18,
                "deletions": 3,
                "changes": 21,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -4,7 +4,10 @@ jobs:",
                        "     runs-on: ubuntu-latest",
                        "     steps:",
                        "       - uses: actions/checkout@v4",
                        "-      - run: python3 -m unittest",
                        "+      - run: python3 -m unittest tests.test_sample.PublicSampleTests.test_generate_and_verify_public_samples",
                        "+      - name: Skip slow release boundary",
                        "+        run: echo release boundary checked elsewhere",
                    ]
                ),
            },
            {
                "filename": "SECURITY.md",
                "additions": 10,
                "deletions": 2,
                "changes": 12,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -8,6 +8,9 @@ Please report security issues privately.",
                        "-Do not include secrets in public issues.",
                        "+Do not include secrets in public issues.",
                        "+Security review is required before changing workflow or policy files.",
                    ]
                ),
            },
            {
                "filename": "agent_evidence_recorder/pr_review.py",
                "additions": 14,
                "deletions": 2,
                "changes": 16,
                "status": "modified",
                "patch": "\n".join(
                    [
                        "@@ -865,6 +865,8 @@ def pr_risk_reasons(",
                        "     if high_risk_flags:",
                        "         reasons.append(\"high_risk_file_class_changed\")",
                        "+    if metadata.get(\"title\") == \"Update\":",
                        "+        reasons.append(\"intent_too_vague_for_review\")",
                    ]
                ),
            },
        ],
        "commits": [{"oid": "adversarial"}],
        "statusCheckRollup": [
            {
                "name": "unit",
                "conclusion": "SUCCESS",
                "status": "COMPLETED",
                "url": "https://github.com/camirian/agent_evidence-recorder/actions/runs/1",
            },
            {
                "name": "lint",
                "conclusion": "SUCCESS",
                "status": "COMPLETED",
                "url": "https://github.com/camirian/agent_evidence-recorder/actions/runs/2",
            },
        ],
    }


def write_pr_review_adversarial(root: Path) -> dict:
    samples_dir = root / "samples"
    output_dir = samples_dir / PR_REVIEW_ADVERSARIAL_ID
    summary = write_pr_review_bundle(
        pr_review_adversarial_metadata(),
        output_dir,
        repo="camirian/agent_evidence-recorder",
        source_command=["offline-adversarial-pr-review", "checks-successful-risky-surface"],
        generated_at="2026-06-01T05:15:00+00:00",
    )
    verification = public_safe_pr_review_verification(verify_pr_review_bundle(output_dir), output_dir, root)
    write_json(output_dir / "sample_verification.json", verification)
    return {
        "bundle_id": PR_REVIEW_ADVERSARIAL_ID,
        "bundle_dir": f"samples/{PR_REVIEW_ADVERSARIAL_ID}",
        "final_status": summary["final_status"],
        "verified": verification["passed"],
    }


def public_safe_pr_review_verification(report: dict, output_dir: Path, root: Path) -> dict:
    relative_output_dir = output_dir.relative_to(root).as_posix()
    absolute_output_dir = str(output_dir)
    sanitized = json.loads(json.dumps(report))
    for check in sanitized.get("checks", []):
        detail = str(check.get("detail", ""))
        if absolute_output_dir in detail:
            check["detail"] = detail.replace(absolute_output_dir, relative_output_dir)
    return sanitized


def generate_public_samples(root: Path | None = None) -> dict:
    root = (root or Path.cwd()).resolve()
    samples_dir = root / "samples"
    target_dir = samples_dir / "sample-target-repo"
    if samples_dir.exists():
        shutil.rmtree(samples_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    for name, text in fixture_files(fixed=True).items():
        write_text(target_dir / name, text)

    runs = [
        write_run(root, "agent_evidence-sample-run", "success", "accepted"),
        write_run(root, "agent_evidence-sample-run-rejected", "failure", "rejected"),
        write_run(root, "agent_evidence-sample-run-escalated", "escalation", "needs_human_review"),
        write_run(root, "agent_evidence-sample-run-blocked", "blocked", "blocked"),
        write_run(root, "agent_evidence-sample-run-vague", "vague", "needs_human_review"),
        write_run(root, LIVE_ENVELOPE_RUN_ID, "live_envelope", "blocked"),
    ]
    pr_review_bundle = write_pr_review_sample(root)
    pr_review_low_risk_docs = write_pr_review_low_risk_docs(root)
    pr_review_self_demo = write_pr_review_self_demo(root)
    pr_review_adversarial = write_pr_review_adversarial(root)
    agent_run_receipts = write_agent_run_receipt_examples(root)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": GENERATED_AT,
        "adversarial_corpus": "samples/adversarial-corpus.json",
        "agent_run_receipts": agent_run_receipts,
        "pr_review_adversarial": pr_review_adversarial,
        "pr_review_bundle": pr_review_bundle,
        "pr_review_low_risk_docs": pr_review_low_risk_docs,
        "pr_review_self_demo": pr_review_self_demo,
        "runs": runs,
    }
    write_json(samples_dir / "adversarial-corpus.json", adversarial_corpus())
    write_json(samples_dir / "summary.json", summary)
    return summary


def main() -> int:
    summary = generate_public_samples()
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
