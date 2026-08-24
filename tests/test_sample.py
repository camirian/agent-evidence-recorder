"""Regression tests for the public synthetic sample."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agent_evidence_recorder.pr_review import (
    PR_REVIEW_REQUIRED_ARTIFACTS,
    inspect_pr_review_bundle,
    verify_pr_review_bundle,
    verify_recorded_review_outcome,
    write_pr_review_bundle,
)
from agent_evidence_recorder.determinism import verify_sample_determinism
from agent_evidence_recorder.sample import generate_public_samples
from agent_evidence_recorder.verify_sample import (
    EXPECTED_RUN_STATUSES,
    REQUIRED_RUN_RECORD_FIELDS,
    public_surface_issues,
    tracked_public_surface_paths,
    verify_run,
    verify_samples,
)

REPO_ROOT = Path(__file__).resolve().parents[1]


class PublicSampleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_root = Path(tempfile.mkdtemp(prefix="agent_evidence-recorder-test-"))
        self.addCleanup(lambda: shutil.rmtree(self.temp_root, ignore_errors=True))

    def test_generate_and_verify_public_samples(self) -> None:
        summary = generate_public_samples(self.temp_root)
        self.assertEqual(
            [run["final_status"] for run in summary["runs"]],
            ["accepted", "rejected", "needs_human_review", "blocked", "needs_human_review", "blocked"],
        )
        self.assertEqual(summary["adversarial_corpus"], "samples/adversarial-corpus.json")
        self.assertEqual(summary["pr_review_bundle"]["bundle_dir"], "samples/agent_evidence-pr-review-sample")
        self.assertEqual(
            summary["pr_review_low_risk_docs"]["bundle_dir"],
            "samples/agent_evidence-pr-review-low-risk-docs",
        )
        self.assertEqual(summary["pr_review_adversarial"]["bundle_dir"], "samples/agent_evidence-pr-review-adversarial")
        self.assertTrue(summary["pr_review_bundle"]["verified"])
        self.assertTrue(summary["pr_review_low_risk_docs"]["verified"])
        self.assertTrue(summary["pr_review_adversarial"]["verified"])
        report = verify_samples(self.temp_root)
        self.assertTrue(report["passed"], report)

    def test_sample_determinism_check_passes_after_generation(self) -> None:
        generate_public_samples(self.temp_root)
        report = verify_sample_determinism(self.temp_root)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["current_file_count"], report["regenerated_file_count"])

    def test_sample_determinism_check_catches_tracked_fixture_drift(self) -> None:
        generate_public_samples(self.temp_root)
        review_packet = self.temp_root / "samples" / "agent_evidence-sample-run" / "review_packet.md"
        review_packet.write_text(review_packet.read_text(encoding="utf-8") + "\nUnrecorded drift.\n", encoding="utf-8")

        report = verify_sample_determinism(self.temp_root)
        self.assertFalse(report["passed"], report)
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("tracked_sample_content_matches_regeneration", failed)

    def test_generate_public_samples_includes_verified_pr_review_bundle(self) -> None:
        generate_public_samples(self.temp_root)
        bundle_dir = self.temp_root / "samples" / "agent_evidence-pr-review-sample"
        self.assertTrue((bundle_dir / "review_request.md").is_file())
        self.assertTrue((bundle_dir / "reviewer_packet.md").is_file())
        self.assertTrue((bundle_dir / "review_outcome.json").is_file())
        self.assertTrue((bundle_dir / "sample_verification.json").is_file())
        sample_verification = json.loads((bundle_dir / "sample_verification.json").read_text(encoding="utf-8"))
        run_record = json.loads((bundle_dir / "run_record.json").read_text(encoding="utf-8"))
        review_outcome = json.loads((bundle_dir / "review_outcome.json").read_text(encoding="utf-8"))
        review_request = (bundle_dir / "review_request.md").read_text(encoding="utf-8")
        self.assertTrue(sample_verification["passed"], sample_verification)
        self.assertEqual(run_record["adapter"], "github_pr_review")
        self.assertEqual(run_record["provenance"], "github_pr_review")
        self.assertEqual(review_outcome["status"], "unrecorded")
        self.assertEqual(review_outcome["recommended_starting_decision"], "needs_followup")
        self.assertIn("Would this PR review bundle reduce review burden", review_request)

    def test_adversarial_pr_review_fixture_holds_trust_despite_successful_checks(self) -> None:
        generate_public_samples(self.temp_root)
        bundle_dir = self.temp_root / "samples" / "agent_evidence-pr-review-adversarial"
        run_record = json.loads((bundle_dir / "run_record.json").read_text(encoding="utf-8"))
        self.assertEqual(run_record["provenance"], "github_pr_review")
        risk = json.loads((bundle_dir / "risk_summary.json").read_text(encoding="utf-8"))
        status_checks = json.loads((bundle_dir / "status_checks.json").read_text(encoding="utf-8"))
        review_outcome = json.loads((bundle_dir / "review_outcome.json").read_text(encoding="utf-8"))
        packet = (bundle_dir / "reviewer_packet.md").read_text(encoding="utf-8")

        self.assertEqual(run_record["final_status"], "needs_human_review")
        self.assertEqual(status_checks["summary"]["results"], {"success": 2})
        self.assertEqual(status_checks["summary"]["risk_flags"], [])
        self.assertIn("high_risk_file_class_changed", risk["risk_reasons"])
        self.assertIn("intent_too_vague_for_review", risk["risk_reasons"])
        self.assertIn("sensitive_pr_surface_requires_review", risk["adversarial_traps"])
        self.assertIn("vague_pr_intent_blocks_review_judgment", risk["adversarial_traps"])
        self.assertEqual(review_outcome["recommended_starting_decision"], "needs_followup")
        self.assertIn("Interpretation: reported checks are successful", packet)
        self.assertIn("Confirm successful status checks cover the changed behavior", packet)

    def test_low_risk_docs_pr_review_fixture_starts_with_accept(self) -> None:
        generate_public_samples(self.temp_root)
        bundle_dir = self.temp_root / "samples" / "agent_evidence-pr-review-low-risk-docs"
        run_record = json.loads((bundle_dir / "run_record.json").read_text(encoding="utf-8"))
        self.assertEqual(run_record["provenance"], "github_pr_review")
        risk = json.loads((bundle_dir / "risk_summary.json").read_text(encoding="utf-8"))
        status_checks = json.loads((bundle_dir / "status_checks.json").read_text(encoding="utf-8"))
        changed_files = json.loads((bundle_dir / "changed_files.json").read_text(encoding="utf-8"))
        review_outcome = json.loads((bundle_dir / "review_outcome.json").read_text(encoding="utf-8"))
        request = (bundle_dir / "review_request.md").read_text(encoding="utf-8")
        packet = (bundle_dir / "reviewer_packet.md").read_text(encoding="utf-8")

        self.assertEqual(run_record["final_status"], "accepted_for_review")
        self.assertEqual(risk["risk_level"], "low")
        self.assertEqual(risk["risk_reasons"], [])
        self.assertEqual(status_checks["summary"]["results"], {"success": 1})
        self.assertEqual(status_checks["summary"]["risk_flags"], [])
        self.assertEqual([file["path"] for file in changed_files["files"]], ["QUICKSTART.md"])
        self.assertEqual(review_outcome["recommended_starting_decision"], "accept")
        self.assertIn("Recommended starting decision: `accept`", request)
        self.assertIn("No PR metadata risk reasons detected.", packet)
        self.assertIn("Interpretation: reported checks are successful", packet)

    def test_pr_review_contract_doc_matches_bundle_contract(self) -> None:
        contract = (REPO_ROOT / "docs" / "PR_REVIEW_CONTRACT_V0_2.md").read_text(encoding="utf-8")

        for artifact in sorted(PR_REVIEW_REQUIRED_ARTIFACTS):
            self.assertIn(f"`{artifact}`", contract)
        for final_status in ("accepted_for_review", "needs_human_review"):
            self.assertIn(f"`{final_status}`", contract)
        for decision in ("accept", "reject", "request_changes", "needs_followup"):
            self.assertIn(f"`{decision}`", contract)
        for risk_reason in (
            "high_risk_file_class_changed",
            "status_checks_missing",
            "status_checks_not_successful",
            "review_decision_requires_attention",
            "intent_too_vague_for_review",
            "changed_file_metadata_incomplete",
            "diff_context_incomplete",
            "large_change_set",
        ):
            self.assertIn(f"`{risk_reason}`", contract)
        for trap in (
            "missing_checks_requires_review",
            "non_successful_checks_require_review",
            "review_required_blocks_trust",
            "vague_pr_intent_blocks_review_judgment",
            "incomplete_file_metadata_requires_review",
            "incomplete_diff_context_requires_review",
            "large_diff_requires_review",
            "sensitive_pr_surface_requires_review",
        ):
            self.assertIn(f"`{trap}`", contract)

    def test_pr_review_contract_fixture_matrix_matches_tracked_fixtures(self) -> None:
        expected = {
            "agent_evidence-pr-review-low-risk-docs": ("accepted_for_review", "accept"),
            "agent_evidence-pr-review-adversarial": ("needs_human_review", "needs_followup"),
            "agent_evidence-pr-review-self-demo": ("needs_human_review", "needs_followup"),
            "agent_evidence-pr-review-sample": ("needs_human_review", "needs_followup"),
        }
        for fixture, (expected_status, expected_decision) in expected.items():
            bundle_dir = REPO_ROOT / "samples" / fixture
            run_record = json.loads((bundle_dir / "run_record.json").read_text(encoding="utf-8"))
            review_outcome = json.loads((bundle_dir / "review_outcome.json").read_text(encoding="utf-8"))

            self.assertEqual(run_record["final_status"], expected_status)
            self.assertEqual(review_outcome["recommended_starting_decision"], expected_decision)

    def test_live_adapter_decision_gate_preserves_no_code_boundary(self) -> None:
        gate = (REPO_ROOT / "docs" / "LIVE_ADAPTER_BOUNDARY.md").read_text(encoding="utf-8")

        self.assertIn("No live adapter code exists in this repository.", gate)
        self.assertIn("Default decision: **hold**.", gate)
        self.assertIn("user explicitly approves live-adapter implementation", gate)
        for required_gate in (
            "**Data boundary:**",
            "**Private-data block:**",
            "**Redaction:**",
            "**Timeout limit:**",
            "**Cost limit:**",
            "**Rollback limit:**",
            "**Reviewer outcome:**",
            "**Release boundary:**",
        ):
            self.assertIn(required_gate, gate)
        self.assertIn("not prove live-agent safety", gate)
        self.assertIn("complete rollback", gate)

    def test_live_adapter_readiness_backlog_preserves_hold_boundary(self) -> None:
        backlog = (REPO_ROOT / "docs" / "LIVE_ADAPTER_READINESS_BACKLOG.md").read_text(encoding="utf-8")
        normalized_backlog = " ".join(backlog.split())

        self.assertIn("No live adapter code is approved or present in this repository.", normalized_backlog)
        self.assertIn("Each task below is required before live adapter code.", backlog)
        for required_task in (
            "Input contract",
            "Redaction contract",
            "Timeout and cost budget fields",
            "Failure capture fixture",
            "Reviewer outcome requirement",
            "Effect boundary contract",
            "Public-surface gate",
            "Release-boundary gate",
        ):
            self.assertIn(required_task, backlog)
        self.assertIn("P2 Only After Explicit Approval", backlog)
        self.assertIn("without adding live provider calls", normalized_backlog)

    def test_live_adapter_input_contract_preserves_preflight_boundary(self) -> None:
        contract = (REPO_ROOT / "docs" / "LIVE_ADAPTER_INPUT_CONTRACT.md").read_text(encoding="utf-8")
        normalized_contract = " ".join(contract.split())

        self.assertIn("does not approve live provider calls", normalized_contract)
        self.assertIn("no provider request was sent", normalized_contract)
        for allowed_field in (
            "`task_id`",
            "`task_description`",
            "`allowed_input_refs`",
            "`allowed_effects`",
            "`rollback_scope`",
            "`evidence_export_target`",
            "`timeout_seconds`",
            "`cost_budget`",
            "`reviewer_outcome_required`",
            "`redaction_profile`",
        ):
            self.assertIn(allowed_field, contract)
        for disallowed_input in (
            "absolute local paths",
            "secrets, credentials, tokens, keys, cookies, or session material",
            "private repository paths",
            "customer data, employer data, or unrelated local files",
            "browser, cloud, hardware, deployment, payment, publish, or real-world action",
        ):
            self.assertIn(disallowed_input, normalized_contract)
        for rejection_field in (
            "`final_status`: `blocked`",
            "`failure_class`: `input_rejected`",
            "rejected field names",
        ):
            self.assertIn(rejection_field, contract)
        for effect_boundary_term in (
            "`boundary_type`: `file_scoped_synthetic`",
            "`non_file_effects_allowed`: `false`",
            "`provider_calls_allowed`: `false`",
            "`rollback_scope`: `recorded_git_diff_only`",
            "`read_file`",
            "`create_file`",
            "`modify_file`",
            "`no_op`",
        ):
            self.assertIn(effect_boundary_term, contract)

    def test_live_adapter_redaction_contract_preserves_evidence_annotations(self) -> None:
        contract = (REPO_ROOT / "docs" / "LIVE_ADAPTER_REDACTION_CONTRACT.md").read_text(encoding="utf-8")
        normalized_contract = " ".join(contract.split())

        self.assertIn("does not approve live provider calls", normalized_contract)
        self.assertIn("Blocked records must state that no provider request was sent.", contract)
        for replacement in (
            "[REDACTED_SECRET]",
            "[REDACTED_LOCAL_PATH]",
            "[REDACTED_ENV_VALUE]",
            "[REDACTED_CREDENTIAL]",
            "[REDACTED_PERSONAL_ID]",
            "[REDACTED_PRIVATE_REF]",
        ):
            self.assertIn(replacement, contract)
        for metadata_field in (
            "\"redaction_profile\"",
            "\"redactions_applied\"",
            "\"redaction_required_before_provider_call\"",
            "\"raw_sensitive_values_exported\"",
        ):
            self.assertIn(metadata_field, contract)
        for never_exported in (
            "raw secrets, tokens, keys, cookies, or session material",
            "`.env` file contents",
            "full absolute paths from the operator machine",
            "private repository contents",
            "customer data, employer data, or unrelated local files",
        ):
            self.assertIn(never_exported, normalized_contract)

    def test_run_record_uses_agent_evidence_kernel_fields(self) -> None:
        generate_public_samples(self.temp_root)
        record = json.loads(
            (self.temp_root / "samples" / "agent_evidence-sample-run" / "run_record.json").read_text(encoding="utf-8")
        )
        self.assertFalse(REQUIRED_RUN_RECORD_FIELDS - set(record))
        self.assertEqual(record["adapter"], "synthetic_sample")
        self.assertEqual(record["provenance"], "synthetic_sample")
        self.assertEqual(record["effect_boundary"]["boundary_type"], "file_scoped_synthetic")
        self.assertFalse(record["effect_boundary"]["non_file_effects_allowed"])
        for section in ("input_artifacts", "output_artifacts"):
            for artifact in record[section]:
                self.assertFalse(artifact["relative_path"].startswith("/"))

    def test_review_packet_captures_run_provenance_and_workflow(self) -> None:
        generate_public_samples(self.temp_root)
        accepted_packet = (self.temp_root / "samples" / "agent_evidence-sample-run" / "review_packet.md").read_text(
            encoding="utf-8"
        )
        live_packet = (
            self.temp_root / "samples" / "agent_evidence-sample-run-live-envelope" / "review_packet.md"
        ).read_text(encoding="utf-8")
        self.assertIn("- Provenance: `synthetic_sample`", accepted_packet)
        self.assertIn("- Workflow: `coding_agent_run`", accepted_packet)
        self.assertIn("- Provider calls executed: `false`", accepted_packet)
        self.assertIn("- Reviewer outcome required: `false`", accepted_packet)
        self.assertIn("- Effect boundary: `file_scoped_synthetic`", accepted_packet)
        self.assertIn("- Non-file effects allowed: `false`", accepted_packet)
        self.assertIn("- Rollback scope: `recorded_git_diff_only`", accepted_packet)

        self.assertIn("- Provenance: `synthetic_live_envelope`", live_packet)
        self.assertIn("- Workflow: `live_preflight_envelope`", live_packet)
        self.assertIn("## Live Preflight Evidence (Synthetic)", live_packet)
        self.assertIn("- Provider calls executed: `false`", live_packet)
        self.assertIn("- Provider request blocked in preflight: `true`", live_packet)
        self.assertIn("- Redaction count: `4`", live_packet)
        self.assertIn("- Non-file effects allowed: `false`", live_packet)

    def test_live_envelope_run_record_uses_live_envelope_provenance(self) -> None:
        generate_public_samples(self.temp_root)
        record = json.loads(
            (self.temp_root / "samples" / "agent_evidence-sample-run-live-envelope" / "run_record.json").read_text(encoding="utf-8")
        )
        self.assertEqual(record["provenance"], "synthetic_live_envelope")

    def test_synthetic_run_records_capture_budget_and_failure_fields(self) -> None:
        generate_public_samples(self.temp_root)
        expected_failure_classes = {
            "agent_evidence-sample-run": "none",
            "agent_evidence-sample-run-rejected": "verifier_failure",
            "agent_evidence-sample-run-escalated": "policy_review_required",
            "agent_evidence-sample-run-blocked": "forbidden_effect_requested",
            "agent_evidence-sample-run-vague": "review_judgment_blocked",
            "agent_evidence-sample-run-live-envelope": "input_rejected",
        }
        for run_id, expected_failure_class in expected_failure_classes.items():
            record = json.loads((self.temp_root / "samples" / run_id / "run_record.json").read_text(encoding="utf-8"))
            limits = record["execution_limits"]
            failure = record["failure_capture"]

            self.assertEqual(limits["timeout_seconds"], 30)
            self.assertEqual(limits["cost_budget"]["maximum"], 0)
            self.assertEqual(limits["cost_budget"]["actual"], 0)
            self.assertFalse(limits["cost_budget"]["provider_account_required"])
            self.assertEqual(failure["failure_class"], expected_failure_class)
            self.assertEqual(failure["verifier_failure_observed"], run_id.endswith("-rejected"))
            self.assertIn("sample_verification.json", failure["recorded_evidence"])

    def test_synthetic_run_records_capture_file_scoped_effect_boundary(self) -> None:
        generate_public_samples(self.temp_root)
        for run_id in EXPECTED_RUN_STATUSES:
            record = json.loads((self.temp_root / "samples" / run_id / "run_record.json").read_text(encoding="utf-8"))
            gate = json.loads((self.temp_root / "samples" / run_id / "policy_gate_report.json").read_text(encoding="utf-8"))
            boundary = record["effect_boundary"]
            observed_paths = {effect["path"] for effect in boundary["observed_effects"]}

            self.assertEqual(boundary["schema_version"], "agent_evidence_recorder.effect_boundary.v0")
            self.assertEqual(boundary["boundary_type"], "file_scoped_synthetic")
            self.assertEqual(set(boundary["allowed_effects"]), {"read_file", "create_file", "modify_file", "no_op"})
            self.assertIn("network_call", boundary["disallowed_effects"])
            self.assertFalse(boundary["non_file_effects_allowed"])
            self.assertFalse(boundary["provider_calls_allowed"])
            self.assertFalse(boundary["external_effects_rollbackable"])
            self.assertEqual(boundary["rollback_scope"], "recorded_git_diff_only")
            self.assertEqual(gate["effect_boundary"], boundary)
            for effect in boundary["observed_effects"]:
                self.assertEqual(effect["effect_type"], "modify_file")
                self.assertTrue(effect["file_scoped"])
                self.assertEqual(effect["rollback_scope"], "recorded_git_diff")
                self.assertFalse(effect["path"].startswith("/"))
            if run_id.endswith("-blocked") or run_id.endswith("-live-envelope"):
                self.assertTrue(boundary["requested_non_file_effects"])
                self.assertTrue(all(effect["status"] == "blocked" for effect in boundary["requested_non_file_effects"]))
            else:
                self.assertFalse(boundary["requested_non_file_effects"])
            self.assertTrue(observed_paths)

    def test_policy_gate_samples_cover_accept_reject_escalate_and_block(self) -> None:
        generate_public_samples(self.temp_root)
        for run_id, expected_status in EXPECTED_RUN_STATUSES.items():
            run_dir = self.temp_root / "samples" / run_id
            record = json.loads((run_dir / "run_record.json").read_text(encoding="utf-8"))
            gate = json.loads((run_dir / "policy_gate_report.json").read_text(encoding="utf-8"))
            escalation = json.loads((run_dir / "human_escalation_record.json").read_text(encoding="utf-8"))
            self.assertEqual(record["final_status"], expected_status)
            if expected_status == "accepted":
                self.assertEqual(gate["final_policy_status"], "passed")
            if expected_status == "rejected":
                self.assertEqual(gate["final_policy_status"], "verification_failed")
            if expected_status == "needs_human_review":
                self.assertEqual(gate["final_policy_status"], "needs_human_review")
                self.assertTrue(gate["escalations"])
                self.assertNotEqual(escalation["required_reviewer_action"], "none")
            if expected_status == "blocked":
                self.assertEqual(gate["final_policy_status"], "blocked")
                self.assertTrue(gate["violations"])
                self.assertNotEqual(escalation["required_reviewer_action"], "none")

    def test_adversarial_corpus_covers_review_traps(self) -> None:
        generate_public_samples(self.temp_root)
        corpus = json.loads((self.temp_root / "samples" / "adversarial-corpus.json").read_text(encoding="utf-8"))
        traps = {trap["trap_id"]: trap for trap in corpus["traps"]}
        self.assertIn("verification_failed_but_evidence_retained", traps)
        self.assertIn("policy_sensitive_file_changed", traps)
        self.assertIn("verification_passed_but_forbidden_effect_requested", traps)
        self.assertIn("rollback_claim_limited_to_recorded_diff", traps)
        self.assertIn("trust_not_granted_by_verification_alone", traps)
        self.assertIn("vague_intent_blocks_review_judgment", traps)
        self.assertIn("unrelated_diff_requires_review", traps)
        self.assertIn("weak_provenance_requires_review", traps)
        self.assertIn("stale_evidence_requires_review", traps)
        self.assertEqual(traps["verification_passed_but_forbidden_effect_requested"]["severity"], "blocker")
        self.assertEqual(traps["rollback_claim_limited_to_recorded_diff"]["expected_final_status"], "blocked")
        self.assertEqual(traps["vague_intent_blocks_review_judgment"]["run_id"], "agent_evidence-sample-run-vague")
        self.assertIn("live_input_rejected_by_preflight", traps)
        self.assertEqual(traps["live_input_rejected_by_preflight"]["run_id"], "agent_evidence-sample-run-live-envelope")
        self.assertEqual(traps["live_input_rejected_by_preflight"]["failure_class"], "input_rejected")
        self.assertEqual(traps["live_input_rejected_by_preflight"]["expected_policy_status"], "blocked")

    def test_live_envelope_sample_run_has_preflight_artifacts(self) -> None:
        generate_public_samples(self.temp_root)
        run_dir = self.temp_root / "samples" / "agent_evidence-sample-run-live-envelope"
        run_record = json.loads((run_dir / "run_record.json").read_text(encoding="utf-8"))
        policy_gate = json.loads((run_dir / "policy_gate_report.json").read_text(encoding="utf-8"))
        redaction_report = json.loads((run_dir / "live_redaction_report.json").read_text(encoding="utf-8"))
        rejection_record = json.loads((run_dir / "provider_request_rejection_record.json").read_text(encoding="utf-8"))
        trace = (run_dir / "trace.jsonl").read_text(encoding="utf-8")
        review_packet = (run_dir / "review_packet.md").read_text(encoding="utf-8")
        live_artifacts = [
            "live_request_envelope.json",
            "live_redaction_report.json",
            "provider_request_rejection_record.json",
        ]

        self.assertEqual(run_record["workflow_type"], "live_preflight_envelope")
        self.assertTrue(run_record["live_envelope"])
        self.assertFalse(run_record["live_envelope"]["provider_request_sent"])
        self.assertEqual(run_record["failure_capture"]["failure_class"], "input_rejected")
        self.assertEqual(policy_gate["final_policy_status"], "blocked")
        self.assertIn("provider_request_rejection_record.json", trace)
        output_artifact_paths = [entry["relative_path"] for entry in run_record["output_artifacts"]]
        for artifact in live_artifacts:
            self.assertTrue((run_dir / artifact).is_file(), artifact)
            self.assertIn(f"samples/agent_evidence-sample-run-live-envelope/{artifact}", output_artifact_paths)
        observed_values = {
            value
            for entry in policy_gate["violations"]
            for value in entry.get("observed_values", [])
            if entry.get("trigger") == "input_rejected"
        }
        self.assertIn("[REDACTED_LOCAL_PATH]", observed_values)
        self.assertIn("[REDACTED_SECRET]", observed_values)
        self.assertIn("[REDACTED_CUSTOMER_DATA]", observed_values)
        self.assertIn("[REDACTED_LOCAL_FILE]", observed_values)
        rules = {entry["rule"] for entry in redaction_report["redactions_applied"]}
        self.assertEqual(rejection_record["redaction_count"], 4)
        self.assertTrue({"absolute_path", "secret_shaped_token", "customer_data_shape", "unrelated_local_file"} <= rules)
        self.assertEqual(set(run_record["effect_boundary"]["allowed_effects"]), {"read_file", "create_file", "modify_file", "no_op"})
        self.assertIn("effect_boundary", json.loads((run_dir / "live_request_envelope.json").read_text(encoding="utf-8")))
        self.assertIn("- Relevant artifacts: `samples/agent_evidence-sample-run-live-envelope/live_request_envelope.json, samples/agent_evidence-sample-run-live-envelope/live_redaction_report.json, samples/agent_evidence-sample-run-live-envelope/provider_request_rejection_record.json`", review_packet)

    def test_public_surface_checker_catches_path_and_key_shaped_values(self) -> None:
        bad = self.temp_root / "bad.txt"
        bad.write_text(
            "path=" + "/" + "home" + "/synthetic/sample\n"
            "repo=" + "onyx-" + "citadel" + "\n"
            "key=" + "gho_" + "examplevalue12345\n",
            encoding="utf-8",
        )
        issues = public_surface_issues([bad])
        self.assertGreaterEqual(len(issues), 3)

    def test_tracked_public_surface_scan_uses_git_files_when_available(self) -> None:
        generate_public_samples(self.temp_root)
        private_dir = self.temp_root / ("strategy-" + "vault")
        private_dir.mkdir()
        (private_dir / "notes.md").write_text("path=" + "/" + "home" + "/private\n", encoding="utf-8")
        paths = tracked_public_surface_paths(self.temp_root)
        self.assertFalse(any(("strategy-" + "vault") in path.parts for path in paths))

    def test_verify_run_rejects_stale_manifested_artifact(self) -> None:
        generate_public_samples(self.temp_root)
        run_dir = self.temp_root / "samples" / "agent_evidence-sample-run"
        review_packet = run_dir / "review_packet.md"
        review_packet.write_text(review_packet.read_text(encoding="utf-8") + "\nStale mutation.\n", encoding="utf-8")

        checks = verify_run(run_dir, EXPECTED_RUN_STATUSES["agent_evidence-sample-run"])
        failed = {check["name"] for check in checks if not check["passed"]}
        self.assertIn("agent_evidence-sample-run:manifest_integrity", failed)

    def test_verify_run_rejects_broad_rollback_boundary(self) -> None:
        generate_public_samples(self.temp_root)
        run_dir = self.temp_root / "samples" / "agent_evidence-sample-run"
        manifest_path = run_dir / "artifact_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        for entry in manifest["entries"]:
            if entry["relative_path"] == "review_packet.md":
                entry["included_in_rollback"] = True
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        checks = verify_run(run_dir, EXPECTED_RUN_STATUSES["agent_evidence-sample-run"])
        failed = {check["name"] for check in checks if not check["passed"]}
        self.assertIn("agent_evidence-sample-run:rollback_boundary_limited", failed)

    def test_verify_run_rejects_non_file_effect_boundary_drift(self) -> None:
        generate_public_samples(self.temp_root)
        run_dir = self.temp_root / "samples" / "agent_evidence-sample-run"
        record_path = run_dir / "run_record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["effect_boundary"]["non_file_effects_allowed"] = True
        record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        checks = verify_run(run_dir, EXPECTED_RUN_STATUSES["agent_evidence-sample-run"])
        failed = {check["name"] for check in checks if not check["passed"]}
        self.assertIn("agent_evidence-sample-run:effect_boundary_contract", failed)
        self.assertIn("agent_evidence-sample-run:policy_gate_effect_boundary_matches_run_record", failed)

    def test_pr_review_bundle_uses_public_pr_metadata(self) -> None:
        metadata = {
            "number": 19,
            "title": "Add reviewer packet index",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/19",
            "state": "MERGED",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "docs/reviewer-packet-index",
            "changedFiles": 2,
            "additions": 12,
            "deletions": 0,
            "reviewDecision": "",
            "createdAt": "2026-05-31T05:30:16Z",
            "updatedAt": "2026-05-31T05:30:37Z",
            "body": "Synthetic PR body",
            "files": [
                {"path": "README.md", "additions": 6, "deletions": 0},
                {"path": ".github/workflows/test.yml", "additions": 6, "deletions": 0},
            ],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [{"name": "unit", "conclusion": "SUCCESS"}],
        }
        output_dir = self.temp_root / "pr-review"
        summary = write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        self.assertEqual(summary["final_status"], "needs_human_review")
        self.assertTrue((output_dir / "reviewer_packet.md").exists())
        run_record = json.loads((output_dir / "run_record.json").read_text(encoding="utf-8"))
        risk = json.loads((output_dir / "risk_summary.json").read_text(encoding="utf-8"))
        changed = json.loads((output_dir / "changed_files.json").read_text(encoding="utf-8"))
        file_diffs = json.loads((output_dir / "file_diffs.json").read_text(encoding="utf-8"))
        status_checks = json.loads((output_dir / "status_checks.json").read_text(encoding="utf-8"))
        review_outcome = json.loads((output_dir / "review_outcome.json").read_text(encoding="utf-8"))
        self.assertEqual(run_record["adapter"], "github_pr_review")
        self.assertIn("ci_or_automation", risk["risk_flags"])
        self.assertIn("diff_context_incomplete", risk["risk_reasons"])
        self.assertIn("sensitive_pr_surface_requires_review", risk["adversarial_traps"])
        self.assertEqual(changed["files"][0]["path"], "README.md")
        self.assertEqual(file_diffs["summary"]["files_without_patch"], 2)
        self.assertEqual(status_checks["summary"]["results"], {"success": 1})
        self.assertEqual(review_outcome["status"], "unrecorded")
        self.assertEqual(review_outcome["recommended_starting_decision"], "needs_followup")
        self.assertIn("reviewer_packet.md", review_outcome["evidence_references"])
        self.assertIn("file_diffs.json", run_record["output_artifacts"])
        self.assertIn("status_checks.json", run_record["output_artifacts"])
        self.assertIn("review_outcome.json", run_record["output_artifacts"])
        self.assertIn("review_request.md", run_record["output_artifacts"])

    def test_pr_review_bundle_accepts_low_risk_checked_metadata(self) -> None:
        metadata = {
            "number": 21,
            "title": "Clarify reviewer packet wording",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/21",
            "state": "OPEN",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "docs/clarify-reviewer-packet",
            "changedFiles": 1,
            "additions": 4,
            "deletions": 2,
            "reviewDecision": "",
            "createdAt": "2026-05-31T18:00:00Z",
            "updatedAt": "2026-05-31T18:05:00Z",
            "body": "Clarifies the reviewer packet description without changing behavior.",
            "files": [
                {
                    "filename": "docs/REVIEWER_PACKET_INDEX.md",
                    "additions": 4,
                    "deletions": 2,
                    "changes": 6,
                    "status": "modified",
                    "patch": "@@ -1,2 +1,2 @@\n-old wording\n+clear wording",
                }
            ],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [{"name": "test", "conclusion": "SUCCESS"}],
        }
        output_dir = self.temp_root / "pr-review-low-risk"
        summary = write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        risk = json.loads((output_dir / "risk_summary.json").read_text(encoding="utf-8"))
        review_outcome = json.loads((output_dir / "review_outcome.json").read_text(encoding="utf-8"))
        packet = (output_dir / "reviewer_packet.md").read_text(encoding="utf-8")
        review_request = (output_dir / "review_request.md").read_text(encoding="utf-8")
        self.assertEqual(summary["final_status"], "accepted_for_review")
        self.assertEqual(risk["risk_level"], "low")
        self.assertEqual(review_outcome["recommended_starting_decision"], "accept")
        self.assertEqual(risk["risk_reasons"], [])
        self.assertEqual(risk["status_check_results"], {"success": 1})
        self.assertIn("No PR metadata risk reasons detected.", packet)
        self.assertIn("## Review Decision Checklist", packet)
        self.assertIn("Confirm successful status checks cover the changed behavior", packet)
        self.assertIn("Inspect each bounded diff excerpt", packet)
        self.assertIn("```diff", packet)
        self.assertIn("+clear wording", packet)
        self.assertIn("Interpretation: reported checks are successful", packet)
        self.assertIn("`test` result: `success`; conclusion: `success`", packet)
        self.assertIn("Recommended starting decision: `accept`", review_request)
        self.assertIn("review_outcome.json", review_request)

    def test_pr_review_bundle_surfaces_pr_specific_adversarial_traps(self) -> None:
        metadata = {
            "number": 22,
            "title": "Update",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/22",
            "state": "OPEN",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "feature/broad-update",
            "changedFiles": 25,
            "additions": 450,
            "deletions": 75,
            "reviewDecision": "REVIEW_REQUIRED",
            "createdAt": "2026-05-31T18:00:00Z",
            "updatedAt": "2026-05-31T18:05:00Z",
            "body": "",
            "files": [
                {"path": "agent_evidence_recorder/pr_review.py", "additions": 350, "deletions": 50},
                {"path": "SECURITY.md", "additions": 100, "deletions": 25},
            ],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [],
        }
        output_dir = self.temp_root / "pr-review-traps"
        summary = write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        risk = json.loads((output_dir / "risk_summary.json").read_text(encoding="utf-8"))
        packet = (output_dir / "reviewer_packet.md").read_text(encoding="utf-8")
        self.assertEqual(summary["final_status"], "needs_human_review")
        self.assertEqual(risk["risk_level"], "needs_review")
        self.assertIn("status_checks_missing", risk["risk_reasons"])
        self.assertIn("review_decision_requires_attention", risk["risk_reasons"])
        self.assertIn("intent_too_vague_for_review", risk["risk_reasons"])
        self.assertIn("changed_file_metadata_incomplete", risk["risk_reasons"])
        self.assertIn("large_change_set", risk["risk_reasons"])
        self.assertIn("high_risk_file_class_changed", risk["risk_reasons"])
        self.assertIn("diff_context_incomplete", risk["risk_reasons"])
        self.assertIn("vague_pr_intent_blocks_review_judgment", risk["adversarial_traps"])
        self.assertIn("incomplete_file_metadata_requires_review", risk["adversarial_traps"])
        self.assertIn("incomplete_diff_context_requires_review", risk["adversarial_traps"])
        self.assertIn("large_diff_requires_review", risk["adversarial_traps"])
        self.assertIn("Changed files observed/reported: 2/25", packet)
        self.assertIn("Resolve `status_checks_missing`", packet)
        self.assertIn("Resolve `intent_too_vague_for_review`", packet)
        self.assertIn("Open the PR on GitHub for any missing, omitted, or truncated diff context.", packet)

    def test_pr_review_bundle_surfaces_non_successful_status_checks(self) -> None:
        metadata = {
            "number": 23,
            "title": "Clarify status check review output",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/23",
            "state": "OPEN",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "feature/status-check-output",
            "changedFiles": 1,
            "additions": 14,
            "deletions": 3,
            "reviewDecision": "",
            "createdAt": "2026-05-31T18:00:00Z",
            "updatedAt": "2026-05-31T18:05:00Z",
            "body": "Adds status check conclusions to the generated reviewer packet.",
            "files": [{"path": "agent_evidence_recorder/pr_review.py", "additions": 14, "deletions": 3}],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [
                {"name": "unit", "conclusion": "SUCCESS", "url": "https://example.test/unit"},
                {"name": "lint", "conclusion": "FAILURE", "url": "https://example.test/lint"},
                {"name": "integration", "status": "IN_PROGRESS"},
            ],
        }
        output_dir = self.temp_root / "pr-review-status-checks"
        summary = write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        risk = json.loads((output_dir / "risk_summary.json").read_text(encoding="utf-8"))
        status_checks = json.loads((output_dir / "status_checks.json").read_text(encoding="utf-8"))
        packet = (output_dir / "reviewer_packet.md").read_text(encoding="utf-8")
        self.assertEqual(summary["final_status"], "needs_human_review")
        self.assertIn("status_checks_not_successful", risk["risk_reasons"])
        self.assertIn("non_successful_checks_require_review", risk["adversarial_traps"])
        self.assertEqual(risk["status_check_results"], {"failure": 1, "in_progress": 1, "success": 1})
        self.assertIn("status_check_failed", status_checks["summary"]["risk_flags"])
        self.assertIn("status_check_incomplete", status_checks["summary"]["risk_flags"])
        self.assertIn("Inspect non-successful or incomplete status checks before accepting the PR.", packet)
        self.assertIn("Interpretation: at least one reported check is failed, incomplete, or ambiguous.", packet)
        self.assertIn("`lint` result: `failure`; conclusion: `failure`; flags: status_check_failed", packet)
        self.assertIn("`integration` result: `in_progress`; status: `in_progress`; flags: status_check_incomplete", packet)

    def test_verify_pr_review_bundle_accepts_generated_bundle(self) -> None:
        metadata = {
            "number": 24,
            "title": "Clarify generated PR review verification",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/24",
            "state": "OPEN",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "feature/verify-pr-review",
            "changedFiles": 1,
            "additions": 8,
            "deletions": 1,
            "reviewDecision": "",
            "createdAt": "2026-05-31T18:00:00Z",
            "updatedAt": "2026-05-31T18:05:00Z",
            "body": "Adds a verifier for generated PR review bundles.",
            "files": [
                {
                    "filename": "agent_evidence_recorder/pr_review.py",
                    "additions": 8,
                    "deletions": 1,
                    "changes": 9,
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                }
            ],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [{"name": "unit", "conclusion": "SUCCESS"}],
        }
        output_dir = self.temp_root / "pr-review-verify"
        write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        report = verify_pr_review_bundle(output_dir)
        self.assertTrue(report["passed"], report)

    def test_verify_recorded_review_outcome_accepts_filled_low_risk_outcome(self) -> None:
        metadata = {
            "number": 28,
            "title": "Clarify docs wording",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/28",
            "state": "OPEN",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "docs/clarify-wording",
            "changedFiles": 1,
            "additions": 2,
            "deletions": 1,
            "reviewDecision": "",
            "createdAt": "2026-05-31T18:00:00Z",
            "updatedAt": "2026-05-31T18:05:00Z",
            "body": "Clarifies README wording for the generated review workflow.",
            "files": [
                {
                    "filename": "README.md",
                    "additions": 2,
                    "deletions": 1,
                    "changes": 3,
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                }
            ],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [{"name": "unit", "conclusion": "SUCCESS"}],
        }
        output_dir = self.temp_root / "pr-review-recorded-accept"
        write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        review_outcome_path = output_dir / "review_outcome.json"
        review_outcome = json.loads(review_outcome_path.read_text(encoding="utf-8"))
        review_outcome["reviewer_decision"] = "accept"
        review_outcome_path.write_text(json.dumps(review_outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        report = verify_recorded_review_outcome(output_dir)
        self.assertTrue(report["passed"], report)

        review_outcome["evidence_references"].append("missing-evidence.json")
        review_outcome_path.write_text(json.dumps(review_outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report = verify_recorded_review_outcome(output_dir)
        self.assertFalse(report["passed"], report)
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("evidence_references_exist", failed)

    def test_verify_recorded_review_outcome_requires_notes_for_risky_accept(self) -> None:
        metadata = {
            "number": 29,
            "title": "Change CI workflow",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/29",
            "state": "OPEN",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "ci/change-workflow",
            "changedFiles": 1,
            "additions": 6,
            "deletions": 1,
            "reviewDecision": "",
            "createdAt": "2026-05-31T18:00:00Z",
            "updatedAt": "2026-05-31T18:05:00Z",
            "body": "Updates CI workflow.",
            "files": [
                {
                    "filename": ".github/workflows/test.yml",
                    "additions": 6,
                    "deletions": 1,
                    "changes": 7,
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                }
            ],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [],
        }
        output_dir = self.temp_root / "pr-review-recorded-risky"
        write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        review_outcome_path = output_dir / "review_outcome.json"
        review_outcome = json.loads(review_outcome_path.read_text(encoding="utf-8"))
        review_outcome["reviewer_decision"] = "accept"
        review_outcome_path.write_text(json.dumps(review_outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")

        report = verify_recorded_review_outcome(output_dir)
        self.assertFalse(report["passed"], report)
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("reviewer_notes_required_for_risky_accept", failed)

        review_outcome["reviewer_notes"] = "Accepted after manually inspecting CI diff and missing-check context."
        review_outcome_path.write_text(json.dumps(review_outcome, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        report = verify_recorded_review_outcome(output_dir)
        self.assertTrue(report["passed"], report)

    def test_tracked_pr_review_self_demo_records_reviewed_outcome(self) -> None:
        bundle_dir = REPO_ROOT / "samples" / "agent_evidence-pr-review-self-demo"
        review_outcome = json.loads((bundle_dir / "review_outcome.json").read_text(encoding="utf-8"))

        self.assertEqual(review_outcome["pr_number"], 32)
        self.assertEqual(review_outcome["reviewer_decision"], "needs_followup")
        self.assertIn("missing status-check evidence", review_outcome["reviewer_notes"])

        outcome_report = verify_recorded_review_outcome(bundle_dir)
        self.assertTrue(outcome_report["passed"], outcome_report)

        bundle_report = verify_pr_review_bundle(bundle_dir)
        failed = {check["name"] for check in bundle_report["checks"] if not check["passed"]}
        self.assertEqual(
            failed,
            {
                "manifest:review_outcome.json:sha256",
                "manifest:review_outcome.json:bytes",
            },
        )

    def test_inspect_pr_review_bundle_summarizes_review_path(self) -> None:
        metadata = {
            "number": 26,
            "title": "Clarify review request summary",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/26",
            "state": "OPEN",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "feature/review-request-summary",
            "changedFiles": 1,
            "additions": 8,
            "deletions": 1,
            "reviewDecision": "",
            "createdAt": "2026-05-31T18:00:00Z",
            "updatedAt": "2026-05-31T18:05:00Z",
            "body": "Clarifies generated PR review request output.",
            "files": [
                {
                    "filename": "agent_evidence_recorder/pr_review.py",
                    "additions": 8,
                    "deletions": 1,
                    "changes": 9,
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                }
            ],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [{"name": "unit", "conclusion": "SUCCESS"}],
        }
        output_dir = self.temp_root / "pr-review-inspect"
        write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        summary = inspect_pr_review_bundle(output_dir)
        self.assertIn("Bundle verification: passed", summary)
        self.assertIn("Final status: accepted_for_review", summary)
        self.assertIn("Status checks: total=1; results=success=1; risk flags=none", summary)
        self.assertIn("successful, but they are not proof", summary)
        self.assertIn("- unit: result=success; conclusion=success; risk flags=none", summary)
        self.assertIn("Next action:", summary)
        self.assertIn("Open next:", summary)
        self.assertIn("- review_request.md", summary)
        self.assertIn("- reviewer_packet.md", summary)
        self.assertIn("Would this PR review bundle reduce review burden", summary)

    def test_inspect_pr_review_bundle_surfaces_adversarial_review_signal(self) -> None:
        bundle_dir = REPO_ROOT / "samples" / "agent_evidence-pr-review-adversarial"
        summary = inspect_pr_review_bundle(bundle_dir)

        self.assertIn("Bundle verification: passed", summary)
        self.assertIn("Final status: needs_human_review", summary)
        self.assertIn("Recommended starting decision: needs_followup", summary)
        self.assertIn("Status checks: total=2; results=success=2; risk flags=none", summary)
        self.assertIn(
            "Interpretation: reported checks are successful, but they are not proof",
            summary,
        )
        self.assertIn(
            "Risk flags: ci_or_automation, documentation, security_or_policy, source_code",
            summary,
        )
        self.assertIn("- high_risk_file_class_changed", summary)
        self.assertIn("- intent_too_vague_for_review", summary)
        self.assertIn("- sensitive_pr_surface_requires_review", summary)
        self.assertIn("- vague_pr_intent_blocks_review_judgment", summary)
        self.assertIn("- unit: result=success; conclusion=success; status=completed; risk flags=none", summary)
        self.assertIn("- lint: result=success; conclusion=success; status=completed; risk flags=none", summary)
        self.assertIn("successful checks are evidence, not approval", summary)

    def test_inspect_pr_review_bundle_reports_missing_bundle_repair(self) -> None:
        summary = inspect_pr_review_bundle(self.temp_root / "missing-pr-review")
        self.assertIn("Bundle verification: failed", summary)
        self.assertIn("Open next:", summary)
        self.assertIn("- no reviewer artifacts available yet", summary)
        self.assertIn("Repair before review:", summary)
        self.assertIn("Create a PR review bundle first", summary)
        self.assertIn("Failed verification checks:", summary)

    def test_inspect_pr_review_bundle_reports_artifact_repair_hints(self) -> None:
        metadata = {
            "number": 27,
            "title": "Record reviewer worksheet",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/27",
            "state": "OPEN",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "feature/review-outcome",
            "changedFiles": 1,
            "additions": 8,
            "deletions": 1,
            "reviewDecision": "",
            "createdAt": "2026-05-31T18:00:00Z",
            "updatedAt": "2026-05-31T18:05:00Z",
            "body": "Records an unfilled review outcome worksheet.",
            "files": [
                {
                    "filename": "agent_evidence_recorder/pr_review.py",
                    "additions": 8,
                    "deletions": 1,
                    "changes": 9,
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                }
            ],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [{"name": "unit", "conclusion": "SUCCESS"}],
        }
        output_dir = self.temp_root / "pr-review-broken-inspect"
        write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        (output_dir / "review_outcome.json").unlink()
        (output_dir / "risk_summary.json").write_text("{not-json\n", encoding="utf-8")
        summary = inspect_pr_review_bundle(output_dir)
        self.assertIn("Bundle verification: failed", summary)
        self.assertIn("Repair before review:", summary)
        self.assertIn("Regenerate or restore missing artifacts: review_outcome.json.", summary)
        self.assertIn("Fix invalid JSON or regenerate artifact: risk_summary.json.", summary)
        self.assertIn("Regenerate the bundle because manifest hash verification failed for risk_summary.json.", summary)

    def test_verify_pr_review_bundle_catches_manifest_hash_mismatch(self) -> None:
        metadata = {
            "number": 25,
            "title": "Clarify generated PR review verification",
            "url": "https://github.com/camirian/agent_evidence-recorder/pull/25",
            "state": "OPEN",
            "author": {"login": "camirian"},
            "baseRefName": "main",
            "headRefName": "feature/verify-pr-review",
            "changedFiles": 1,
            "additions": 8,
            "deletions": 1,
            "reviewDecision": "",
            "createdAt": "2026-05-31T18:00:00Z",
            "updatedAt": "2026-05-31T18:05:00Z",
            "body": "Adds a verifier for generated PR review bundles.",
            "files": [
                {
                    "filename": "agent_evidence_recorder/pr_review.py",
                    "additions": 8,
                    "deletions": 1,
                    "changes": 9,
                    "status": "modified",
                    "patch": "@@ -1 +1 @@\n-old\n+new",
                }
            ],
            "commits": [{"oid": "abc"}],
            "statusCheckRollup": [{"name": "unit", "conclusion": "SUCCESS"}],
        }
        output_dir = self.temp_root / "pr-review-bad-hash"
        write_pr_review_bundle(
            metadata,
            output_dir,
            repo="camirian/agent_evidence-recorder",
            generated_at="2026-05-31T00:00:00+00:00",
        )
        (output_dir / "risk_summary.json").write_text("{\"tampered\": true}\n", encoding="utf-8")
        report = verify_pr_review_bundle(output_dir)
        self.assertFalse(report["passed"])
        failed = {check["name"] for check in report["checks"] if not check["passed"]}
        self.assertIn("manifest:risk_summary.json:sha256", failed)


if __name__ == "__main__":
    unittest.main()
