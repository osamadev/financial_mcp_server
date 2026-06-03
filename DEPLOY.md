## Deploy

### One-click buttons

Host your own copy from this repository (fork first if you need a custom `azuredeploy.json` / `render.yaml`).

<p align="center">
  <a href="https://portal.azure.com/#create/Microsoft.Template/uri=https%3A%2F%2Fraw.githubusercontent.com%2Fosamadev%2Ffinancial_mcp_server%2Fmain%2Fazuredeploy.json">
    <img src="https://aka.ms/deploytoazurebutton" alt="Deploy to Azure" height="40" width="180" />
  </a>
  &nbsp;
  <a href="https://render.com/deploy?repo=https://github.com/osamadev/financial_mcp_server">
    <img src="https://render.com/images/deploy-to-render-button.svg" alt="Deploy to Render" height="40" width="180" />
  </a>
  &nbsp;
  <a href="https://deploy.cloud.run/?git_repo=https://github.com/osamadev/financial_mcp_server">
    <img src="https://deploy.cloud.run/button.svg" alt="Run on Google Cloud" height="40" width="180" />
  </a>
  &nbsp;
  <a href="https://deploy.workers.cloudflare.com/?url=https://github.com/osamadev/financial_mcp_server/tree/main/cloudflare-worker">
    <img src="https://deploy.workers.cloudflare.com/button" alt="Deploy to Cloudflare" height="40" width="180" />
  </a>
</p>

| Button | What it deploys | Endpoint | Auth defaults |
|--------|-----------------|----------|---------------|
| **Azure** | Container Apps + Log Analytics via `azuredeploy.json` | `mcpEndpoint` output → `https://<fqdn>/mcp` | `mcpAuthMode=static`; set `mcpAccessToken` in the portal |
| **Render** | Docker web service via `render.yaml` | `https://<app>.onrender.com/mcp` | `MCP_AUTH_MODE=static`; set `MCP_ACCESS_TOKEN` when prompted |
| **Google Cloud** | Cloud Run from repo `Dockerfile` ([`gcp/`](gcp/)) | `https://<service>.run.app/mcp` | Set `MCP_ACCESS_TOKEN` in Cloud Run after one-click deploy |
| **Cloudflare** | Worker proxy in `cloudflare-worker/` only | `https://<worker>.workers.dev/mcp` | Not the Python backend — configure `MCP_BACKEND_URL` after backend deploy |

> **Free tiers** sleep after ~15 min idle; the first MCP call after idle may take 30–60s.
> Use a paid plan or a keep-alive ping for production connectors.

---

### Option A — Platform notes

#### Azure Container Apps

1. Click **Deploy to Azure** (or use the [portal link](https://portal.azure.com/#create/Microsoft.Template/uri=https%3A%2F%2Fraw.githubusercontent.com%2Fosamadev%2Ffinancial_mcp_server%2Fmain%2Fazuredeploy.json)).
2. Pick a resource group and region.
3. **Static auth (simplest):** leave `mcpAuthMode` as `static`, set `mcpAccessToken`.
4. **OAuth auth:** set `mcpAuthMode` to `oauth`, leave `mcpAccessToken` empty, fill `oauthIssuerUrl`, `oauthAudience`, `oauthRequiredScopes`, and `mcpResourceServerUrl` (use `https://<fqdn>/mcp` after first deploy, or your known hostname).
5. Optional: `serpApiKey`, Telegram vars, summarizer settings.
6. Deploy; copy the **`mcpEndpoint`** output for Claude.

Runs one always-on replica with sticky sessions (small steady cost, not scale-to-zero).

#### Render

1. Click **Deploy to Render**.
2. Connect the repo; Render applies `render.yaml` (Docker, `streamable-http`).
3. When prompted, set `MCP_ACCESS_TOKEN` (static mode) and optional `SERPAPI_API_KEY` / Telegram vars.
4. For **OAuth**, open the service → **Environment** and add variables from [Backend env (OAuth)](#backend-env-oauth) below.

#### Cloudflare Worker (proxy)

1. Deploy the **Python backend** on Azure or Render first.
2. Click **Deploy to Cloudflare** (or `npm run deploy` in `cloudflare-worker/`).
3. Set Worker secrets/vars:
   - `MCP_BACKEND_URL` = `https://<backend-host>/mcp`
   - **Static:** `WORKER_AUTH_MODE=static`, `MCP_ACCESS_TOKEN` = same as backend `MCP_ACCESS_TOKEN`
   - **OAuth:** `WORKER_AUTH_MODE=passthrough` (forwards the caller’s Entra JWT to the backend)

See [`cloudflare-worker/README.md`](cloudflare-worker/README.md).

#### Google Cloud Run

1. Click **Run on Google Cloud** (builds from this repo’s `Dockerfile` via [deploy.cloud.run](https://deploy.cloud.run/)).
2. Select project/region; allow the deploy to finish.
3. Open the service → **Edit & deploy new revision** → **Variables & secrets**:
   - `MCP_ACCESS_TOKEN` (static mode)
   - Optional: `SERPAPI_API_KEY`, Telegram vars
   - OAuth: `MCP_AUTH_MODE=oauth`, `OAUTH_ISSUER_URL`, `OAUTH_AUDIENCE`, `OAUTH_REQUIRED_SCOPES=mcp.tools`, `MCP_RESOURCE_SERVER_URL=https://<url>/mcp`
4. MCP URL: `https://<service-url>/mcp`

CLI alternative: [`gcp/deploy-cloudrun.sh`](gcp/deploy-cloudrun.sh) — details in [`gcp/README.md`](gcp/README.md).

---

### Option B — Run the prebuilt image anywhere

Every push to `main` publishes a multi-arch image to GHCR:

```bash
docker run -p 8000:8000 \
  -e MCP_TRANSPORT=streamable-http \
  -e MCP_AUTH_MODE=static \
  -e MCP_ACCESS_TOKEN=replace_with_strong_token \
  -e SERPAPI_API_KEY=your_key \
  ghcr.io/osamadev/financial_mcp_server:latest
# MCP endpoint -> http://localhost:8000/mcp
```

- **VPS / Fly.io / Container Apps / Cloud Run / ECS** can pull `ghcr.io/osamadev/financial_mcp_server:latest`.
- **Cloud Run / App Runner** — mirror the image to your registry first.

Make the GHCR package public: GitHub repo → **Packages** → image → **Package settings** → **Change visibility** → Public.

---

## OAuth (Entra ID)

Use this when Claude’s custom connector should use **OAuth** (client ID + client secret in Claude), not a static `MCP_ACCESS_TOKEN` on the connector.

The MCP server **only validates JWTs**. It does **not** store an OAuth client secret.

### Overview

| App registration | Purpose | Credentials live in |
|------------------|---------|---------------------|
| **API app** (`financial-mcp-api`) | Defines scopes & audience (`aud` in token) | Azure portal only |
| **Client app** (`financial-mcp-claude-client`) | Claude sign-in, redirect URIs, client secret | **Claude connector** (+ Entra portal) |
| **MCP backend** | Validates `iss`, `aud`, `scp`/`scope` | Container env / Azure ARM parameters |

### 1. Register the API app (resource server)

1. [Microsoft Entra admin center](https://entra.microsoft.com) → **Applications** → **App registrations** → **New registration**.
2. Name: e.g. `financial-mcp-api`. Note **Application (client) ID** and **Directory (tenant) ID**.
3. **Expose an API**:
   - Set **Application ID URI** (e.g. `api://financial-mcp` or default `api://<api-client-id>`).
   - **Add a scope**: name `mcp.tools` (must match `OAUTH_REQUIRED_SCOPES` on the server).
   - Note the full scope clients request, e.g. `api://financial-mcp/mcp.tools`.

### 2. Register the OAuth client app (for Claude)

1. **New registration** → e.g. `financial-mcp-claude-client`.
2. **Authentication** → **Add platform** → **Web** (or per [Claude custom connector](https://support.anthropic.com/) docs).
3. Add **Redirect URIs** exactly as Claude documents for custom MCP connectors (wrong URI → sign-in failure).
4. **Certificates & secrets** → **New client secret** → copy value once (used in Claude only).
5. **API permissions** → **Add permission** → **My APIs** → `financial-mcp-api` → delegated `mcp.tools` → **Grant admin consent** if required.

**Do not** put the client secret in Azure Container Apps, Render, or Docker env vars.

### 3. Deploy backend with OAuth env {#backend-env-oauth}

After the backend is reachable at a public HTTPS URL:

```env
MCP_TRANSPORT=streamable-http
MCP_AUTH_MODE=oauth
OAUTH_ISSUER_URL=https://login.microsoftonline.com/<tenant-id>/v2.0
OAUTH_AUDIENCE=api://<api-app-client-id>,<api-app-client-id>
OAUTH_REQUIRED_SCOPES=mcp.tools
MCP_RESOURCE_SERVER_URL=https://<your-public-host>/mcp
```

| Variable | Azure ARM parameter | Notes |
|----------|---------------------|--------|
| `MCP_AUTH_MODE` | `mcpAuthMode` | `oauth` |
| `OAUTH_ISSUER_URL` | `oauthIssuerUrl` | Tenant v2.0 issuer |
| `OAUTH_AUDIENCE` | `oauthAudience` | Match token `aud` (URI and/or API app GUID, comma-separated) |
| `OAUTH_REQUIRED_SCOPES` | `oauthRequiredScopes` | Must appear in JWT `scp` or `scope` — decode a test token at [jwt.ms](https://jwt.ms) and align |
| `MCP_RESOURCE_SERVER_URL` | `mcpResourceServerUrl` | Public URL ending in `/mcp` |
| `MCP_ACCESS_TOKEN` | `mcpAccessToken` | Leave **empty** in OAuth mode |

If Entra puts `api://financial-mcp/mcp.tools` in `scp`, set `OAUTH_REQUIRED_SCOPES` to that full string (not only `mcp.tools`).

### 4. Configure Claude custom connector

1. **Customize** → **Connectors** → **Add custom connector**.
2. **URL:** `https://<backend-fqdn>/mcp` or Cloudflare `https://<worker>.workers.dev/mcp`.
3. **Authentication:** OAuth (not static bearer).
4. **Client ID / Client secret:** from the **client app** (step 2), not the API app.
5. **Scopes:** match Entra and `OAUTH_REQUIRED_SCOPES`.
6. Complete sign-in; Claude sends the Entra access token as `Authorization: Bearer <jwt>`.

### 5. Verify

```bash
curl -X POST "https://<your-host>/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer <entra-access-token>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

Expect **HTTP 200** with a valid token; **401** if issuer, audience, or scopes do not match server config.

### Troubleshooting

| Symptom | Check |
|---------|--------|
| Claude “Couldn't register with sign-in service” | Backend `MCP_AUTH_MODE=oauth`, real `OAUTH_ISSUER_URL`, client app redirect URIs |
| 401 after login | Token `aud` vs `OAUTH_AUDIENCE`; `scp` vs `OAUTH_REQUIRED_SCOPES` |
| Works on Azure URL but not via Worker | `WORKER_AUTH_MODE=passthrough` and backend `MCP_AUTH_MODE=oauth` |
| Want simple shared secret instead | `MCP_AUTH_MODE=static`, omit `MCP_RESOURCE_SERVER_URL`, bearer token in Claude |

---

## Connect from Claude

Once live over HTTPS: **Customize → Connectors → Add custom connector** → paste:

- Backend: `https://<azure-or-render-host>/mcp`
- Or Cloudflare proxy: `https://<worker>.workers.dev/mcp`

Claude connects from Anthropic’s cloud; the host must be on the public internet.

### Auth mode summary

| Mode | Server env | Claude connector |
|------|------------|------------------|
| **Static** | `MCP_AUTH_MODE=static`, `MCP_ACCESS_TOKEN` | Bearer / static token (same secret) |
| **OAuth** | `MCP_AUTH_MODE=oauth`, Entra vars above | OAuth + client app ID/secret |
| **None** | `ALLOW_UNAUTHENTICATED_HTTP=true` | Dev only — not for production |

Static verification:

```bash
curl -X POST "https://<your-host>/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer <MCP_ACCESS_TOKEN>" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```
