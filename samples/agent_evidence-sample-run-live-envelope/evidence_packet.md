# Evidence Packet: agent_evidence-sample-run-live-envelope

## Summary
- Final status: `blocked`
- Recommended reviewer decision: `reject`
- Adapter: `synthetic_sample`
- Live model used: `false`
- External APIs used: `false`
- Network used: `false`
- Timeout limit: `30` seconds
- Cost budget: `0` synthetic provider tokens
- Failure class: `input_rejected`

## Intent
Record a bounded synthetic coding-agent-style run with enough evidence for replay, review, and rollback inspection.

## What Changed
- Target fixture: `samples/sample-target-repo/calculator.py`
- Modeled change record: `git.diff`
- Verification command summary: `commands.log`

## Verification
- Result: The modeled edit passes verification but is blocked by policy.
- Detailed checks: `sample_verification.json`
- Public-surface boundary: `sample_policy.json`
- Policy gate: `policy_gate_report.json`
- Human escalation: `human_escalation_record.json`

## Evidence Index
- `run_record.json` captures the intent, inputs, outputs, modeled steps, replay command, boundary, and final status.
- `run_record.json` also captures timeout, cost-budget, and failure-capture fields for the synthetic run.
- `artifact_manifest.json` captures artifact roles, classifications, hashes, byte sizes, replay inclusion, and rollback inclusion.
- `trace.jsonl` captures ordered run events.
- `git.diff` captures the modeled code change.
- `rollback.sh` documents the bounded rollback mechanism for modeled git-tracked changes.

## Limits
- This sample does not wrap live agents.
- Rollback is limited to modeled git-tracked file changes.
- External effects are not reversed.
- This packet is operational evidence, not a legal or compliance certification.
