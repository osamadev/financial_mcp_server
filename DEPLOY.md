## Deploy

### Option A — One-click (host your own copy)

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fosamadev%2Ffinancial_mcp_server%2Fmain%2Fazuredeploy.json)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/osamadev/financial_mcp_server)
[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/osamadev/financial_mcp_server/tree/main/cloudflare-worker)

- **Azure Container Apps** uses `azuredeploy.json` (ARM). The button opens the
  Azure Portal pre-filled; pick a resource group, optionally paste your
  `mcpAccessToken` plus optional `serpApiKey`/Telegram keys (stored as Container App secrets), and deploy. It
  provisions a Container Apps environment + Log Analytics and pulls the public
  GHCR image. The MCP endpoint is the app's HTTPS FQDN + `/mcp` (shown as the
  `mcpEndpoint` output). Runs 1 always-on replica with sticky sessions (so MCP
  session state stays on one instance) — that means a small steady cost, not
  scale-to-zero.
- **Render** reads `render.yaml` (Docker runtime). Click the button, add your
  `SERPAPI_API_KEY` (and Telegram vars) when prompted, deploy. Your endpoint is
  `https://<app>.onrender.com/mcp`.
- **Cloudflare Worker proxy** deploys only the proxy app in `cloudflare-worker/`.
  It does not host the Python MCP backend itself.

### Cloudflare proxy flow (two steps)

1. Deploy the Python MCP backend to **Azure** or **Render**.
2. Deploy the Cloudflare Worker proxy, then set:
   - `MCP_BACKEND_URL=https://<your-azure-or-render-host>/mcp`
   - `MCP_ACCESS_TOKEN=<same-token-as-backend>`

The Worker validates the caller's bearer token and forwards MCP traffic to the
backend with the same token.

> Free tiers on these platforms sleep after ~15 min idle, so the first MCP call
> after a pause may take 30-60s (the connector can time out on a cold start).
> Use a paid instance or a keep-alive ping for always-on use.

### Option B — Run the prebuilt image anywhere

Every push to `main` publishes a multi-arch image to GHCR via GitHub Actions, so
it runs on any provider that accepts a public image:

```bash
docker run -p 8000:8000 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_ACCESS_TOKEN=replace_with_strong_token \
  -e SERPAPI_API_KEY=your_key \
  ghcr.io/osamadev/financial_mcp_server:latest
# MCP endpoint -> http://localhost:8000/mcp
```

- **Any VPS / Docker host, Fly.io, Azure Container Apps, AWS ECS/Fargate, Koyeb**
  can pull `ghcr.io/...` directly (`fly launch --image ghcr.io/osamadev/financial_mcp_server:latest`).
- **Google Cloud Run / AWS App Runner** prefer their own registry — mirror the
  image into Artifact Registry / ECR first, then deploy it.

To make the GHCR package public: GitHub repo -> Packages -> the image ->
Package settings -> Change visibility -> Public. No registry secrets are needed;
the workflow authenticates with the built-in `GITHUB_TOKEN`.

### Connect from Claude

Once it is live over HTTPS: Claude -> **Customize -> Connectors -> + -> Add
custom connector**, paste:
- backend direct URL: `https://.../mcp`, or
- Cloudflare proxy URL: `https://<worker-subdomain>.workers.dev/mcp`

The server must be reachable
on the public internet (Claude connects from Anthropic's cloud, not your machine).

When HTTP security is enabled (recommended), include:
- Header: `Authorization: Bearer <MCP_ACCESS_TOKEN>`
- Rotate `MCP_ACCESS_TOKEN` whenever sharing or revoking access.

Quick verification after deploy:

```bash
curl -X POST "https://<your-host>/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer <MCP_ACCESS_TOKEN>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```
