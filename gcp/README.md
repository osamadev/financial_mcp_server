# Google Cloud Run

Deploy the Financial MCP Server on **Cloud Run** using the public GHCR image or this repo’s `Dockerfile`.

## One-click (GitHub → Cloud Run)

Use the **Run on Google Cloud** button in the root [`README.md`](../README.md) or [`DEPLOY.md`](../DEPLOY.md). After deploy, open the Cloud Run service → **Edit & deploy new revision** → **Variables & secrets** and set at least:

- `MCP_ACCESS_TOKEN` (static mode)
- `SERPAPI_API_KEY` (optional)
- For OAuth: `MCP_AUTH_MODE=oauth`, `OAUTH_ISSUER_URL`, `OAUTH_AUDIENCE`, `OAUTH_REQUIRED_SCOPES=mcp.tools`, `MCP_RESOURCE_SERVER_URL=https://<service-url>/mcp`

Cloud Run injects `PORT`; the server reads it automatically.

## CLI (`gcloud`)

```bash
export MCP_ACCESS_TOKEN="your-strong-token"
chmod +x gcp/deploy-cloudrun.sh
./gcp/deploy-cloudrun.sh us-central1 financial-mcp-server
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
