# Live Adapter Redaction Contract

This contract defines deterministic redaction requirements for any future live
adapter boundary. It does not add live adapter code and does not approve live
provider calls.

## Purpose

Redaction is evidence-preservation work, not a way to make broad private inputs
acceptable. Inputs that are outside the live adapter input contract must be
rejected before any provider request. Redaction only applies to allowed inputs
that contain incidental sensitive shapes or machine-local details.

## Deterministic Rules

Rules must be deterministic, ordered, and test-covered. A future implementation
must apply them before evidence export and before any provider request:

| Rule | Replacement | Notes |
| --- | --- | --- |
| Secret-shaped token | `[REDACTED_SECRET]` | Includes provider keys, GitHub tokens, session tokens, and private keys. |
| Absolute local path | `[REDACTED_LOCAL_PATH]` | Preserves only the fact that a local path was present. |
| Environment assignment | `[REDACTED_ENV_VALUE]` | Applies to secret-like environment values. |
| Credential URL component | `[REDACTED_CREDENTIAL]` | Removes userinfo, token query params, and session identifiers. |
| Email or personal identifier | `[REDACTED_PERSONAL_ID]` | Only when incidental to an otherwise allowed public-safe input. |
| Private organization or repository label | `[REDACTED_PRIVATE_REF]` | Must normally block private repo access rather than proceed. |

Rules must be stable across runs. The same input shape should produce the same
redaction label and count without depending on wall-clock time, provider
responses, or external services.

## Never Exported

The evidence bundle must never export:

- raw secrets, tokens, keys, cookies, or session material
- `.env` file contents
- full absolute paths from the operator machine
- private repository contents or private issue/PR contents
- customer data, employer data, or unrelated local files
- provider account identifiers unless explicitly approved and public-safe
- browser session state, cloud credentials, deployment credentials, or payment
  credentials

If these values are necessary to understand the task, the task is outside the
current boundary and must be blocked.

## Evidence Annotation

Every redacted artifact must record redaction metadata that is useful for
review without revealing raw values:

```json
{
  "redaction_profile": "agent_evidence_live_adapter_preflight_v0",
  "redactions_applied": [
    {
      "rule": "secret_shaped_token",
      "replacement": "[REDACTED_SECRET]",
      "count": 1,
      "artifact": "request_envelope.json"
    }
  ],
  "redaction_required_before_provider_call": true,
  "raw_sensitive_values_exported": false
}
```

The reviewer packet must summarize redaction counts and must explicitly say
whether any request was blocked because redaction was insufficient.

## Rejection Over Redaction

Redaction is not enough when the input asks the adapter to read or act on
private material. The correct outcome is `blocked` when the request includes:

- private repository access
- raw `.env` contents
- credential files
- unrelated local directories
- cloud, browser, deployment, publish, payment, hardware, or real-world
  actuation requests
- a task description too vague to verify from the evidence bundle

Blocked records must state that no provider request was sent.

## Verification Requirements

Before any live adapter code exists, tests must be able to verify this contract
from documentation and synthetic fixtures. A future implementation must add
negative controls for:

- secret-shaped values
- absolute local paths
- private repository references
- unrelated local file references
- redaction metadata omissions
- claims that a reviewer outcome is optional

## Current Status

This contract is documentation only. It adds no live provider calls, no
credential access, no private data access, and no release workflow.
