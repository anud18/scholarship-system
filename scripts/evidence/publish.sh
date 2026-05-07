#!/usr/bin/env bash
# scripts/evidence/publish.sh — Publish a staging-test session's evidence
# directory to a dedicated `evidence/<date>` orphan branch on origin.
#
# Usage:
#   scripts/evidence/publish.sh <YYYY-MM-DD>
#
# What it does:
#   1. Validates the date dir exists under docs/staging-tests/<date>/.
#   2. Stashes any local changes so the branch switch is clean.
#   3. Creates or fast-forwards `evidence/<date>` (orphan if it doesn't exist
#      yet on origin).
#   4. Copies the evidence tree onto the orphan branch, runs render.mjs to
#      generate index.html, commits, pushes.
#   5. Returns to the previous branch and pops the stash.
#
# This script intentionally does NOT modify the user's main worktree on the
# original branch — it stashes, switches, publishes, and switches back.
set -euo pipefail

DATE="${1:-}"
if [ -z "$DATE" ] || ! [[ "$DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
  echo "usage: $0 <YYYY-MM-DD>" >&2
  exit 2
fi

REPO_ROOT=$(git rev-parse --show-toplevel)
cd "$REPO_ROOT"

SRC_DIR="docs/staging-tests/$DATE"
if [ ! -d "$SRC_DIR" ]; then
  echo "error: source directory $SRC_DIR not found" >&2
  echo "       did you run the test session and write artifacts under that path?" >&2
  exit 2
fi

# Capture a clean copy of the evidence tree before switching branches; the
# subsequent checkout would either delete the dir (if it's gitignored) or fail
# (if it has uncommitted tracked changes).
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
cp -r "$SRC_DIR" "$TMP/$DATE"

ORIG_BRANCH=$(git rev-parse --abbrev-ref HEAD)
STASH_REF=""
if ! git diff-index --quiet HEAD -- || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  echo "==> stashing local changes (will pop after publish)"
  git stash push -u -m "evidence-publish $DATE on $ORIG_BRANCH" >/dev/null
  STASH_REF=$(git stash list | awk -F: 'NR==1 {print $1}')
fi

echo "==> fetching origin"
git fetch origin --quiet || true

if git rev-parse --verify "origin/evidence/$DATE" >/dev/null 2>&1; then
  echo "==> evidence/$DATE already exists on origin — checking out"
  git checkout -B "evidence/$DATE" "origin/evidence/$DATE"
else
  echo "==> creating new orphan branch evidence/$DATE"
  git checkout --orphan "evidence/$DATE"
  # Empty out the index — orphan keeps tracked files in the worktree
  git rm -rf --quiet --cached . 2>/dev/null || true
  # And delete worktree files (they're tracked from the parent commit). Use
  # `find -delete` instead of `rm -rf .` so we don't blow away .git.
  find . -maxdepth 1 -mindepth 1 -not -name '.git' -exec rm -rf {} +
fi

echo "==> copying evidence tree into orphan branch"
mkdir -p "$SRC_DIR"
cp -r "$TMP/$DATE/." "$SRC_DIR/"

echo "==> generating index.html"
node "$REPO_ROOT/scripts/evidence/render.mjs" --date "$DATE" --src "$SRC_DIR" --out "$REPO_ROOT" >&2 || {
  echo "render.mjs failed" >&2
  exit 1
}

echo "==> staging + committing"
git add -A
if git diff --cached --quiet; then
  echo "    no changes to commit (orphan branch already up-to-date)"
else
  git commit -m "evidence: snapshot $DATE"
fi

echo "==> pushing to origin/evidence/$DATE"
git push origin "evidence/$DATE"

echo "==> switching back to $ORIG_BRANCH"
git checkout "$ORIG_BRANCH"

if [ -n "$STASH_REF" ]; then
  echo "==> popping stash"
  git stash pop "$STASH_REF" >/dev/null || {
    echo "    stash pop hit a conflict; resolve manually with: git stash pop $STASH_REF" >&2
  }
fi

echo
echo "✅ published evidence/$DATE"
echo "   tree:  https://github.com/anud18/scholarship-system/tree/evidence/$DATE"
echo "   index: https://github.com/anud18/scholarship-system/blob/evidence/$DATE/index.html"
