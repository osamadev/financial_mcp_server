#!/usr/bin/env bash
# Deploy Financial MCP Server to Google Cloud Run (requires gcloud CLI).
# Usage:
#   Static: MCP_ACCESS_TOKEN=secret ./gcp/deploy-cloudrun.sh [REGION] [SERVICE_NAME]
#   OAuth: MCP_AUTH_MODE=oauth OAUTH_ISSUER_URL=... OAUTH_AUDIENCE=... MCP_RESOURCE_SERVER_URL=... ./gcp/deploy-cloudrun.sh
set -euo pipefail

REGION="${1:-us-central1}"
SERVICE="${2:-financial-mcp-server}"
IMAGE="${IMAGE:-ghcr.io/osamadev/financial_mcp_server:latest}"
PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null)}"

if [[ -z "${PROJECT}" ]]; then
  echo "Set GCP_PROJECT or run: gcloud config set project <project-id>"
  exit 1
fi

AUTH_MODE="${MCP_AUTH_MODE:-static}"
if [[ "${AUTH_MODE}" == "static" ]]; then
  : "${MCP_ACCESS_TOKEN:?Set MCP_ACCESS_TOKEN before deploy (static mode)}"
fi

ENV_VARS="MCP_TRANSPORT=streamable-http,MCP_AUTH_MODE=${AUTH_MODE},HOST=0.0.0.0,LOG_LEVEL=${LOG_LEVEL:-INFO},ALLOW_UNAUTHENTICATED_HTTP=${ALLOW_UNAUTHENTICATED_HTTP:-false},ENABLE_TELEGRAM_ALERTS=${ENABLE_TELEGRAM_ALERTS:-false},SUMMARIZER_PROVIDER=${SUMMARIZER_PROVIDER:-ollama},OLLAMA_MODEL=${OLLAMA_MODEL:-mistral},OPENAI_MODEL=${OPENAI_MODEL:-gpt-4o-mini},OAUTH_REQUIRED_SCOPES=${OAUTH_REQUIRED_SCOPES:-mcp.tools},OAUTH_BROKER_ENABLED=${OAUTH_BROKER_ENABLED:-false}"

append_env() {
  local name="$1"
  local value="${!name:-}"
  if [[ -n "${value}" ]]; then
    ENV_VARS="${ENV_VARS},${name}=${value}"
  fi
}

for var in \
  MCP_ACCESS_TOKEN \
  SERPAPI_API_KEY \
  ALPHA_VANTAGE_API_KEY \
  TELEGRAM_BOT_TOKEN \
  TELEGRAM_USER_ID \
  PORTFOLIO_FILE \
  OLLAMA_HOST \
  OPENAI_API_KEY \
  OPENAI_BASE_URL \
  OAUTH_ISSUER_URL \
  OAUTH_ISSUER_URLS \
  OAUTH_JWKS_URL \
  OAUTH_AUDIENCE \
  OAUTH_SCOPES_SUPPORTED \
  MCP_RESOURCE_SERVER_URL \
  OAUTH_BROKER_ISSUER_URL \
  OAUTH_BROKER_CLIENT_ID \
  OAUTH_BROKER_CLIENT_SECRET \
  OAUTH_BROKER_SCOPE; do
  append_env "${var}"
done

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
  --set-env-vars="${ENV_VARS}"

URL="$(gcloud run services describe "${SERVICE}" --region="${REGION}" --format='value(status.url)')"
echo "MCP endpoint: ${URL}/mcp"
echo "For OAuth mode, set MCP_RESOURCE_SERVER_URL=${MCP_RESOURCE_SERVER_URL:-${URL}/mcp}."
