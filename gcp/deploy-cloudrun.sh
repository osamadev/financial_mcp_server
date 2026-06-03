#!/usr/bin/env bash
# Deploy Financial MCP Server to Google Cloud Run (requires gcloud CLI).
# Usage: MCP_ACCESS_TOKEN=secret ./gcp/deploy-cloudrun.sh [REGION] [SERVICE_NAME]
set -euo pipefail

REGION="${1:-us-central1}"
SERVICE="${2:-financial-mcp-server}"
IMAGE="${IMAGE:-ghcr.io/osamadev/financial_mcp_server:latest}"
PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"

if [[ -z "${PROJECT}" ]]; then
  echo "Set GCP_PROJECT or run: gcloud config set project <project-id>"
  exit 1
fi

: "${MCP_ACCESS_TOKEN:?Set MCP_ACCESS_TOKEN before deploy (static mode)}"

gcloud run deploy "${SERVICE}" \
  --project="${PROJECT}" \
  --region="${REGION}" \
  --image="${IMAGE}" \
  --platform=managed \
  --allow-unauthenticated \
  --port=8000 \
  --memory=1Gi \
  --cpu=1 \
  --min-instances=0 \
  --max-instances=3 \
  --set-env-vars="MCP_TRANSPORT=streamable-http,MCP_AUTH_MODE=static,MCP_ACCESS_TOKEN=${MCP_ACCESS_TOKEN},HOST=0.0.0.0,LOG_LEVEL=INFO,OAUTH_REQUIRED_SCOPES=mcp.tools"

URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"
echo "MCP endpoint: ${URL}/mcp"
echo "For OAuth mode, set MCP_AUTH_MODE=oauth and MCP_RESOURCE_SERVER_URL=${URL}/mcp in the Cloud Run console."
