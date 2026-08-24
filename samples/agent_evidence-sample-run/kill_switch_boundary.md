# Kill Switch Boundary: agent_evidence-sample-run

## Trigger
- Final policy status: `passed`
- Final recorder status: `accepted`

## Stopped Or Held Action
- Trust is not granted until the policy gate passes or a reviewer records a decision.

## Reviewer Action
- Inspect `policy_gate_report.json`, `git.diff`, `human_escalation_record.json`, and `review_packet.md`.
- Accept only if the policy status is `passed` and verification supports the result.
- Escalate or reject if policy-sensitive or forbidden behavior appears.

## Rollback Limits
- Rollback is limited to modeled git-tracked fixture changes.
- External effects are not reversible by this sample.
