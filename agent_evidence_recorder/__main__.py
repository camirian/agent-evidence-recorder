"""Command entrypoint for the public synthetic sample."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_evidence_recorder.agent_run_receipt import read_json, score_receipt, verify_receipts
from agent_evidence_recorder.determinism import verify_sample_determinism
from agent_evidence_recorder.pr_review import (
    PrReviewError,
    fetch_pr_metadata,
    inspect_pr_review_bundle,
    verify_pr_review_bundle,
    verify_recorded_review_outcome,
    write_pr_review_bundle,
)
from agent_evidence_recorder.fleet import format_fleet, scan_runs
from agent_evidence_recorder.ingest_session import ingest_session
from agent_evidence_recorder.release_boundary import check_release_boundary
from agent_evidence_recorder.sample import generate_public_samples
from agent_evidence_recorder.verify_run import verify_run
from agent_evidence_recorder.verify_sample import verify_samples


def main() -> int:
    parser = argparse.ArgumentParser(prog="agent_evidence-recorder")
    subcommands = parser.add_subparsers(dest="command", required=True)
    subcommands.add_parser("run-sample", help="generate public-safe synthetic sample artifacts")
    subcommands.add_parser("verify-sample", help="verify generated synthetic sample artifacts")
    subcommands.add_parser(
        "verify-sample-determinism",
        help="regenerate samples in a temp directory and compare them with tracked samples",
    )
    pr_review = subcommands.add_parser("pr-review", help="generate a public-safe GitHub PR review bundle")
    pr_review.add_argument("--repo", required=True, help="GitHub repo in OWNER/NAME form")
    pr_review.add_argument("--pr", required=True, type=int, help="pull request number")
    pr_review.add_argument(
        "--output-dir",
        default="agent_evidence-pr-review",
        help="directory for generated review artifacts",
    )
    verify_pr_review = subcommands.add_parser("verify-pr-review", help="verify a generated GitHub PR review bundle")
    verify_pr_review.add_argument(
        "--bundle-dir",
        default="agent_evidence-pr-review",
        help="directory containing generated PR review artifacts",
    )
    inspect_pr_review = subcommands.add_parser("inspect-pr-review", help="print a reviewer-oriented PR bundle summary")
    inspect_pr_review.add_argument(
        "--bundle-dir",
        default="agent_evidence-pr-review",
        help="directory containing generated PR review artifacts",
    )
    verify_review_outcome = subcommands.add_parser(
        "verify-review-outcome",
        help="verify a filled PR review outcome worksheet",
    )
    verify_review_outcome.add_argument(
        "--bundle-dir",
        default="agent_evidence-pr-review",
        help="directory containing generated PR review artifacts",
    )
    verify_release_boundary = subcommands.add_parser(
        "verify-release-boundary",
        help="verify an extracted source release artifact or staged candidate tree",
    )
    verify_release_boundary.add_argument(
        "--path",
        required=True,
        help="extracted release artifact or staged candidate tree to scan",
    )
    score_agent_run = subcommands.add_parser("score-agent-run", help="score one synthetic agent run receipt")
    score_agent_run.add_argument("receipt", type=Path, help="agent_run_receipt JSON path")
    verify_agent_run_receipts = subcommands.add_parser(
        "verify-agent-run-receipts",
        help="verify tracked synthetic agent run receipt examples",
    )
    verify_agent_run_receipts.add_argument(
        "--receipt-dir",
        default="samples/agent-run-receipts",
        type=Path,
        help="directory containing agent-run-receipt.*.json examples",
    )
    verify_run_cmd = subcommands.add_parser(
        "verify-run",
        help="independently verify a real agent run on things it can't narrate around",
    )
    verify_run_cmd.add_argument("--repo", default=".", help="path to the git repo the agent worked in")
    verify_run_cmd.add_argument("--base", required=True, help="base ref (before the agent's work)")
    verify_run_cmd.add_argument("--head", default="HEAD", help="head ref (after the agent's work)")
    verify_run_cmd.add_argument(
        "--test-cmd",
        default=None,
        help="shell command Agent Evidence runs in a CLEAN checkout (e.g. 'pytest -q')",
    )
    verify_run_cmd.add_argument(
        "--max-files",
        type=int,
        default=20,
        help="blast-radius threshold: more changed files than this -> needs_review",
    )
    ingest_session_cmd = subcommands.add_parser(
        "ingest-session",
        help="turn a real Claude Code .jsonl session into a structured run record",
    )
    ingest_session_cmd.add_argument("--session", required=True, type=Path, help="path to a Claude Code session .jsonl")
    ingest_session_cmd.add_argument(
        "--redact",
        action="store_true",
        help="omit free text (intent/commands/paths) for privacy-safe sharing",
    )
    fleet_cmd = subcommands.add_parser(
        "fleet",
        help="triage recent agent runs: which of last night's runs need your eyes",
    )
    fleet_cmd.add_argument(
        "--projects-dir",
        default=str(Path.home() / ".claude" / "projects"),
        help="Claude Code projects dir to scan for session transcripts",
    )
    fleet_cmd.add_argument(
        "--since-hours", type=float, default=24.0, help="only runs touched within this many hours"
    )
    fleet_cmd.add_argument("--redact", action="store_true", help="mask repo/branch/intent for sharing")
    fleet_cmd.add_argument("--json", action="store_true", help="emit raw JSON instead of the board")
    args = parser.parse_args()

    if args.command == "run-sample":
        summary = generate_public_samples()
        print(f"generated {len(summary['runs'])} sample runs")
        return 0
    if args.command == "verify-sample":
        report = verify_samples()
        print(f"verified {len(report['checks'])} checks")
        return 0
    if args.command == "verify-sample-determinism":
        report = verify_sample_determinism()
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    if args.command == "pr-review":
        try:
            metadata = fetch_pr_metadata(args.repo, args.pr)
            summary = write_pr_review_bundle(metadata, Path(args.output_dir), repo=args.repo)
        except PrReviewError as exc:
            print(f"error: {exc}")
            return 1
        print(f"generated {len(summary['artifacts'])} PR review artifacts in {summary['output_dir']}")
        return 0
    if args.command == "verify-pr-review":
        report = verify_pr_review_bundle(Path(args.bundle_dir))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    if args.command == "inspect-pr-review":
        print(inspect_pr_review_bundle(Path(args.bundle_dir)), end="")
        return 0
    if args.command == "verify-review-outcome":
        report = verify_recorded_review_outcome(Path(args.bundle_dir))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    if args.command == "verify-release-boundary":
        report = check_release_boundary(Path(args.path))
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    if args.command == "score-agent-run":
        print(json.dumps(score_receipt(read_json(args.receipt)), indent=2, sort_keys=True))
        return 0
    if args.command == "verify-agent-run-receipts":
        report = verify_receipts(args.receipt_dir)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    if args.command == "verify-run":
        report = verify_run(
            args.repo,
            args.base,
            args.head,
            test_command=args.test_cmd,
            blast_radius_threshold=args.max_files,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0 if report["passed"] else 1
    if args.command == "ingest-session":
        record = ingest_session(args.session, redact=args.redact)
        print(json.dumps(record, indent=2, sort_keys=True))
        return 0
    if args.command == "fleet":
        since = None if args.since_hours <= 0 else args.since_hours
        items = scan_runs(args.projects_dir, since_hours=since)
        if args.json:
            payload = [
                {
                    "suspicion": i["suspicion"],
                    "reasons": i["reasons"],
                    "record": i["record"],
                    "verify_command": i.get("verify_command"),
                }
                for i in items
            ]
            print(json.dumps(payload, indent=2, sort_keys=True))
        else:
            print(format_fleet(items, redact=args.redact))
        return 0
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
