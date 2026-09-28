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
python3 -m agent_evidence_recorder.verify_sample
python3 -m unittest discover -s tests -p "test_*.py"
```

The fixtures are synthetic. They cover accepted, rejected, escalated, blocked,
and incomplete evidence states. A passing test suite does not authorize a
merge, deployment, or real-world action.

The sample generator removes and recreates the entire `samples/` directory.
Run `python3 -m agent_evidence_recorder.sample` only in a clean, disposable
checkout with no user files under `samples/`. For a non-destructive
reproducibility check, use `python3 -m agent_evidence_recorder
verify-sample-determinism`; it generates fixtures in a temporary directory
and compares them with the tracked samples.

## Status and boundaries

Package metadata identifies version `0.1.0`. This engineering artifact
contains deterministic synthetic examples, a verifier for recorded Git
changes, local Claude Code session tools, and a GitHub PR review bundle from
data visible to the caller's `gh` CLI identity. PR data may come from a private
repository and can contain private text; keep those bundles in the same
privacy boundary unless reviewed and sanitized. These paths use different
inputs and have different privacy boundaries; see the
[PR review contract](docs/PR_REVIEW_CONTRACT_V0_2.md) for the GitHub data boundary.

The tests and synthetic negative controls are implementation evidence. This
repository does not report measured external-user outcomes or production
reliability evidence.

It is not a hosted service or a general-purpose autonomous coding system. It
does not approve pull requests, certify safety or compliance, prove production
readiness, or guarantee rollback. There is no live model/provider adapter.
The live-adapter gate remains on hold in
[Live Adapter Decision Gate](docs/LIVE_ADAPTER_BOUNDARY.md).

## Capabilities

- deterministic synthetic evidence generation and verification;
- agent-run receipts with explicit provenance and outcome states;
- bounded GitHub pull-request review bundles from data visible to the caller's `gh` CLI identity;
- local session ingestion with redaction boundaries;
- fleet triage for suspicious runs;
- replayable verification inputs and reviewer-facing packets.

## Scope

This repository is a technical and research artifact. It is not a hosted
service, telemetry product, compliance certification, merge-approval system, or
replacement for human review.

## License

Apache-2.0. See [LICENSE](LICENSE).

## Development and verification

The test suite uses the Python standard library. From a checkout, run the same
test command used by CI:

```bash
python3 -m unittest discover -s tests -p "test_*.py"
python3 -m agent_evidence_recorder verify-sample-determinism
python3 -m py_compile $(find . -name '*.py' -not -path './.*')
```

CI runs the unit tests and syntax compilation on Python 3.10, 3.11, and 3.12.
The deterministic sample comparison is an additional local check. Run it
before syntax compilation: `py_compile` creates bytecode caches under the
sample fixture tree, and the verifier currently reports those files as
unexpected sample artifacts. Each command's input boundary is documented with
its contract.

## Documentation map

- [PR review contract](docs/PR_REVIEW_CONTRACT_V0_2.md)
- [Live adapter decision gate](docs/LIVE_ADAPTER_BOUNDARY.md)
- [Live adapter readiness backlog](docs/LIVE_ADAPTER_READINESS_BACKLOG.md)
