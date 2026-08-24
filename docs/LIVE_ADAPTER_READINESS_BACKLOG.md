# Live Adapter Readiness Backlog

This backlog converts the live-adapter decision gate into implementable
prerequisite tasks. It does not approve live-adapter code.

Current decision: **hold**. Agent Evidence Recorder remains synthetic-only plus
public GitHub PR metadata bundles. No live adapter code is approved or present
in this repository.
All slices in this backlog preserve the no-live-provider-call boundary and are
done without adding live provider calls.

Each task below is required before live adapter code.

## P0 Required Before Live Adapter Code

| Task | Output | Acceptance |
| --- | --- | --- |
| Input contract | shipped `docs/LIVE_ADAPTER_INPUT_CONTRACT.md` | Names allowed task fields, allowed public/synthetic inputs, disallowed private inputs, and rejection behavior. |
| Redaction contract | shipped `docs/LIVE_ADAPTER_REDACTION_CONTRACT.md` | Defines deterministic redaction rules, what is never exported, and how redaction is recorded in evidence. |
| Timeout and cost budget fields | shipped schema-only fixture/docs update | Adds timeout and cost/token budget fields to synthetic run records without calling providers. |
| Failure capture fixture | shipped synthetic fixture/docs update | Covers timeout, budget exceeded, provider refusal, partial output, and verifier failure as recorded evidence. |
| Reviewer outcome requirement | verifier/docs update | Ensures any future live run remains untrusted until a reviewer records an outcome. |
| ✅ Effect boundary contract | shipped docs/tests | Limits effects to file-scoped, predeclared actions and marks non-file effects as out of scope. |
| Public-surface gate | test/scanner update | Confirms live-adapter docs still say no live adapter code is approved until explicit approval. |
| Release-boundary gate | release-boundary test | Confirms candidate trees fail on overclaims about live safety, automatic approval, or complete rollback. |

## P1 Required Before Any Live Fixture

| Task | Output | Acceptance |
| --- | --- | --- |
| ✅ Synthetic live-envelope fixture | shipped `samples/agent_evidence-sample-run-live-envelope` | Mimics provider request/response, timeout, cost, and refusal fields without network access. |
| ✅ Live provenance schema | shipped `docs/ROADMAP.md` and `tests/test_sample.py` | Distinguishes `synthetic_sample`, `github_pr_review`, and `synthetic_live_envelope` provenance values. |
| ✅ Redaction negative controls | tests | Secret-shaped, private-path, customer-data, and unrelated-local-file inputs are rejected or redacted deterministically. |
| ✅ Manual review packet update | docs/tests | Reviewer packet surfaces live/synthetic distinction, budget result, failure result, and reviewer outcome requirement. |

## P2 Only After Explicit Approval

These tasks remain blocked until the user explicitly approves implementation
after reviewing the gate and P0/P1 evidence.

| Task | Output | Acceptance |
| --- | --- | --- |
| Provider-neutral adapter interface | code/docs/tests | Defines an interface without binding to a provider account or hidden environment state. |
| Single-run live adapter prototype | code/tests/fixture | Runs one bounded task with fixed timeout/cost and public-safe evidence export. |
| Live adapter public claim audit | docs/checks | Re-audits README, QUICKSTART, roadmap, samples, and release-boundary output before merge. |

## Stop Conditions

Stop instead of implementing if a proposed task would:

- read private repositories, secrets, credentials, `.env` contents, customer
  data, employer data, or unrelated local files
- execute browser, cloud, hardware, deployment, publish, payment, or real-world
  actuation steps
- claim approval, production readiness, compliance readiness, legal review,
  safety certification, or complete rollback
- hide provider prompts, responses, errors, costs, timeouts, or verification
  results from the reviewer packet

## Next Recommended Slice

With effect-boundary contract hardening landed, the next non-live engineering slice is:

```text
Implement the public-surface gate for live-adapter overclaim detection.
```

That slice improves the evidence contract while staying inside the current hold
decision.
