# Cloudflare Worker MCP Proxy

This Worker proxies MCP traffic to the Python backend while enforcing bearer auth.

## Required Variables

- `MCP_BACKEND_URL` (example: `https://your-azure-or-render-host/mcp`)
- `MCP_ACCESS_TOKEN` (must match backend `MCP_ACCESS_TOKEN`)

## Local Dev

```bash
npm install
npm run dev
```

Set local variables in `.dev.vars` (copy from `.dev.vars.example`).

## Deploy

```bash
npm install
npm run deploy
```
