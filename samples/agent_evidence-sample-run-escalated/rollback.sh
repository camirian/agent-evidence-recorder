#!/usr/bin/env bash
set -euo pipefail
TARGET_REPO="${TARGET_REPO:-sample-target-repo}"
RUN_DIR="${RUN_DIR:-samples/agent_evidence-sample-run}"
case "$TARGET_REPO" in /*|~*) echo "Refusing non-relative target path" >&2; exit 1 ;; esac
case "$RUN_DIR" in /*|~*) echo "Refusing non-relative run path" >&2; exit 1 ;; esac
if [ ! -f "$RUN_DIR/git.diff" ]; then echo "Missing recorded diff" >&2; exit 1; fi
cd "$TARGET_REPO"
if [ -n "$(git ls-files --others --exclude-standard 2>/dev/null)" ]; then
  echo "Refusing rollback: untracked files present" >&2
  exit 1
fi
git apply -R "../$RUN_DIR/git.diff"
echo "Rollback applied to modeled git-tracked changes only."
