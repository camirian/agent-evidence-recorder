# Live Adapter Input Contract

This contract defines the input boundary required before any future live
adapter code. It is not an adapter implementation and does not approve live
provider calls. The current repository remains synthetic-only plus public
GitHub PR metadata bundles.

## Purpose

A future live adapter may only accept a bounded task request that can be
reviewed from the exported evidence bundle. The request must not depend on
hidden local context, private repositories, provider account state, or
unrecorded operator intent.

## Allowed Request Fields

Any future request envelope must be explicit and limited to these fields:

| Field | Required | Contract |
| --- | --- | --- |
| `task_id` | yes | Stable identifier for the requested run. |
| `task_description` | yes | Plain-language task. Must be specific enough for review. |
| `working_root_label` | yes | Human-readable label, not an absolute local path. |
| `allowed_input_refs` | yes | Relative paths, public URLs, or synthetic fixture IDs allowed as evidence inputs. |
| `allowed_effects` | yes | File-scoped effects only: `read_file`, `create_file`, `modify_file`, or `no_op`. |
| `disallowed_effects` | yes | Non-file effects and any action outside the declared boundary. |
| `rollback_scope` | yes | Recorded file diff, unavailable, or another explicit narrow scope. |
| `evidence_export_target` | yes | Relative output directory for the evidence bundle. |
| `timeout_seconds` | yes | Fixed positive integer recorded before execution. |
| `cost_budget` | yes | Fixed budget object recorded before execution. |
| `reviewer_outcome_required` | yes | Must be `true` for any future live run. |
| `redaction_profile` | yes | Named deterministic redaction profile. |
| `verification_commands` | optional | Relative, reviewable commands that do not require secrets or private state. |

No field may be inferred from `.env`, provider credentials, shell history,
global git config, untracked local files, or a private workspace path.

## Allowed Input References

Allowed references are:

- relative paths under the declared working root
- public URLs that are captured as metadata, not as secret-bearing sessions
- synthetic fixture IDs already tracked in this repository
- public GitHub PR metadata already allowed by the PR-review contract

Relative paths must stay relative in exported evidence. Public URLs must not
carry credentials, session identifiers, or private organization identifiers.

## Disallowed Inputs

The request must be rejected before export if it contains or points at:

- absolute local paths
- `.env` contents or environment variable dumps
- secrets, credentials, tokens, keys, cookies, or session material
- private repository paths or private issue/PR URLs
- customer data, employer data, or unrelated local files
- binary uploads, archives, build outputs, caches, or virtual environments
- browser, cloud, hardware, deployment, payment, publish, or real-world action
  requests
- vague tasks that do not identify the intended change or review question

Rejection is the correct behavior when the request cannot be made public-safe
through deterministic redaction.

## Rejection Behavior

A rejected request must produce a local rejection record, not a live provider
call. The record must include:

- `final_status`: `blocked`
- `failure_class`: `input_rejected`
- rejected field names
- public-safe rejection reasons
- a statement that no provider request was sent
- the redaction profile that was considered

The rejection record must not echo raw sensitive values. It may include
redacted labels such as `[REDACTED_SECRET]` or `[REDACTED_LOCAL_PATH]`.

## Evidence Requirements

If a future request passes this contract, the evidence bundle must record:

- the normalized request envelope
- the exact allowed input references
- timeout and cost budget values
- allowed and disallowed effects
- rollback scope
- redaction profile and redaction counts
- reviewer outcome requirement
- residual risk notes

The reviewer must be able to decide whether the request stayed inside the
declared boundary without reading hidden machine state.

## Effect Boundary Contract

Every synthetic or future live-eligible evidence bundle must carry an explicit
effect boundary in `run_record.json` and mirror it in reviewer-facing evidence.
The current synthetic contract uses:

- `boundary_type`: `file_scoped_synthetic`
- `allowed_effects`: `read_file`, `create_file`, `modify_file`, `no_op`
- `non_file_effects_allowed`: `false`
- `provider_calls_allowed`: `false`
- `external_effects_rollbackable`: `false`
- `rollback_scope`: `recorded_git_diff_only`

Any requested non-file effect, including network calls, deployment,
publication, browser automation, cloud operations, hardware access, payment,
or external API calls, must be recorded as blocked before execution. A review
packet must not claim that non-file effects are allowed, executed, or
rollbackable.

## Current Status

This contract is a prerequisite only. It adds no live adapter, no provider
request, no credential access, and no package or release workflow.
