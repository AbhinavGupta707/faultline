#!/usr/bin/env bash
# Faultline — scriptable GCP provisioning (idempotent; safe to re-run).
# Usage: bash infra/setup.sh <GCP_PROJECT_ID> [REGION]
# Manual steps (Elastic Cloud, Maps key creation, Firebase init, GitHub, Devpost)
# are in infra/PROVISIONING.md.
set -euo pipefail

PROJECT="${1:?usage: setup.sh <GCP_PROJECT_ID> [REGION]}"
REGION="${2:-us-central1}"
BUCKET="gs://${PROJECT}-faultline"

echo "==> Project: ${PROJECT}  Region: ${REGION}"
gcloud config set project "${PROJECT}"

echo "==> Enabling APIs (Vertex AI / Agent Engine, Run, Build, Secrets, Storage, BigQuery, Scheduler, Firebase, Maps, TTS/STT)"
gcloud services enable \
  aiplatform.googleapis.com \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  bigquery.googleapis.com \
  cloudscheduler.googleapis.com \
  firebasehosting.googleapis.com \
  firebase.googleapis.com \
  maps-backend.googleapis.com \
  geocoding-backend.googleapis.com \
  texttospeech.googleapis.com \
  speech.googleapis.com

echo "==> Service accounts (least privilege)"
for SA in faultline-agent faultline-svc; do
  gcloud iam service-accounts describe "${SA}@${PROJECT}.iam.gserviceaccount.com" >/dev/null 2>&1 \
    || gcloud iam service-accounts create "${SA}" --display-name="Faultline ${SA}"
done
# agent runtime: Vertex inference, secrets, GCS writes (POs/reports), BQ inserts
for ROLE in roles/aiplatform.user roles/secretmanager.secretAccessor roles/bigquery.dataEditor; do
  gcloud projects add-iam-policy-binding "${PROJECT}" --quiet \
    --member="serviceAccount:faultline-agent@${PROJECT}.iam.gserviceaccount.com" --role="${ROLE}" >/dev/null
done
# ingest/tooling services: secrets + geocoding happens via API key, ES via secret
gcloud projects add-iam-policy-binding "${PROJECT}" --quiet \
  --member="serviceAccount:faultline-svc@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor" >/dev/null

echo "==> GCS bucket ${BUCKET}"
gcloud storage buckets describe "${BUCKET}" >/dev/null 2>&1 \
  || gcloud storage buckets create "${BUCKET}" --location="${REGION}" --uniform-bucket-level-access
for SA in faultline-agent faultline-svc; do
  gcloud storage buckets add-iam-policy-binding "${BUCKET}" --quiet \
    --member="serviceAccount:${SA}@${PROJECT}.iam.gserviceaccount.com" \
    --role="roles/storage.objectAdmin" >/dev/null
done

echo "==> BigQuery dataset faultline"
bq --project_id="${PROJECT}" show --dataset faultline >/dev/null 2>&1 \
  || bq --project_id="${PROJECT}" mk --dataset --location=US "${PROJECT}:faultline"

echo "==> Secret Manager (prompts for values; press Enter to skip one)"
for SECRET in ELASTIC_API_KEY KIBANA_URL MAPS_API_KEY; do
  gcloud secrets describe "${SECRET}" >/dev/null 2>&1 \
    || gcloud secrets create "${SECRET}" --replication-policy=automatic
  read -r -p "Value for ${SECRET} (blank to skip): " VAL
  if [ -n "${VAL}" ]; then
    printf '%s' "${VAL}" | gcloud secrets versions add "${SECRET}" --data-file=-
  fi
done

echo "==> Done. Remaining manual steps: infra/PROVISIONING.md (Elastic, Maps key, Firebase init, GitHub, Devpost)."
