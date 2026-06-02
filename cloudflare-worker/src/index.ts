export interface Env {
  MCP_BACKEND_URL: string;
  MCP_ACCESS_TOKEN: string;
}

function getBearerToken(value: string | null): string | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed.toLowerCase().startsWith("bearer ")) return null;
  return trimmed.slice(7).trim();
}

function unauthorized(message = "Unauthorized"): Response {
  return Response.json({ error: message }, { status: 401 });
}

function forbidden(message = "Forbidden"): Response {
  return Response.json({ error: message }, { status: 403 });
}

function validateConfig(env: Env): Response | null {
  if (!env.MCP_BACKEND_URL) {
    return Response.json(
      { error: "MCP_BACKEND_URL is not configured." },
      { status: 500 },
    );
  }
  if (!env.MCP_ACCESS_TOKEN) {
    return Response.json(
      { error: "MCP_ACCESS_TOKEN is not configured." },
      { status: 500 },
    );
  }
  return null;
}

function buildBackendUrl(requestUrl: URL, env: Env): URL {
  const backendBase = new URL(env.MCP_BACKEND_URL);
  const target = new URL(backendBase.toString());
  target.pathname = backendBase.pathname;
  target.search = requestUrl.search;
  return target;
}

function copyHeaders(request: Request, env: Env): Headers {
  const headers = new Headers();
  const passthroughHeaders = [
    "accept",
    "content-type",
    "mcp-session-id",
    "user-agent",
  ];

  for (const headerName of passthroughHeaders) {
    const value = request.headers.get(headerName);
    if (value) headers.set(headerName, value);
  }
  headers.set("authorization", `Bearer ${env.MCP_ACCESS_TOKEN}`);
  return headers;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === "/health") {
      return Response.json({ ok: true, service: "financial-mcp-cloudflare-proxy" });
    }

    if (url.pathname !== "/mcp") {
      return Response.json({ error: "Not found" }, { status: 404 });
    }

    const configError = validateConfig(env);
    if (configError) return configError;

    const incomingToken = getBearerToken(request.headers.get("authorization"));
    if (!incomingToken) return unauthorized("Missing bearer token.");
    if (incomingToken !== env.MCP_ACCESS_TOKEN) return forbidden("Invalid token.");

    const backendUrl = buildBackendUrl(url, env);
    const response = await fetch(backendUrl.toString(), {
      method: request.method,
      headers: copyHeaders(request, env),
      body: request.body,
      redirect: "manual",
    });

    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers: response.headers,
    });
  },
};
