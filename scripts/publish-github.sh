#!/usr/bin/env bash
# Publish this repo to GitHub (DSW / headless friendly).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PATH="${HOME}/.local/bin:${PATH}"

if ! command -v gh >/dev/null 2>&1; then
  echo "error: gh not found. Add to PATH: ~/.local/bin/gh" >&2
  exit 1
fi

REPO_NAME="${GITHUB_REPO:-deal-desk-flask}"
VIS="${GITHUB_VISIBILITY:-public}"
if [[ "$VIS" != "public" && "$VIS" != "private" ]]; then
  echo "error: GITHUB_VISIBILITY must be public or private" >&2
  exit 1
fi

if ! gh auth status -h github.com >/dev/null 2>&1 && [[ -z "${GH_TOKEN:-}" ]]; then
  echo "error: not logged in. Run: export GH_TOKEN=ghp_...  OR  gh auth login -h github.com" >&2
  exit 1
fi

LOGIN="$(gh api user -q .login)"
echo "Using GitHub account: ${LOGIN}"

if git remote get-url origin >/dev/null 2>&1; then
  echo "Remote origin exists → git push -u origin main"
  git push -u origin main
  echo "Done: $(git remote get-url origin)"
  exit 0
fi

if [[ "$VIS" == "public" ]]; then
  gh repo create "${REPO_NAME}" --public --source=. --remote=origin --push
else
  gh repo create "${REPO_NAME}" --private --source=. --remote=origin --push
fi
echo "Done: https://github.com/${LOGIN}/${REPO_NAME}"
