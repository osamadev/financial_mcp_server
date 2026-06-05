# Google Cloud Run

Deploy the Financial MCP Server on **Cloud Run** using the public GHCR image or this repo’s `Dockerfile`.

## One-click (GitHub → Cloud Run)

Use the **Run on Google Cloud** button in the root [`README.md`](../README.md) or [`DEPLOY.md`](../DEPLOY.md). After deploy, open the Cloud Run service → **Edit & deploy new revision** → **Variables & secrets** and set at least:

- `MCP_ACCESS_TOKEN` (static mode)
- `SERPAPI_API_KEY` (optional)
- `ALPHA_VANTAGE_API_KEY` (optional; reserved — quotes currently use yfinance)
- Optional: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_USER_ID`, `ENABLE_TELEGRAM_ALERTS`, `PORTFOLIO_FILE`
- Optional summarizer: `SUMMARIZER_PROVIDER`, `OLLAMA_HOST`, `OLLAMA_MODEL`, `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL`
- For OAuth: `MCP_AUTH_MODE=oauth`, `OAUTH_ISSUER_URL`, `OAUTH_ISSUER_URLS`, `OAUTH_AUDIENCE`, `OAUTH_REQUIRED_SCOPES=mcp.tools`, `OAUTH_SCOPES_SUPPORTED`, `MCP_RESOURCE_SERVER_URL=https://<service-url>/mcp`
- For the Claude + Entra broker: `OAUTH_BROKER_ENABLED=true`, `OAUTH_BROKER_ISSUER_URL`, `OAUTH_BROKER_CLIENT_ID`, `OAUTH_BROKER_CLIENT_SECRET`, `OAUTH_BROKER_SCOPE`

Cloud Run injects `PORT`; the server reads it automatically.

## CLI (`gcloud`)

```bash
export MCP_ACCESS_TOKEN="your-strong-token"  # static mode
chmod +x gcp/deploy-cloudrun.sh
./gcp/deploy-cloudrun.sh us-central1 financial-mcp-server
```

The script reads the same optional environment variables listed above. For OAuth mode, export them before running the script:

```bash
export MCP_AUTH_MODE=oauth
export OAUTH_ISSUER_URL="https://login.microsoftonline.com/<tenant-id>/v2.0"
export OAUTH_AUDIENCE="api://<api-app-id>,<api-app-id>"
export OAUTH_REQUIRED_SCOPES="mcp.tools"
export OAUTH_SCOPES_SUPPORTED="api://<api-app-id>/mcp.tools"
export MCP_RESOURCE_SERVER_URL="https://<service-url>/mcp"
```

Or deploy manually:

```bash
gcloud run deploy financial-mcp-server \
  --image ghcr.io/osamadev/financial_mcp_server:latest \
  --region us-central1 \
  --allow-unauthenticated \
  --port 8000 \
  --set-env-vars MCP_TRANSPORT=streamable-http,MCP_AUTH_MODE=static,MCP_ACCESS_TOKEN=YOUR_TOKEN,OAUTH_REQUIRED_SCOPES=mcp.tools
```

Endpoint: `https://<service-url>/mcp`

OAuth (Entra) client setup: [`DEPLOY.md` — OAuth (Entra ID)](../DEPLOY.md#oauth-entra-id).
