#!/usr/bin/env bash
# Commit provenance guard: rejects known-bad Git identities and reports
# Co-authored-by trailers so unexpected contributors never reach main silently.
#
# Env overrides (space-separated, optional):
#   ALLOWED_AUTHOR_EMAILS      default: "153974602+camirian@users.noreply.github.com"
#   ALLOWED_COMMITTER_EMAILS   default: ALLOWED_AUTHOR_EMAILS + "noreply@github.com"
#   ALLOWED_COAUTHOR_EMAILS    default: "" (no human co-author pre-approved)
#   BLOCKED_EMAILS             default: "noreply@users.noreply.github.com"
set -euo pipefail

ALLOWED_AUTHOR_EMAILS="${ALLOWED_AUTHOR_EMAILS:-153974602+camirian@users.noreply.github.com}"
ALLOWED_COMMITTER_EMAILS="${ALLOWED_COMMITTER_EMAILS:-153974602+camirian@users.noreply.github.com noreply@github.com}"
ALLOWED_COAUTHOR_EMAILS="${ALLOWED_COAUTHOR_EMAILS:-}"
BLOCKED_EMAILS="${BLOCKED_EMAILS:-noreply@users.noreply.github.com}"

summary="${GITHUB_STEP_SUMMARY:-/dev/stdout}"
fail=0

in_list() { local needle="${1,,}" hay="$2" item; for item in $hay; do [[ "${item,,}" == "$needle" ]] && return 0; done; return 1; }

# --- Resolve the commit range introduced by this PR/push ---------------------
range=""
if [[ "${GITHUB_EVENT_NAME:-}" == "pull_request" || "${GITHUB_EVENT_NAME:-}" == "pull_request_target" ]]; then
  base_sha="$(jq -r '.pull_request.base.sha' "$GITHUB_EVENT_PATH")"
  head_sha="$(jq -r '.pull_request.head.sha' "$GITHUB_EVENT_PATH")"
  merge_base="$(git merge-base "$base_sha" "$head_sha" 2>/dev/null || echo "$base_sha")"
  range="${merge_base}..${head_sha}"
elif [[ "${GITHUB_EVENT_NAME:-}" == "push" ]]; then
  before="$(jq -r '.before' "$GITHUB_EVENT_PATH")"
  after="$(jq -r '.after' "$GITHUB_EVENT_PATH")"
  zero="0000000000000000000000000000000000000000"
  if [[ "$after" == "$zero" ]]; then
    echo "Branch deletion push; nothing to check." | tee -a "$summary"
    exit 0
  fi
  if [[ "$before" == "$zero" ]]; then
    # First push of a new branch/ref: only check commits not already reachable elsewhere.
    commits="$(git rev-list "$after" --not --remotes='origin/*' 2>/dev/null || true)"
    [[ -z "$commits" ]] && commits="$after"
    range=""
  else
    range="${before}..${after}"
  fi
else
  echo "Unrecognized event '${GITHUB_EVENT_NAME:-}', defaulting to HEAD only." | tee -a "$summary"
  commits="$(git rev-parse HEAD)"
fi

if [[ -n "$range" ]]; then
  commits="$(git rev-list "$range")"
fi

if [[ -z "${commits:-}" ]]; then
  echo "No new commits in range; nothing to check." | tee -a "$summary"
  exit 0
fi

{
  echo "## Commit provenance report"
  echo
  echo "| SHA | Subject | Co-author name | Co-author email | Verdict |"
  echo "|---|---|---|---|---|"
} >> "$summary"

for sha in $commits; do
  author_email="$(git show -s --format='%ae' "$sha")"
  committer_email="$(git show -s --format='%ce' "$sha")"
  subject="$(git show -s --format='%s' "$sha" | tr '|' '/')"

  for bad in $BLOCKED_EMAILS; do
    if [[ "${author_email,,}" == "${bad,,}" ]]; then
      echo "::error::Commit $sha ($subject): author email '$author_email' is a blocked identity."
      fail=1
    fi
    if [[ "${committer_email,,}" == "${bad,,}" ]]; then
      echo "::error::Commit $sha ($subject): committer email '$committer_email' is a blocked identity."
      fail=1
    fi
  done

  if ! in_list "$author_email" "$ALLOWED_AUTHOR_EMAILS"; then
    echo "::error::Commit $sha ($subject): author email '$author_email' is not in the allowed author list."
    fail=1
  fi
  if ! in_list "$committer_email" "$ALLOWED_COMMITTER_EMAILS"; then
    echo "::error::Commit $sha ($subject): committer email '$committer_email' is not in the allowed committer list."
    fail=1
  fi

  # Parse Co-authored-by trailers (case-insensitive), tolerate malformed lines.
  while IFS= read -r line; do
    [[ -z "$line" ]] && continue
    trailer_val="$(sed -E 's/^[Cc][Oo]-[Aa]uthored-[Bb][Yy]:[[:space:]]*//; s/\r$//' <<<"$line")"
    if [[ "$trailer_val" =~ ^(.+)\<([^\>]+)\>[[:space:]]*$ ]]; then
      co_name="$(sed -E 's/[[:space:]]+$//' <<<"${BASH_REMATCH[1]}")"
      co_email="${BASH_REMATCH[2]}"
    else
      co_name="(malformed trailer)"
      co_email="$trailer_val"
    fi

    for bad in $BLOCKED_EMAILS; do
      if [[ "${co_email,,}" == "${bad,,}" ]]; then
        echo "| $sha | $subject | $co_name | $co_email | BLOCKED (known-bad identity) |" >> "$summary"
        echo "::error::Commit $sha ($subject): Co-authored-by '$co_email' is a blocked identity."
        fail=1
        continue 2
      fi
    done

    if [[ "$co_name" == "(malformed trailer)" ]]; then
      echo "| $sha | $subject | $co_name | $co_email | FAIL (malformed) |" >> "$summary"
      echo "::error::Commit $sha ($subject): malformed Co-authored-by trailer: '$line'"
      fail=1
    elif in_list "$co_email" "$ALLOWED_COAUTHOR_EMAILS"; then
      echo "| $sha | $subject | $co_name | $co_email | OK (approved human co-author) |" >> "$summary"
    else
      echo "| $sha | $subject | $co_name | $co_email | FAIL (use AI-Assisted-By / Generated-With, or get pre-approved) |" >> "$summary"
      echo "::error::Commit $sha ($subject): unrecognized Co-authored-by '$co_name <$co_email>'. AI/tool assistance must use 'AI-Assisted-By:' or 'Generated-With:' instead of GitHub's Co-authored-by trailer. Human co-authors must be pre-approved via ALLOWED_COAUTHOR_EMAILS."
      fail=1
    fi
  done < <(git show -s --format='%b' "$sha" | grep -iE '^co-authored-by:')
done

if [[ "$fail" -ne 0 ]]; then
  echo >> "$summary"; echo "**Result: FAIL**" >> "$summary"
  exit 1
fi
echo >> "$summary"; echo "**Result: PASS**" >> "$summary"
