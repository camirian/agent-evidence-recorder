# PR Review Contract v0.2

This contract describes the public GitHub PR review bundle produced by
`agent_evidence-recorder pr-review` and by the deterministic offline fixtures under
`samples/`.

It is a review contract, not an approval contract. Passing verification means
the bundle is internally consistent and inspectable. It does not approve the
pull request, prove production readiness, execute CI, inspect private
repositories, or replace a reviewer decision.

## Boundary

The bundle may use only public GitHub PR metadata:

- PR title, body, state, author, base branch, head branch, timestamps, URL, and
  review decision
- changed file paths and line counts reported by GitHub
- bounded file patch excerpts reported by GitHub
- status-check rollup names, conclusions, states, statuses, and URLs
- commit count

The bundle must not read local repository files, fetch secrets, inspect private
artifacts, call live agent/provider tools, run tests, approve a PR, or claim
complete rollback.

## Required Artifacts

Every generated PR review bundle must contain these files:

| Artifact | Role |
| --- | --- |
| `artifact_manifest.json` | Hashes, byte counts, and public-metadata classification for generated artifacts. |
| `changed_files.json` | Normalized GitHub changed-file metadata and file risk flags. |
| `commands.log` | Source command provenance for the metadata capture. |
| `file_diffs.json` | Bounded GitHub patch excerpts and diff coverage limits. |
| `pr_metadata.json` | Normalized public PR metadata. |
| `review_outcome.json` | Mutable reviewer worksheet for the final human decision. |
| `review_request.md` | Short shareable critique request for a cold reviewer. |
| `reviewer_packet.md` | Reviewer-facing decision packet and checklist. |
| `risk_summary.json` | Machine-readable risk flags, risk reasons, and trap classes. |
| `run_record.json` | Bundle intent, boundary, output list, and final status. |
| `status_checks.json` | Normalized public status-check evidence. |

`review_outcome.json` is intentionally mutable after review. After a reviewer
fills it, `verify-review-outcome` allows only that artifact's manifest hash and
byte count to drift. Every other artifact must still pass bundle verification.

## Status Contract

`run_record.json` may record only these final statuses:

- `accepted_for_review`: the public metadata has no detected PR review risk
  reasons. This is still only a starting point for review.
- `needs_human_review`: at least one risk reason holds trust for a human
  decision.

`review_outcome.json` starts with:

- `status`: `unrecorded`
- `recommended_starting_decision`: `accept` or `needs_followup`
- `reviewer_decision`: empty until a reviewer records a decision

Allowed reviewer decisions are:

- `accept`
- `reject`
- `request_changes`
- `needs_followup`

Non-accept decisions require reviewer notes. Accepting a bundle that started
from review-needed risk also requires notes.

## Risk Contract

File risk flags are inspectable labels, not decisions:

- `ci_or_automation`
- `security_or_policy`
- `source_code`
- `documentation`

Risk reasons hold trust for review:

- `high_risk_file_class_changed`
- `status_checks_missing`
- `status_checks_not_successful`
- `review_decision_requires_attention`
- `intent_too_vague_for_review`
- `changed_file_metadata_incomplete`
- `diff_context_incomplete`
- `large_change_set`

PR-review trap classes make the review failure mode explicit:

- `missing_checks_requires_review`
- `non_successful_checks_require_review`
- `review_required_blocks_trust`
- `vague_pr_intent_blocks_review_judgment`
- `incomplete_file_metadata_requires_review`
- `incomplete_diff_context_requires_review`
- `large_diff_requires_review`
- `sensitive_pr_surface_requires_review`

Successful checks are evidence to inspect, not approval. Missing, failed,
pending, skipped, stale, neutral, unknown, or otherwise ambiguous check states
hold trust for review.

## Diff Contract

`file_diffs.json` records bounded GitHub-reported patch excerpts. The current
limits are:

- at most 12 files with patch excerpts
- at most 80 patch lines per file

Omitted files, missing patches, and truncated patches must be reported in
`file_diffs.json` and surfaced as `diff_context_incomplete` when they prevent a
clean metadata-only review.

## Verification Contract

`verify-pr-review` checks:

- required artifact presence
- JSON schema versions
- manifest hashes and byte counts
- run-record output coverage
- public metadata boundary text
- relative artifact paths
- bounded diff limits
- status-check summary consistency
- risk-summary fields and allowed risk level
- review-outcome worksheet fields
- required Markdown sections

`verify-review-outcome` additionally checks:

- the bundle still verifies except for mutable `review_outcome.json` manifest
  drift
- the reviewer decision is present and allowed
- notes are present when required
- evidence references are relative and exist inside the bundle

Verification failure means the bundle should be repaired or regenerated before
review. Verification success means the bundle is fit to inspect, not fit to
auto-accept.

## Offline Fixture Coverage

The tracked fixtures exercise the contract without GitHub authentication or
network access:

| Fixture | Expected status | Starting decision | Contract point |
| --- | --- | --- | --- |
| `samples/agent_evidence-pr-review-low-risk-docs/` | `accepted_for_review` | `accept` | Low-risk docs-only metadata can start from accept. |
| `samples/agent_evidence-pr-review-adversarial/` | `needs_human_review` | `needs_followup` | Successful checks do not override vague intent and high-risk files. |
| `samples/agent_evidence-pr-review-self-demo/` | `needs_human_review` | `needs_followup` | A filled worksheet can record follow-up when status checks are missing. |
| `samples/agent_evidence-pr-review-sample/` | `needs_human_review` | `needs_followup` | Generated baseline remains an unrecorded worksheet. |

Use the fixture matrix for the shortest reviewer path:

```bash
less docs/PR_REVIEW_FIXTURE_MATRIX.md
python3 -m agent_evidence_recorder inspect-pr-review --bundle-dir samples/agent_evidence-pr-review-low-risk-docs
python3 -m agent_evidence_recorder inspect-pr-review --bundle-dir samples/agent_evidence-pr-review-adversarial
python3 -m agent_evidence_recorder verify-review-outcome --bundle-dir samples/agent_evidence-pr-review-self-demo
```
