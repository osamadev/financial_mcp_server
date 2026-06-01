## Deploy

### Option A — One-click (host your own copy)

[![Deploy to Azure](https://aka.ms/deploytoazurebutton)](https://portal.azure.com/#create/Microsoft.Template/uri/https%3A%2F%2Fraw.githubusercontent.com%2Fosamadev%2Ffinancial_mcp_server%2Fmain%2Fazuredeploy.json)
[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/osamadev/financial_mcp_server)
[![Deploy to Heroku](https://www.herokucdn.com/deploy/button.svg)](https://heroku.com/deploy?template=https://github.com/osamadev/financial_mcp_server)

- **Azure Container Apps** uses `azuredeploy.json` (ARM). The button opens the
  Azure Portal pre-filled; pick a resource group, optionally paste your
  `serpApiKey`/Telegram keys (stored as Container App secrets), and deploy. It
  provisions a Container Apps environment + Log Analytics and pulls the public
  GHCR image. The MCP endpoint is the app's HTTPS FQDN + `/mcp` (shown as the
  `mcpEndpoint` output). Runs 1 always-on replica with sticky sessions (so MCP
  session state stays on one instance) — that means a small steady cost, not
  scale-to-zero.
- **Render** reads `render.yaml` (Docker runtime). Click the button, add your
  `SERPAPI_API_KEY` (and Telegram vars) when prompted, deploy. Your endpoint is
  `https://<app>.onrender.com/mcp`.
- **Heroku** uses `app.json` + `heroku.yml` (container stack). Note: Heroku has
  no free tier.
- **Railway**: publish this repo once as a template in the Railway UI
  (New Template -> GitHub repo), then drop in the button:
  `[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/new/template/<YOUR_TEMPLATE_ID>)`

> Free tiers on these platforms sleep after ~15 min idle, so the first MCP call
> after a pause may take 30-60s (the connector can time out on a cold start).
> Use a paid instance or a keep-alive ping for always-on use.

### Option B — Run the prebuilt image anywhere

Every push to `main` publishes a multi-arch image to GHCR via GitHub Actions, so
it runs on any provider that accepts a public image:

```bash
docker run -p 8000:8000 \
  -e MCP_TRANSPORT=streamable-http \
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
custom connector**, paste the `https://.../mcp` URL. The server must be reachable
on the public internet (Claude connects from Anthropic's cloud, not your machine).
