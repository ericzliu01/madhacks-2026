#!/usr/bin/env bash
# Assemble databricks/app/static from the demo dashboard (after syncing the SDK copies) so the app folder is self-contained.
set -euo pipefail
cd "$(dirname "$0")/.."
./scripts/sync-core.sh >/dev/null
rm -rf databricks/app/static && mkdir -p databricks/app/static
cp demo/dashboard/static/* databricks/app/static/
echo "built databricks/app/static ($(ls databricks/app/static | wc -l | tr -d ' ') files)"
