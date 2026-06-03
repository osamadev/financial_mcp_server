# Cloudflare Worker MCP Proxy

This Worker proxies MCP traffic to the Python backend while enforcing bearer auth at the edge.

## Deploy

[![Deploy to Cloudflare](https://deploy.workers.cloudflare.com/button)](https://deploy.workers.cloudflare.com/?url=https://github.com/osamadev/financial_mcp_server/tree/main/cloudflare-worker)

Deploy the **backend** on [Azure or Render](../DEPLOY.md) first, then set Worker variables:

| Variable | Static mode | OAuth mode |
|----------|-------------|------------|
| `MCP_BACKEND_URL` | `https://<backend>/mcp` | same |
| `WORKER_AUTH_MODE` | `static` | `passthrough` |
| `MCP_ACCESS_TOKEN` | Same as backend `MCP_ACCESS_TOKEN` | not used |

OAuth (Entra) client app setup for Claude: **[`DEPLOY.md` — OAuth (Entra ID)](../DEPLOY.md#oauth-entra-id)**.

## Required variables

- `MCP_BACKEND_URL` (example: `https://your-azure-or-render-host/mcp`)
- `WORKER_AUTH_MODE` (`static` or `passthrough`)
- `MCP_ACCESS_TOKEN` (required only in `static`; must match backend `MCP_ACCESS_TOKEN`)

`passthrough` forwards the caller's bearer token to the backend unchanged (use when backend `MCP_AUTH_MODE=oauth`).

## Local dev

```bash
npm install
npm run dev
```

Copy `.dev.vars.example` to `.dev.vars`.

## CLI deploy

```bash
npm install
npm run deploy
```
