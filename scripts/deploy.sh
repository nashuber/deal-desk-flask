#!/bin/bash
# Deploy the latest main onto this DSW serve directory.
#
# This directory is DEPLOY-ONLY: never hand-edit files here. Develop on your
# laptop, push to origin/main, then run this script on DSW to pull the code.
#
# It hard-resets the working tree to origin/main. Untracked / gitignored files
# (notably data/deals.json produced by run_extract.py, and any *.xlsx) are NOT
# touched, so the live dataset survives a code deploy.
#
# The live Flask process is managed by the DSW dashboard, so after this runs you
# must RESTART the dashboard from the DSW UI (Stop -> Start) for code changes to
# take effect. (Changes to data/deals.json are hot-reloaded without a restart.)
set -euo pipefail

cd "$(dirname "$0")/.."
REPO_DIR="$(pwd)"
echo "[deploy] repo: $REPO_DIR"

echo "[deploy] fetching origin..."
git fetch origin

OLD=$(git rev-parse --short HEAD)
git reset --hard origin/main
NEW=$(git rev-parse --short HEAD)
echo "[deploy] code updated: $OLD -> $NEW"

if [[ ! -f data/deals.json ]]; then
  echo "[deploy] WARNING: data/deals.json missing. Run run_extract.py (or seed from"
  echo "         data/deals.sample.json) before the dashboard will show live data."
fi

echo "[deploy] DONE. Now RESTART the dashboard from the DSW UI (Stop -> Start)"
echo "         so the new code is loaded (data changes hot-reload on their own)."
