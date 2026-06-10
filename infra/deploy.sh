#!/usr/bin/env bash
# Faultline deploy — OWNED BY SESSION F. Phase 0 stub: outlines the targets so the
# pipeline can be proven against the stubs early (parallel plan §3, F duty #1).
#   Cloud Run:  agents/ (faultline-agent), services/feed_ingest, services/po_generator,
#               services/voice_gateway   — each has a Dockerfile.
#   Firebase:   web/ (npm run build → firebase deploy --only hosting)
#   Scheduler:  every 5 min → feed_ingest /ingest
set -euo pipefail
echo "deploy.sh is a Phase 0 stub — Session F implements (impl plan §5, parallel plan §3)."
exit 1
