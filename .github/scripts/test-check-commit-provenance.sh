#!/usr/bin/env bash
# Deterministic test matrix for check-commit-provenance.sh. Run: bash test-provenance.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$SCRIPT_DIR/check-commit-provenance.sh"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

REPO="$WORK/repo"
git init -q "$REPO"
cd "$REPO"
git config user.name Test; git config user.email test@example.com

commit_as() { # name email subject [body-with-trailers]
  echo "$RANDOM" > f.txt; git add f.txt
  GIT_AUTHOR_NAME="$1" GIT_AUTHOR_EMAIL="$2" GIT_COMMITTER_NAME="$1" GIT_COMMITTER_EMAIL="$2" \
    git commit -q -m "$3" ${4:+-m "$4"}
}

pass=0 fail=0
check() { # description expected_exit
  local desc="$1" expect="$2" summary got out
  summary="$(mktemp)"; out="$(mktemp)"
  GITHUB_STEP_SUMMARY="$summary" bash "$GUARD" >"$out" 2>&1 && got=0 || got=$?
  if [[ "$got" == "$expect" ]]; then
    echo "PASS: $desc"; pass=$((pass+1))
  else
    echo "FAIL: $desc (expected $expect got $got)"; cat "$out"; fail=$((fail+1))
  fi
  rm -f "$summary" "$out"
}

OWNER="153974602+camirian@users.noreply.github.com"
BAD="noreply@users.noreply.github.com"

# --- 1. owner author/committer -> PASS ---
commit_as "Caaren Amirian" "$OWNER" "good: owner commit"
base="$(git rev-parse HEAD)"
export GITHUB_EVENT_NAME=push GITHUB_EVENT_PATH="$WORK/ev.json"
echo "{\"before\":\"$(printf '0%.0s' {1..40})\",\"after\":\"$base\"}" > "$GITHUB_EVENT_PATH"
check "owner author/committer -> PASS" 0

# --- 2. bad author -> FAIL ---
commit_as "Someone" "$BAD" "bad: author is blocked identity"
head1="$(git rev-parse HEAD)"
echo "{\"before\":\"$base\",\"after\":\"$head1\"}" > "$GITHUB_EVENT_PATH"
check "blocked author email -> FAIL" 1

# --- 3. bad committer -> FAIL (author ok, committer bad, via env override) ---
echo "$RANDOM" > f.txt; git add f.txt
GIT_AUTHOR_NAME="Caaren Amirian" GIT_AUTHOR_EMAIL="$OWNER" GIT_COMMITTER_NAME="X" GIT_COMMITTER_EMAIL="$BAD" \
  git commit -q -m "bad: committer is blocked identity"
head2="$(git rev-parse HEAD)"
echo "{\"before\":\"$head1\",\"after\":\"$head2\"}" > "$GITHUB_EVENT_PATH"
check "blocked committer email -> FAIL" 1

# --- 4. GitHub trusted merge committer (noreply@github.com) -> PASS ---
GIT_AUTHOR_NAME="Caaren Amirian" GIT_AUTHOR_EMAIL="$OWNER" GIT_COMMITTER_NAME="GitHub" GIT_COMMITTER_EMAIL="noreply@github.com" \
  git commit -q --allow-empty -m "merge: squash via GitHub UI"
head3="$(git rev-parse HEAD)"
echo "{\"before\":\"$head2\",\"after\":\"$head3\"}" > "$GITHUB_EVENT_PATH"
check "GitHub trusted merge committer -> PASS" 0

# --- 5. AI Co-authored-by -> FAIL under policy ---
commit_as "Caaren Amirian" "$OWNER" "feat: add thing" $'feat: add thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>'
head4="$(git rev-parse HEAD)"
echo "{\"before\":\"$head3\",\"after\":\"$head4\"}" > "$GITHUB_EVENT_PATH"
check "AI Co-authored-by trailer -> FAIL" 1

# --- 6. approved human co-author -> PASS ---
commit_as "Caaren Amirian" "$OWNER" "feat: pair session" $'feat: pair session\n\nCo-authored-by: Jane Human <jane@example.com>'
head5="$(git rev-parse HEAD)"
echo "{\"before\":\"$head4\",\"after\":\"$head5\"}" > "$GITHUB_EVENT_PATH"
ALLOWED_COAUTHOR_EMAILS="jane@example.com" GITHUB_STEP_SUMMARY="$(mktemp)" GITHUB_EVENT_NAME=push GITHUB_EVENT_PATH="$GITHUB_EVENT_PATH" \
  bash "$GUARD" >/tmp/co_out.$$ 2>&1 && r=0 || r=$?
[[ "$r" == 0 ]] && { echo "PASS: approved human co-author -> PASS"; pass=$((pass+1)); } || { echo "FAIL: approved human co-author"; cat /tmp/co_out.$$; fail=$((fail+1)); }
rm -f /tmp/co_out.$$

# --- 7. malformed trailer -> FAIL/detected ---
commit_as "Caaren Amirian" "$OWNER" "feat: malformed trailer" $'feat: malformed trailer\n\nCo-authored-by: not-a-valid-line'
head6="$(git rev-parse HEAD)"
echo "{\"before\":\"$head5\",\"after\":\"$head6\"}" > "$GITHUB_EVENT_PATH"
check "malformed Co-authored-by trailer -> FAIL" 1

# --- 8. multiple trailers -> all reported (2 AI/unknown -> FAIL) ---
commit_as "Caaren Amirian" "$OWNER" "feat: multi" $'feat: multi\n\nCo-authored-by: Claude <noreply@anthropic.com>\nCo-authored-by: Jane Human <jane@example.com>'
head7="$(git rev-parse HEAD)"
echo "{\"before\":\"$head6\",\"after\":\"$head7\"}" > "$GITHUB_EVENT_PATH"
multi_summary="$(mktemp)"
ALLOWED_COAUTHOR_EMAILS="jane@example.com" GITHUB_STEP_SUMMARY="$multi_summary" bash "$GUARD" >/tmp/multi.$$ 2>&1 && r=0 || r=$?
grep -q "noreply@anthropic.com" "$multi_summary" && grep -q "jane@example.com" "$multi_summary" && [[ "$r" == 1 ]] \
  && { echo "PASS: multiple trailers all reported, AI one fails"; pass=$((pass+1)); } \
  || { echo "FAIL: multiple trailers case"; cat "$multi_summary" /tmp/multi.$$; fail=$((fail+1)); }
rm -f /tmp/multi.$$ "$multi_summary"

# --- 9. old bad historical commit outside PR range -> does not fail new PR ---
# head1 (bad author) is now old history; a new PR range starting after head7 with a good commit must pass.
commit_as "Caaren Amirian" "$OWNER" "good: unrelated to old bad history"
head8="$(git rev-parse HEAD)"
echo "{\"before\":\"$head7\",\"after\":\"$head8\"}" > "$GITHUB_EVENT_PATH"
check "old bad commit outside range ignored -> PASS" 0

# --- 10. new bad commit inside PR range -> FAIL (pull_request event, base/head) ---
git branch base_branch "$head8"
commit_as "Someone" "$BAD" "bad: inside this PR"
head9="$(git rev-parse HEAD)"
cat > "$GITHUB_EVENT_PATH" <<EOF
{"pull_request":{"base":{"sha":"$head8"},"head":{"sha":"$head9"}}}
EOF
export GITHUB_EVENT_NAME=pull_request
check "new bad commit inside PR range -> FAIL" 1

# --- 11. merge commit / range edge case: merge commit with two parents, only new side checked ---
git checkout -q -b feature base_branch
commit_as "Caaren Amirian" "$OWNER" "feat: on feature branch"
feat_head="$(git rev-parse HEAD)"
git checkout -q -B main_tmp "$head8"
GIT_AUTHOR_NAME="Caaren Amirian" GIT_AUTHOR_EMAIL="$OWNER" GIT_COMMITTER_NAME="Caaren Amirian" GIT_COMMITTER_EMAIL="$OWNER" \
  git merge -q --no-ff feature -m "merge: feature into main" || true
merge_head="$(git rev-parse HEAD)"
cat > "$GITHUB_EVENT_PATH" <<EOF
{"pull_request":{"base":{"sha":"$head8"},"head":{"sha":"$merge_head"}}}
EOF
check "merge commit range -> PASS (only new commits, all owner)" 0

# --- 12. CRLF-terminated trailer (Windows line endings) -> parsed, not misclassified as malformed ---
git checkout -q main_tmp
printf 'crlf-test\r\n' > f.txt; git add f.txt
GIT_AUTHOR_NAME="Caaren Amirian" GIT_AUTHOR_EMAIL="$OWNER" GIT_COMMITTER_NAME="Caaren Amirian" GIT_COMMITTER_EMAIL="$OWNER" \
  git commit -q -m "$(printf 'feat: crlf trailer\r\n\r\nCo-authored-by: Jane Human <jane@example.com>\r\n')"
crlf_head="$(git rev-parse HEAD)"
echo "{\"before\":\"$merge_head\",\"after\":\"$crlf_head\"}" > "$GITHUB_EVENT_PATH"
export GITHUB_EVENT_NAME=push
crlf_summary="$(mktemp)"
ALLOWED_COAUTHOR_EMAILS="jane@example.com" GITHUB_STEP_SUMMARY="$crlf_summary" bash "$GUARD" >/tmp/crlf.$$ 2>&1 && r=0 || r=$?
grep -q "jane@example.com" "$crlf_summary" && ! grep -qi "malformed" "$crlf_summary" && [[ "$r" == 0 ]] \
  && { echo "PASS: CRLF-terminated trailer parsed correctly -> PASS"; pass=$((pass+1)); } \
  || { echo "FAIL: CRLF trailer case"; cat "$crlf_summary" /tmp/crlf.$$; fail=$((fail+1)); }
rm -f /tmp/crlf.$$ "$crlf_summary"

echo
echo "Summary: $pass passed, $fail failed"
[[ "$fail" -eq 0 ]]
