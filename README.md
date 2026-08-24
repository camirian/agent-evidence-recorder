# Agent Evidence Recorder

Agent Evidence Recorder is a standard-library Python toolkit for turning an
autonomous software run into a reviewable evidence bundle.

It records intent, actions, diffs, command output, verification results,
reviewer checks, provenance, and bounded rollback information. The central
boundary is simple: the process that performs work does not certify its own
success.

## Quick start

Python 3.10+ is required. Core operation has no third-party runtime
dependencies.

```bash
python3 -m agent_evidence_recorder.sample
python3 -m agent_evidence_recorder.verify_sample
python3 -m pytest -q
```

The fixtures are synthetic. They cover accepted, rejected, escalated, blocked,
and incomplete evidence states. A passing test suite does not authorize a
merge, deployment, or real-world action.

## Capabilities

- deterministic synthetic evidence generation and verification;
- agent-run receipts with explicit provenance and outcome states;
- bounded GitHub pull-request review bundles from public metadata;
- local session ingestion with redaction boundaries;
- fleet triage for suspicious runs;
- replayable verification inputs and reviewer-facing packets.

## Scope

This repository is a technical and research artifact. It is not a hosted
service, telemetry product, compliance certification, merge-approval system, or
replacement for human review.

## License

Apache-2.0. See [LICENSE](LICENSE).
