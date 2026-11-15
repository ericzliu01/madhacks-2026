#!/usr/bin/env bash
# Copy the single-source core (packages/core) into every consumer that must ship it as a plain file
# (the extension, the demo dashboard, and the Databricks App's copy of the stub assistant). Run after editing packages/core/*.js.
# `--check` exits non-zero if any copy is stale (used by tests).
set -euo pipefail
cd "$(dirname "$0")/.."

PAIRS=(
  "packages/core/uxtelemetry.js:dbx-telemetry-ext/src/uxtelemetry.js"
  "packages/core/uxtelemetry.js:demo/dashboard/static/uxtelemetry.js"
  "packages/core/plotly-adapter.js:demo/dashboard/static/plotly-adapter.js"
  "demo/dashboard/chatbot.py:databricks/app/chatbot.py"
)

status=0
for pair in "${PAIRS[@]}"; do
  src="${pair%%:*}"; dst="${pair##*:}"
  if [[ "${1:-}" == "--check" ]]; then
    if ! cmp -s "$src" "$dst"; then echo "STALE: $dst (run scripts/sync-core.sh)"; status=1; fi
  else
    mkdir -p "$(dirname "$dst")"; cp "$src" "$dst"; echo "synced $dst"
  fi
done
exit $status
