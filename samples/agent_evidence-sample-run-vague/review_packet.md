# Review Packet: agent_evidence-sample-run-vague

## Decision
- Final status: `needs_human_review`
- Reviewer action: Escalate the run; verification passed but policy requires a reviewer decision.
- Adapter: `synthetic_sample`
- Provenance: `synthetic_sample`
- Workflow: `coding_agent_run`
- Scope: modeled local coding-agent-style run
- Timeout and cost budget: recorded in `run_record.json`
- Failure capture: `review_judgment_blocked`
- Provider calls executed: `false`
- Reviewer outcome required: `true`
- Effect boundary: `file_scoped_synthetic`
- Non-file effects allowed: `false`
- Rollback scope: `recorded_git_diff_only`

## Required Reviewer Checks
- Confirm `run_record.json` states the run intent, replay command, input artifacts, output artifacts, environment boundary, and final status.
- Confirm `artifact_manifest.json` lists every relevant artifact with role, classification, SHA-256 hash, byte size, replay inclusion, and rollback inclusion.
- Confirm `git.diff` is narrow and only changes the modeled target file.
- Confirm `sample_verification.json` supports the final status.
- Confirm `policy_gate_report.json` supports the final status.
- Confirm `human_escalation_record.json` names the reviewer action when needed.
- Confirm verification passing is not enough when policy escalates or blocks trust.
- Confirm `sample_policy.json` keeps the run synthetic, relative-path-only, and live-adapter-free.
- Confirm `run_record.json` records timeout, cost budget, and failure-capture evidence without live provider calls.
- Confirm `run_record.json` limits effects to file-scoped read/create/modify/no-op actions.
- Confirm `rollback.sh` is limited to modeled git-tracked file changes and does not imply full system rollback.

## Escalate If
- any artifact path is absolute or machine-local
- any artifact contains sensitive values, access material, or non-public organizational data
- verification status conflicts with final status
- rollback claims exceed the recorded `git.diff` boundary
- non-file effects are claimed as allowed, executed, or rollbackable
- the adapter is anything other than `synthetic_sample` in this candidate
