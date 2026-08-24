# Live Adapter Decision Gate

This document is the go/no-go gate for any future live-adapter work in
Agent Evidence Recorder. It defines the minimum conditions that must be true before
the repository can move from deterministic synthetic/public-metadata fixtures
to live agent or provider execution.

The current repository remains synthetic-only plus public GitHub PR metadata
bundles. No live adapter code exists in this repository. This file is a
decision gate, not an implementation announcement.

## Gate Decision

Default decision: **hold**.

Proceed is allowed only when every proceed criterion below is satisfied and the
user explicitly approves live-adapter implementation.

Hold when:

- the work would improve the public evidence contract, verifier, fixtures, or
  reviewer workflow without adding live execution
- any data, redaction, timeout, cost, rollback, or review requirement is
  underspecified
- the live run cannot be inspected manually from the generated bundle

Stop when:

- the adapter would read private repositories, secrets, credentials, `.env`
  contents, customer data, employer data, or unrelated local files
- the adapter would execute browser, cloud, hardware, deployment, publish,
  payment, or real-world actuation steps
- the adapter would claim approval, production readiness, compliance readiness,
  legal review, safety certification, or complete rollback
- the adapter would hide provider prompts, responses, errors, costs, timeouts,
  or verification results from the reviewer packet

## Proceed Criteria

All criteria are required before implementation:

- **Explicit approval:** the user approves live-adapter code after reviewing
  this gate.
- **Data boundary:** the adapter input contract names exactly what public or
  synthetic data can enter the run.
- **Private-data block:** the adapter rejects secrets, credentials, `.env`
  contents, private repository paths, customer data, employer data, and
  unrelated local files before export.
- **Redaction:** any future redaction rule is deterministic, test-covered, and
  visible in the evidence packet.
- **Timeout limit:** the adapter has a fixed wall-clock timeout recorded in the
  run record.
- **Cost limit:** the adapter has a fixed maximum cost or token budget recorded
  in the run record.
- **Effect limit:** allowed effects are file-scoped, predeclared, and
  reviewable before execution.
- **Rollback limit:** rollback claims are limited to recorded file diffs or
  explicitly marked unavailable.
- **Failure capture:** provider errors, timeouts, partial outputs, refused
  actions, and verifier failures are preserved as review evidence.
- **Reviewer outcome:** no live run can be treated as accepted until a reviewer
  records `review_outcome.json` or an equivalent worksheet.
- **Release boundary:** release-boundary scanning still passes on the exact
  candidate tree after the adapter code is added.
- **Public docs:** README, QUICKSTART, roadmap, and claim-audit docs still say
  what remains out of scope.

If one criterion is missing, the next slice must stay synthetic or
public-metadata-only.

For the implementation prerequisites that keep the project inside this hold
decision, see
[LIVE_ADAPTER_READINESS_BACKLOG.md](LIVE_ADAPTER_READINESS_BACKLOG.md).
The concrete preflight contracts are
[LIVE_ADAPTER_INPUT_CONTRACT.md](LIVE_ADAPTER_INPUT_CONTRACT.md) and
[LIVE_ADAPTER_REDACTION_CONTRACT.md](LIVE_ADAPTER_REDACTION_CONTRACT.md).

## Intended Slice

If the gate is later approved, the smallest acceptable live-adapter slice is a
single adapter boundary that can:

- accept one live agent request for one bounded coding task,
- capture the request/response envelope and the resulting run record,
- preserve the same public-safe evidence bundle shape used by the synthetic
  sample,
- keep rollback and review boundaries explicit and narrow.

This slice is intentionally smaller than a general agent platform. It is a
thin live boundary around one run, not a multi-tool automation system.

## Boundary

The live adapter boundary starts where a caller hands the adapter a bounded
task and ends where the adapter returns a structured run artifact bundle.

Inside the boundary:

- one task request
- one live model or provider invocation
- one bounded set of recorded inputs
- one bounded set of recorded outputs
- one evidence bundle with review and rollback metadata

Outside the boundary:

- the provider platform itself
- provider-side orchestration
- any hosted service or account management layer
- any long-running agent loop
- any multi-step workflow manager
- any release, publish, or deployment path

## Inputs

The minimum live-adapter inputs should be limited to:

- a single task description
- a bounded working-root description
- an explicit allowed-effect classification
- a declared rollback scope
- a declared evidence export target
- a fixed timeout limit
- a fixed cost or token budget
- a reviewer outcome requirement

The inputs must be enough to explain what the run was allowed to touch without
requiring hidden environment state or private local context.

## Outputs

The live adapter should produce the same kind of reviewer-facing outputs as the
synthetic sample, with live provenance where applicable:

- run record
- artifact manifest
- evidence packet
- review packet
- command or action log
- verification summary
- rollback notes limited to the recorded boundary
- timeout and cost-budget result
- provider error or refusal record, when applicable
- reviewer outcome worksheet

The outputs must make it obvious whether the run was live or synthetic, what
was actually attempted, and what was not verified.

## Explicit Non-Goals

This slice is not meant to:

- prove general live-agent safety
- provide customer readiness
- provide production rollout readiness
- support arbitrary tool use
- support browser automation
- support cloud operations
- support multi-agent coordination
- support non-file side effects as rollbackable
- support public release or package publication
- claim compliance, certification, or legal review

## Risk Controls

The smallest acceptable live-adapter slice should keep these controls explicit:

- public-safe artifact format only
- relative paths only
- no private data in exported evidence
- deterministic redaction when redaction is needed
- no hidden provider account dependence in the record
- no implied rollback beyond the recorded file boundary
- explicit separation of live execution from synthetic sample artifacts
- explicit classification of external effects
- explicit time, cost, and failure limits
- explicit reviewer outcome before trust is granted

If any of those controls cannot be stated clearly in the evidence, the live
adapter slice is too large.

## Minimum Evidence Before Implementing

Before this adapter boundary is added, the project should have evidence for all
of the following:

1. The synthetic sample contract still reads as an honest baseline for the
   artifact shape.
2. The adapter boundary can be described without changing the meaning of the
   existing synthetic-only docs.
3. The live run record can truthfully distinguish live execution from the
   current `synthetic_sample` adapter.
4. The evidence bundle can show the live request, recorded response, and
   verification result without exposing private data.
5. The rollback boundary is still limited to what the bundle can actually
   reverse.
6. The public-surface docs can explain what remains out of scope.
7. The release-boundary checker catches claims that would overstate the live
   adapter.
8. A reviewer can reject, request changes, or request follow-up from the
   generated bundle without reading hidden context.

If any one of these is missing, the next step should stay synthetic.

## Required Verification For A Future Adapter PR

Any future live-adapter implementation PR must include:

- unit tests for input rejection and redaction
- a deterministic fixture for timeout, cost-limit, provider-error, and verifier
  failure cases
- a generated live-adapter sample that uses only synthetic or public-safe data
- `python3 -m unittest`
- `python3 -m agent_evidence_recorder.verify_sample`
- `python3 -m agent_evidence_recorder verify-sample-determinism`
- release-boundary scan from a clean archive
- a public-surface scan over changed docs and generated fixtures

Passing these checks would show only that the adapter is inspectable. It would
not prove live-agent safety, production readiness, compliance readiness, or
complete rollback.

## Assumptions

This boundary assumes:

- the project continues to treat the current sample as the canonical
  public-safe reference
- the first live adapter will be narrow enough to inspect manually
- live-provider interaction will be recorded, not inferred
- live execution will not widen the rollback promise beyond file-scoped changes

## Relationship To Existing Docs

This file intentionally overlaps with the current boundary language in:

- `docs/OPERATING_BOUNDARIES.md`
- `docs/AGENT_RUN_RECORD_SPEC.md`
- `docs/ARTIFACT_GUIDE.md`

Those docs define the present synthetic-only and public-metadata contract. This
file only defines the decision gate for a future live-adapter slice that would
sit beyond that contract.
