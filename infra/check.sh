#!/usr/bin/env bash
# Faultline main-branch health check (Session F).
# Each suite runs as its own pytest invocation: the service test dirs use
# flat (non-package) layouts whose conftest/test module basenames collide
# when collected together. Per-suite runs match how each lane verifies.
set -uo pipefail
cd "$(dirname "$0")/.."

fail=0
run() {
  echo "=== $* ==="
  python3 -m pytest "$@" -q || fail=1
}

run agents contracts
run services/feed_ingest
run services/po_generator
run services/voice_gateway

if [ -d web/node_modules ]; then
  echo "=== web build ==="
  (cd web && npm run build) || fail=1
else
  echo "=== web build SKIPPED (web/node_modules missing — run npm ci in web/) ==="
fi

if [ "$fail" -ne 0 ]; then echo "CHECK FAILED"; exit 1; fi
echo "ALL CHECKS GREEN"
