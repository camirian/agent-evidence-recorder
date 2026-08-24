# PR Review Packet: camirian/agent_evidence-recorder #24

Title: Add PR review bundle verifier
URL: https://github.com/camirian/agent_evidence-recorder/pull/24
State: MERGED
Author: camirian
Base/head: `main` <- `feature/verify-pr-review-bundle`

## Risk Summary

- Risk level: `needs_review`
- Review decision: `none`
- Status checks observed: 0
- Status check results: none
- Diff excerpts observed/omitted/truncated: 5/0/0
- Changed files observed/reported: 5/5
- Additions/deletions: +260/-2
- Risk flags: documentation, source_code

## Risk Reasons

- `status_checks_missing`

## PR-Review Trap Classes

- `missing_checks_requires_review`

## Review Decision Checklist

- [ ] Compare the PR title/body against `pr_metadata.json`, `changed_files.json`, and the diff excerpts.
- [ ] Resolve `status_checks_missing`: require a human decision because no check evidence was reported.
- [ ] Decide whether missing status checks are acceptable before trusting the run.
- [ ] Inspect each bounded diff excerpt and decide whether it is enough for this review.
- [ ] Record one outcome: accept, reject, request changes, or request a narrower follow-up run.

## Changed Files

- `README.md` (+5/-0) flags: documentation
- `docs/GITHUB_PR_REVIEW_BUNDLE.md` (+12/-0) flags: documentation
- `agent_evidence_recorder/pr_review.py` (+149/-0) flags: source_code
- `agent_evidence_recorder/__main__.py` (+13/-1) flags: source_code
- `tests/test_sample.py` (+83/-1) flags: source_code

## Diff Excerpts

### `README.md`

- Status: `modified`; additions/deletions: +5/-0; patch lines shown/total: 5/5

```diff
@@ -130,6 +130,7 @@ GitHub CLI:
 ```bash
 agent_evidence-recorder pr-review --repo camirian/agent_evidence-recorder --pr 19
+agent_evidence-recorder verify-pr-review --bundle-dir agent_evidence-pr-review
 ```
```

### `docs/GITHUB_PR_REVIEW_BUNDLE.md`

- Status: `modified`; additions/deletions: +12/-0; patch lines shown/total: 8/8

```diff
@@ -25,6 +25,14 @@ agent_evidence-pr-review/
   status_checks.json
 ```
+Verify the generated bundle before reviewing it:
+
+```bash
+agent_evidence-recorder verify-pr-review --bundle-dir agent_evidence-pr-review
+```
```

### `agent_evidence_recorder/pr_review.py`

- Status: `modified`; additions/deletions: +149/-0; patch lines shown/total: 5/5

```diff
@@ -126,6 +137,20 @@ def write_pr_review_bundle(
+def verify_pr_review_bundle(bundle_dir: Path) -> dict[str, Any]:
+    checks: list[dict[str, Any]] = []
+    def add(name: str, passed: bool, detail: str = "") -> None:
+        checks.append({"name": name, "passed": passed, "detail": detail})
```

### `agent_evidence_recorder/__main__.py`

- Status: `modified`; additions/deletions: +13/-1; patch lines shown/total: 3/3

```diff
@@ -24,6 +24,11 @@ def main() -> int:
+    verify_pr_review = subcommands.add_parser("verify-pr-review", help="verify a generated GitHub PR review bundle")
+    verify_pr_review.add_argument("--bundle-dir", default="agent_evidence-pr-review")
```

### `tests/test_sample.py`

- Status: `modified`; additions/deletions: +83/-1; patch lines shown/total: 4/4

```diff
@@ -286,6 +286,30 @@ class PublicSampleTests(unittest.TestCase):
+    def test_verify_pr_review_bundle_accepts_generated_bundle(self) -> None:
+        report = verify_pr_review_bundle(output_dir)
+        self.assertTrue(report["passed"], report)
```

## Status Checks

- No status checks reported by GitHub metadata.

## Reviewer Questions

- Does the PR title/body state an intent specific enough to compare against the file list?
- Do changed files match the stated intent?
- Do the bounded diff excerpts support the stated intent?
- Are CI, automation, security, auth, or policy files changed?
- Are status checks present and sufficient for the change type?
- What rollback boundary is realistic for this PR?
