#!/usr/bin/env bash
# Faultline deploy — OWNED BY SESSION F (impl plan §5, parallel plan §3 F duty #1).
#
#   bash infra/deploy.sh                 # everything: 4 Cloud Run services + web + scheduler
#   bash infra/deploy.sh agents web      # any subset: agents|feed_ingest|po_generator|voice_gateway|web|scheduler
#
# Reads repo-root .env (same keys as infra/env.example) for mode flips:
# S1 = set ELASTIC_MODE=live + ELASTICSEARCH_URL + ELASTIC_EVENTS_INDEX=world-events, re-run
# `deploy.sh agents feed_ingest`. S2 = set VITE_DEMO_MODE=live, re-run `deploy.sh web`.
# Secrets (ELASTIC_API_KEY, KIBANA_URL, MAPS_API_KEY) come from Secret Manager, never .env→git.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# gcloud may be a user-local install (not on non-interactive PATH)
export PATH="$HOME/google-cloud-sdk/bin:$PATH"
# ALWAYS prefer nvm's node: WSL interop exposes Windows npm on PATH, which
# fails on UNC paths — `command -v npm` alone is not a safe check here.
export NVM_DIR="$HOME/.nvm"; [ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"

[ -f .env ] && { set -a; . ./.env; set +a; }

PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${VERTEX_LOCATION:-us-central1}"
BUCKET="${GCS_BUCKET:-${PROJECT}-faultline}"
AR_REPO="${REGION}-docker.pkg.dev/${PROJECT}/faultline"
SA_AGENT="faultline-agent@${PROJECT}.iam.gserviceaccount.com"
SA_SVC="faultline-svc@${PROJECT}.iam.gserviceaccount.com"
: "${PROJECT:?no GCP project (set GCP_PROJECT in .env or gcloud config)}"
echo "==> project=${PROJECT} region=${REGION}"

TARGETS=("$@"); [ ${#TARGETS[@]} -eq 0 ] && TARGETS=(agents feed_ingest po_generator voice_gateway web scheduler)
want() { local t; for t in "${TARGETS[@]}"; do [ "$t" = "$1" ] && return 0; done; return 1; }

# ── helpers ──────────────────────────────────────────────────────────────────
ensure_ar() {
  gcloud artifacts repositories describe faultline --location="$REGION" >/dev/null 2>&1 \
    || gcloud artifacts repositories create faultline --location="$REGION" \
         --repository-format=docker --description="Faultline images"
}

# secret exists AND has a version → safe to mount
has_secret() { gcloud secrets versions list "$1" --limit=1 --format="value(name)" 2>/dev/null | grep -q .; }

build_image() { # build_image <name> <dockerfile>  (context is always repo root)
  local name="$1" dockerfile="$2" img="${AR_REPO}/$1:latest" cfg
  cfg="$(mktemp)"
  cat > "$cfg" <<EOF
steps:
- name: gcr.io/cloud-builders/docker
  args: [build, -f, ${dockerfile}, -t, ${img}, .]
images: [${img}]
EOF
  echo "==> build ${name} (${dockerfile})"
  gcloud builds submit . --config="$cfg" --quiet
  rm -f "$cfg"
}

run_url() { gcloud run services describe "$1" --region="$REGION" --format="value(status.url)" 2>/dev/null || true; }

deploy_run() { # deploy_run <service> <sa> <extra flags...>
  local svc="$1" sa="$2"; shift 2
  echo "==> deploy ${svc}"
  gcloud run deploy "$svc" --image="${AR_REPO}/${svc}:latest" --region="$REGION" \
    --service-account="$sa" --port=8080 --quiet "$@"
  echo "    ${svc} → $(run_url "$svc")"
}

join_secrets() { # join_secrets NAME1 NAME2... → "NAME1=NAME1:latest,..." for those that exist
  local out="" s
  for s in "$@"; do has_secret "$s" && out="${out:+${out},}${s}=${s}:latest"; done
  echo "$out"
}

# ── Cloud Run services ───────────────────────────────────────────────────────
ensure_ar

if want feed_ingest; then
  build_image faultline-feed-ingest services/feed_ingest/Dockerfile
  SEC="$(join_secrets ELASTIC_API_KEY MAPS_API_KEY)"
  # private: only Cloud Scheduler (OIDC as faultline-svc) may invoke /ingest
  deploy_run faultline-feed-ingest "$SA_SVC" \
    --no-allow-unauthenticated --memory=512Mi \
    ${SEC:+--set-secrets=${SEC}} \
    --set-env-vars="ELASTIC_MODE=${ELASTIC_MODE:-mock},ELASTICSEARCH_URL=${ELASTICSEARCH_URL:-},ELASTIC_EVENTS_INDEX=${ELASTIC_EVENTS_INDEX:-world-events-dev}"
  gcloud run services add-iam-policy-binding faultline-feed-ingest --region="$REGION" \
    --member="serviceAccount:${SA_SVC}" --role="roles/run.invoker" --quiet >/dev/null
fi

if want po_generator; then
  build_image faultline-po-generator services/po_generator/Dockerfile
  deploy_run faultline-po-generator "$SA_SVC" \
    --allow-unauthenticated --memory=512Mi \
    --set-env-vars="GCS_BUCKET=${BUCKET}"
fi

if want voice_gateway; then
  build_image faultline-voice-gateway services/voice_gateway/Dockerfile
  deploy_run faultline-voice-gateway "$SA_AGENT" \
    --allow-unauthenticated --timeout=3600 --session-affinity --memory=1Gi \
    --set-env-vars="GCP_PROJECT=${PROJECT},VERTEX_LOCATION=${REGION},VOICE_MODE=${VOICE_MODE:-mock},GEMINI_LIVE_MODEL=${GEMINI_LIVE_MODEL:-gemini-live-2.5-flash-native-audio},GEMINI_LIVE_MODEL_FALLBACK=${GEMINI_LIVE_MODEL_FALLBACK:-gemini-live-2.5-flash-native-audio},GEMINI_MODEL_FLASH=${GEMINI_MODEL_FLASH:-gemini-3.5-flash}"
fi

# agents deploys last of the Run services so PO_GENERATOR_URL resolves on a cold project
if want agents; then
  build_image faultline-agents agents/Dockerfile
  PO_URL="$(run_url faultline-po-generator)"
  SEC="$(join_secrets ELASTIC_API_KEY KIBANA_URL)"
  deploy_run faultline-agents "$SA_AGENT" \
    --allow-unauthenticated --timeout=3600 --session-affinity \
    --min-instances=1 --max-instances=2 --memory=1Gi --cpu=1 --no-cpu-throttling \
    ${SEC:+--set-secrets=${SEC}} \
    --set-env-vars="GCP_PROJECT=${PROJECT},VERTEX_LOCATION=${REGION},GCS_BUCKET=${BUCKET},BQ_DATASET=${BQ_DATASET:-faultline},GEMINI_MODEL_PRO=${GEMINI_MODEL_PRO:-gemini-3.1-pro},GEMINI_MODEL_FLASH=${GEMINI_MODEL_FLASH:-gemini-3.5-flash},ELASTIC_MODE=${ELASTIC_MODE:-mock},ELASTIC_EVENTS_INDEX=${ELASTIC_EVENTS_INDEX:-world-events},ELASTICSEARCH_URL=${ELASTICSEARCH_URL:-},COMPANY_PROFILE=${COMPANY_PROFILE:-company_profile.json},PO_GENERATOR_URL=${PO_URL}"
fi

# ── Frontend → Firebase Hosting ──────────────────────────────────────────────
if want web; then
  AGENTS_URL="$(run_url faultline-agents)"; VOICE_URL="$(run_url faultline-voice-gateway)"
  [ -n "$AGENTS_URL" ] || echo "WARN: faultline-agents not deployed yet — web will point at localhost defaults"
  echo "==> web build (VITE_DEMO_MODE=${VITE_DEMO_MODE:-replay})"
  ( cd web && npm ci --no-audit --no-fund >/dev/null && \
    VITE_WS_URL="${AGENTS_URL:+${AGENTS_URL/https:/wss:}/ws}" \
    VITE_API_BASE="${AGENTS_URL}" \
    VITE_VOICE_WS_URL="${VOICE_URL/https:/wss:}" \
    VITE_MAPS_API_KEY="${VITE_MAPS_API_KEY:-${MAPS_API_KEY:-}}" \
    VITE_DEMO_MODE="${VITE_DEMO_MODE:-replay}" \
    npm run build )
  echo "==> firebase deploy"
  npx --yes firebase-tools deploy --only hosting --project "$PROJECT" --non-interactive
  echo "    web → https://${PROJECT}.web.app"
fi

# ── Cloud Scheduler: feed_ingest every 5 min ────────────────────────────────
if want scheduler; then
  FEED_URL="$(run_url faultline-feed-ingest)"
  if [ -z "$FEED_URL" ]; then echo "WARN: feed-ingest not deployed; skipping scheduler"; else
    if gcloud scheduler jobs describe faultline-feed-ingest --location="$REGION" >/dev/null 2>&1; then
      gcloud scheduler jobs update http faultline-feed-ingest --location="$REGION" \
        --schedule="*/5 * * * *" --uri="${FEED_URL}/ingest" --http-method=POST \
        --oidc-service-account-email="$SA_SVC" --quiet
    else
      gcloud scheduler jobs create http faultline-feed-ingest --location="$REGION" \
        --schedule="*/5 * * * *" --uri="${FEED_URL}/ingest" --http-method=POST \
        --oidc-service-account-email="$SA_SVC" --quiet
    fi
    echo "    scheduler → ${FEED_URL}/ingest every 5 min (OIDC ${SA_SVC})"
  fi
fi

echo "==> DEPLOY DONE"
for s in faultline-agents faultline-feed-ingest faultline-po-generator faultline-voice-gateway; do
  u="$(run_url "$s")"; [ -n "$u" ] && echo "    $s  $u"
done
