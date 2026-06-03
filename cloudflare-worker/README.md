# Cloudflare Worker MCP Proxy

This Worker proxies MCP traffic to the Python backend while enforcing bearer auth.

## Required Variables

- `MCP_BACKEND_URL` (example: `https://your-azure-or-render-host/mcp`)
- `WORKER_AUTH_MODE` (`static` or `passthrough`)
- `MCP_ACCESS_TOKEN` (required only in `static`; must match backend `MCP_ACCESS_TOKEN`)

`passthrough` mode forwards the caller's bearer token to backend unchanged, useful when backend uses OAuth JWT validation.

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
