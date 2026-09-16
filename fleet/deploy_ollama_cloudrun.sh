#!/usr/bin/env bash
# לזכרה של עלמה ז"ל
#
# ALMAWARE Fleet — deploy Ollama to GCP Cloud Run (free-tier friendly).
#
# Ships the official ollama/ollama image to Cloud Run and warms a lightweight
# model (gemma2:2b by default) so the fleet has a zero-API-cost backend for
# simple/fast/high-volume tasks.
#
# Free-tier notes:
#   - Cloud Run gives 2M requests + 360k GB-s + 180k vCPU-s free per month.
#   - We keep min-instances=0 so it scales to zero (no idle cost) and cap memory.
#   - gemma2:2b (~1.6GB) fits in 4Gi RAM. phi3 also works.
#   - First request after scale-to-zero is a cold start (model load) — slow once,
#     fast after. For always-warm set --min-instances=1 (leaves free tier).
#
# Prereqs: gcloud authenticated, project set, billing enabled (required even for
#          free tier on Cloud Run).
#
# Usage:
#   ./deploy_ollama_cloudrun.sh                 # defaults: gemma2:2b, region us-central1
#   MODEL=phi3 REGION=europe-west1 ./deploy_ollama_cloudrun.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-ollama-fleet}"
MODEL="${MODEL:-gemma2:2b}"
MEMORY="${MEMORY:-4Gi}"
CPU="${CPU:-2}"

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
  echo "ERROR: no GCP project set. Run: gcloud config set project <PROJECT_ID>" >&2
  exit 1
fi

echo ">> Project : ${PROJECT_ID}"
echo ">> Region  : ${REGION}"
echo ">> Service : ${SERVICE}"
echo ">> Model   : ${MODEL}"

echo ">> Enabling required APIs..."
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com --project "${PROJECT_ID}"

# Deploy the upstream Ollama image directly. Cloud Run pulls public Docker Hub
# images via its mirror, so no local build needed.
echo ">> Deploying Ollama to Cloud Run (this can take a few minutes)..."
gcloud run deploy "${SERVICE}" \
  --image=docker.io/ollama/ollama:latest \
  --region="${REGION}" \
  --project="${PROJECT_ID}" \
  --port=11434 \
  --memory="${MEMORY}" \
  --cpu="${CPU}" \
  --min-instances=0 \
  --max-instances=3 \
  --timeout=600 \
  --concurrency=4 \
  --no-cpu-throttling \
  --allow-unauthenticated \
  --set-env-vars=OLLAMA_HOST=0.0.0.0:11434

URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" \
  --project="${PROJECT_ID}" --format='value(status.url)')"
echo ">> Service URL: ${URL}"

echo ">> Pulling model ${MODEL} into the running service..."
# Ollama lazily pulls on first /api/pull. Trigger it now so it's cached.
curl -fsS -X POST "${URL}/api/pull" \
  -H 'content-type: application/json' \
  -d "{\"name\": \"${MODEL}\", \"stream\": false}" \
  && echo "   pull ok" || echo "   (pull may continue in background)"

cat <<EOF

>> Done.

Wire it into the fleet router by exporting the endpoint:
    export OLLAMA_URL="${URL}"

Then test:
    python router.py --task fast "say hi in one word"
    curl -s "${URL}/api/generate" \\
      -d '{"model":"${MODEL}","prompt":"hello","stream":false}'

Cost control:
    - min-instances=0 -> scales to zero, no idle charge (cold starts apply).
    - To lock it down later, drop --allow-unauthenticated and call with an
      identity token: curl -H "Authorization: Bearer \$(gcloud auth print-identity-token)" ...
EOF
