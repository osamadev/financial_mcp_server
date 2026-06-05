import json
import logging
import os
import sys
from typing import Any, Dict
from urllib.parse import parse_qs, urlencode

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response

from services.alerts import check_alerts, get_alerts
from services.context_builder import build_final_prompt
from services.fetcher import fetch_web_data
from services.intent_parser import extract_financial_entities
from services.market_data import (
    get_company_overview as market_data_company_overview,
    get_price_history as market_data_price_history,
    get_stock_news as market_data_stock_news,
    get_stock_quote as market_data_stock_quote,
)
from services.market_summary import get_market_wrap
from services.portfolio import (
    add_ticker,
    get_price_alerts,
    load_portfolio,
    remove_ticker,
    set_price_alert,
)
from services.security import OidcJwtVerifier, StaticTokenVerifier
from services.summarizer import summarize_articles

load_dotenv()

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
if LOG_LEVEL not in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
    LOG_LEVEL = "INFO"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr), logging.FileHandler("financial_mcp.log")],
)
logger = logging.getLogger(__name__)

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
MCP_AUTH_MODE = os.getenv("MCP_AUTH_MODE", "static").lower()
MCP_ACCESS_TOKEN = os.getenv("MCP_ACCESS_TOKEN", "").strip()
OAUTH_ISSUER_URL = os.getenv("OAUTH_ISSUER_URL", "").strip()
OAUTH_JWKS_URL = os.getenv("OAUTH_JWKS_URL", "").strip()
OAUTH_AUDIENCE = os.getenv("OAUTH_AUDIENCE", "").strip()
OAUTH_AUDIENCES = [aud.strip() for aud in OAUTH_AUDIENCE.split(",") if aud.strip()]


def _split_env_scopes(raw_value: str) -> list[str]:
    return [scope for scope in raw_value.replace(",", " ").split() if scope]


OAUTH_REQUIRED_SCOPES = _split_env_scopes(
    os.getenv("OAUTH_REQUIRED_SCOPES", "mcp.tools")
)
OAUTH_SCOPES_SUPPORTED = _split_env_scopes(os.getenv("OAUTH_SCOPES_SUPPORTED", ""))
OAUTH_ISSUER_URLS = [
    issuer for issuer in os.getenv("OAUTH_ISSUER_URLS", "").replace(",", " ").split() if issuer
]
MCP_RESOURCE_SERVER_URL = os.getenv("MCP_RESOURCE_SERVER_URL", "").strip()
OAUTH_BROKER_ENABLED = (
    os.getenv("OAUTH_BROKER_ENABLED", "false").lower() in ("1", "true", "yes")
)
OAUTH_BROKER_ISSUER_URL = os.getenv("OAUTH_BROKER_ISSUER_URL", "").strip()
OAUTH_BROKER_CLIENT_ID = os.getenv("OAUTH_BROKER_CLIENT_ID", "").strip()
OAUTH_BROKER_CLIENT_SECRET = os.getenv("OAUTH_BROKER_CLIENT_SECRET", "").strip()
OAUTH_BROKER_SCOPE = os.getenv("OAUTH_BROKER_SCOPE", "").strip()
ALLOW_UNAUTHENTICATED_HTTP = (
    os.getenv("ALLOW_UNAUTHENTICATED_HTTP", "false").lower() in ("1", "true", "yes")
)


def resolve_transport() -> str:
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    if transport in ("http", "streamable-http", "streamable_http"):
        return "streamable-http"
    if transport in ("stdio", "sse"):
        return transport
    return "stdio"


def _resolve_supported_scopes() -> list[str]:
    # scopes_supported in protected-resource metadata should reflect what the IdP expects
    # during authorize/token requests. It can differ from strict token validation scopes.
    if OAUTH_SCOPES_SUPPORTED:
        return OAUTH_SCOPES_SUPPORTED

    supported = list(OAUTH_REQUIRED_SCOPES)
    api_audiences = [aud for aud in OAUTH_AUDIENCES if aud.startswith("api://")]
    for required_scope in OAUTH_REQUIRED_SCOPES:
        if "://" in required_scope:
            continue
        for audience in api_audiences:
            full_scope = f"{audience.rstrip('/')}/{required_scope}"
            if full_scope not in supported:
                supported.append(full_scope)
    return supported


OAUTH_METADATA_SCOPES = _resolve_supported_scopes()


def _public_origin(url: str) -> str:
    if not url:
        return ""
    parts = url.split("/")
    if len(parts) >= 3:
        return f"{parts[0]}//{parts[2]}"
    return url.rstrip("/")


def _broker_issuer_url() -> str:
    return (OAUTH_BROKER_ISSUER_URL or _public_origin(MCP_RESOURCE_SERVER_URL)).rstrip("/")


def _entra_oauth_base_url() -> str:
    issuer = OAUTH_ISSUER_URL.rstrip("/")
    if issuer.endswith("/v2.0"):
        return issuer[: -len("/v2.0")]
    return issuer


def _broker_scope() -> str:
    if OAUTH_BROKER_SCOPE:
        return OAUTH_BROKER_SCOPE
    if OAUTH_METADATA_SCOPES:
        return OAUTH_METADATA_SCOPES[-1]
    if OAUTH_REQUIRED_SCOPES:
        return OAUTH_REQUIRED_SCOPES[0]
    return "mcp.tools"


def _build_auth():
    if MCP_AUTH_MODE == "none":
        return None, None

    if MCP_AUTH_MODE == "static":
        if not MCP_ACCESS_TOKEN:
            raise RuntimeError("MCP_ACCESS_TOKEN is required when MCP_AUTH_MODE=static.")
        # FastMCP requires AuthSettings when token_verifier is set. Do not set
        # resource_server_url unless MCP_RESOURCE_SERVER_URL is explicitly provided —
        # that URL drives /.well-known/oauth-protected-resource and makes Claude expect OAuth.
        static_resource_url = MCP_RESOURCE_SERVER_URL or None
        auth_settings = AuthSettings(
            issuer_url=(static_resource_url or f"http://{HOST}:{PORT}"),
            resource_server_url=static_resource_url,
            required_scopes=OAUTH_METADATA_SCOPES or None,
        )
        return StaticTokenVerifier(MCP_ACCESS_TOKEN), auth_settings

    if MCP_AUTH_MODE == "oauth":
        if not OAUTH_ISSUER_URL:
            raise RuntimeError("OAUTH_ISSUER_URL is required when MCP_AUTH_MODE=oauth.")
        if not OAUTH_AUDIENCE:
            raise RuntimeError("OAUTH_AUDIENCE is required when MCP_AUTH_MODE=oauth.")
        if not MCP_RESOURCE_SERVER_URL:
            raise RuntimeError("MCP_RESOURCE_SERVER_URL is required when MCP_AUTH_MODE=oauth.")

        verifier = OidcJwtVerifier(
            issuer_url=OAUTH_ISSUER_URL,
            issuer_urls=OAUTH_ISSUER_URLS,
            audience=OAUTH_AUDIENCE,
            required_scopes=OAUTH_REQUIRED_SCOPES,
            jwks_url=(OAUTH_JWKS_URL or None),
        )
        auth_settings = AuthSettings(
            issuer_url=(_broker_issuer_url() if OAUTH_BROKER_ENABLED else OAUTH_ISSUER_URL),
            resource_server_url=MCP_RESOURCE_SERVER_URL,
            required_scopes=OAUTH_METADATA_SCOPES,
        )
        return verifier, auth_settings

    raise RuntimeError(
        f"Unsupported MCP_AUTH_MODE={MCP_AUTH_MODE}. Use static, oauth, or none."
    )


TOKEN_VERIFIER, AUTH_SETTINGS = _build_auth()

mcp = FastMCP(
    "Financial-MCP-Server",
    host=HOST,
    port=PORT,
    token_verifier=TOKEN_VERIFIER,
    auth=AUTH_SETTINGS,
    log_level=LOG_LEVEL,
    stateless_http=True,
)


if OAUTH_BROKER_ENABLED:
    @mcp.custom_route("/.well-known/oauth-authorization-server", methods=["GET", "OPTIONS"])
    async def oauth_authorization_server_metadata(request: Request) -> Response:
        issuer = _broker_issuer_url()
        if request.method == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "GET, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, MCP-Protocol-Version",
                },
            )
        return JSONResponse(
            {
                "issuer": issuer,
                "authorization_endpoint": f"{issuer}/authorize",
                "token_endpoint": f"{issuer}/token",
                "registration_endpoint": f"{issuer}/register",
                "scopes_supported": OAUTH_METADATA_SCOPES or [_broker_scope()],
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "token_endpoint_auth_methods_supported": [
                    "client_secret_post",
                    "client_secret_basic",
                    "none",
                ],
                "code_challenge_methods_supported": ["S256", "plain"],
            },
            headers={"Access-Control-Allow-Origin": "*"},
        )

    @mcp.custom_route("/register", methods=["POST", "OPTIONS"])
    async def oauth_register(request: Request) -> Response:
        if request.method == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, MCP-Protocol-Version",
                },
            )

        try:
            payload = await request.json()
        except Exception:
            payload = {}

        client_id = OAUTH_BROKER_CLIENT_ID or payload.get("client_id")
        if not client_id:
            return JSONResponse(
                {"error": "invalid_client_metadata", "error_description": "OAUTH_BROKER_CLIENT_ID is required for dynamic registration."},
                status_code=400,
            )

        response_payload = {
            "client_id": client_id,
            "client_id_issued_at": 0,
            "redirect_uris": payload.get("redirect_uris", []),
            "grant_types": payload.get("grant_types", ["authorization_code", "refresh_token"]),
            "response_types": payload.get("response_types", ["code"]),
            "scope": payload.get("scope") or _broker_scope(),
            "token_endpoint_auth_method": payload.get(
                "token_endpoint_auth_method",
                "client_secret_post" if OAUTH_BROKER_CLIENT_SECRET else "none",
            ),
        }
        if OAUTH_BROKER_CLIENT_SECRET:
            response_payload["client_secret"] = OAUTH_BROKER_CLIENT_SECRET
            response_payload["client_secret_expires_at"] = 0

        return JSONResponse(response_payload, status_code=201, headers={"Access-Control-Allow-Origin": "*"})

    @mcp.custom_route("/authorize", methods=["GET"])
    async def oauth_authorize(request: Request) -> Response:
        params = dict(request.query_params)
        client_id = OAUTH_BROKER_CLIENT_ID or params.get("client_id")
        if not client_id:
            return JSONResponse(
                {"error": "invalid_request", "error_description": "Missing client_id."},
                status_code=400,
            )

        forwarded = {
            key: value
            for key, value in params.items()
            if key not in {"resource", "scope", "client_id"}
        }
        forwarded["client_id"] = client_id
        forwarded["scope"] = _broker_scope()
        forwarded.setdefault("response_type", "code")
        forwarded.setdefault("response_mode", "query")

        authorize_url = f"{_entra_oauth_base_url()}/oauth2/v2.0/authorize?{urlencode(forwarded)}"
        return RedirectResponse(authorize_url, status_code=302)

    @mcp.custom_route("/token", methods=["POST", "OPTIONS"])
    async def oauth_token(request: Request) -> Response:
        if request.method == "OPTIONS":
            return Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Methods": "POST, OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization, MCP-Protocol-Version",
                },
            )

        raw_body = (await request.body()).decode()
        parsed = parse_qs(raw_body, keep_blank_values=True)
        form = {key: values[-1] for key, values in parsed.items() if values}
        form.pop("resource", None)
        form.pop("scope", None)
        form["client_id"] = OAUTH_BROKER_CLIENT_ID or form.get("client_id", "")
        if OAUTH_BROKER_CLIENT_SECRET and not form.get("client_secret"):
            form["client_secret"] = OAUTH_BROKER_CLIENT_SECRET

        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                f"{_entra_oauth_base_url()}/oauth2/v2.0/token",
                data=form,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        return Response(
            content=response.content,
            status_code=response.status_code,
            media_type=response.headers.get("content-type", "application/json"),
            headers={"Access-Control-Allow-Origin": "*"},
        )


def _invalidate_portfolio_cache() -> None:
    if hasattr(mcp, "_resource_cache"):
        mcp._resource_cache.pop("portfolio://data", None)


def _enrich_portfolio(base_portfolio: Dict[str, Any]) -> Dict[str, Any]:
    positions = base_portfolio.get("positions", [])
    enriched = []
    total_value = 0.0

    for position in positions:
        ticker = position.get("ticker")
        quantity = float(position.get("quantity", 0) or 0)
        quote = market_data_stock_quote(ticker)
        price = quote.get("price")
        market_value = (price or 0.0) * quantity if quantity else None
        if market_value:
            total_value += market_value

        enriched.append(
            {
                **position,
                "quote": quote,
                "market_value": market_value,
            }
        )

    return {
        **base_portfolio,
        "positions": enriched,
        "summary": {
            "position_count": len(enriched),
            "portfolio_market_value": total_value,
        },
    }


@mcp.tool()
def get_stock_quote(ticker: str) -> Dict[str, Any]:
    return market_data_stock_quote(ticker)


@mcp.tool()
def get_price_history(ticker: str, period: str = "1mo", interval: str = "1d") -> Dict[str, Any]:
    return market_data_price_history(ticker=ticker, period=period, interval=interval)


@mcp.tool()
def get_company_overview(ticker: str) -> Dict[str, Any]:
    return market_data_company_overview(ticker=ticker)


@mcp.tool()
async def get_stock_news(ticker_or_query: str, max_results: int = 5) -> Dict[str, Any]:
    return await market_data_stock_news(ticker_or_query=ticker_or_query, max_results=max_results)


@mcp.tool()
def market_summary() -> Dict[str, Any]:
    return get_market_wrap()


@mcp.tool()
def get_portfolio() -> Dict[str, Any]:
    return _enrich_portfolio(load_portfolio())


@mcp.tool()
def add_stock(ticker: str, quantity: float = 0.0, avg_cost: float | None = None) -> Dict[str, Any]:
    result = add_ticker(ticker=ticker, quantity=quantity, avg_cost=avg_cost)
    _invalidate_portfolio_cache()
    return _enrich_portfolio(result)


@mcp.tool()
def remove_stock(ticker: str) -> Dict[str, Any]:
    result = remove_ticker(ticker=ticker)
    _invalidate_portfolio_cache()
    return _enrich_portfolio(result)


@mcp.tool()
def set_stock_alert(
    ticker: str, above: float | None = None, below: float | None = None
) -> Dict[str, Any]:
    result = set_price_alert(ticker=ticker, above=above, below=below)
    _invalidate_portfolio_cache()
    return result


@mcp.tool()
async def get_portfolio_alerts(ticker: str | None = None) -> Dict[str, Any]:
    if ticker:
        return await check_alerts(tickers=[ticker], send_notifications=False)
    return await check_alerts(send_notifications=False)


@mcp.tool()
async def financial_context(query: str) -> Dict[str, Any]:
    if not query or not isinstance(query, str):
        return {
            "error": "Invalid query input",
            "query": str(query),
            "tickers": [],
            "keywords": [],
            "context": [],
            "final_prompt": "",
        }

    parsed = extract_financial_entities(query)
    articles = await fetch_web_data(query, tickers=parsed["tickers"])
    if not articles:
        return {
            "query": query,
            "tickers": parsed["tickers"],
            "keywords": parsed["keywords"],
            "context": [],
            "final_prompt": "No recent market data found for the query.",
        }

    summaries = await summarize_articles(articles)
    final_prompt = build_final_prompt(query, summaries)
    return {
        "query": query,
        "tickers": parsed["tickers"],
        "keywords": parsed["keywords"],
        "context": summaries,
        "final_prompt": final_prompt,
        "notes": [
            "financial_context depends on SERPAPI_API_KEY.",
            "Summarization backend is controlled by SUMMARIZER_PROVIDER (ollama|openai|auto).",
        ],
    }


@mcp.tool()
async def portfolio_alerts(random_string: str = "all") -> Dict[str, Any]:
    if random_string and random_string.lower() != "all":
        return await check_alerts(tickers=[random_string], send_notifications=False)
    return await check_alerts(send_notifications=False)


@mcp.tool()
async def check_stock_alerts(ticker: str) -> Dict[str, Any]:
    return await check_alerts(tickers=[ticker], send_notifications=False)


@mcp.tool()
async def single_stock_alert(ticker: str) -> Dict[str, Any]:
    return await check_alerts(tickers=[ticker], send_notifications=False)


@mcp.resource("financial://market-summary")
def market_summary_resource() -> Dict[str, Any]:
    return get_market_wrap()


@mcp.resource("portfolio://data")
def portfolio_resource() -> Dict[str, Any]:
    return _enrich_portfolio(load_portfolio())


@mcp.resource("alerts://rules")
def alert_rules_resource() -> Dict[str, Any]:
    return {"alerts": get_price_alerts()}


if __name__ == "__main__":
    transport = resolve_transport()
    if transport == "streamable-http":
        if MCP_AUTH_MODE == "none" and not ALLOW_UNAUTHENTICATED_HTTP:
            raise RuntimeError(
                "MCP_AUTH_MODE=none is only allowed when ALLOW_UNAUTHENTICATED_HTTP=true."
            )
        if MCP_AUTH_MODE == "static" and not MCP_ACCESS_TOKEN:
            raise RuntimeError("MCP_ACCESS_TOKEN is required when MCP_AUTH_MODE=static.")
        if MCP_AUTH_MODE == "oauth" and (
            not OAUTH_ISSUER_URL or not OAUTH_AUDIENCE or not MCP_RESOURCE_SERVER_URL
        ):
            raise RuntimeError(
                "OAuth mode requires OAUTH_ISSUER_URL, OAUTH_AUDIENCE, and MCP_RESOURCE_SERVER_URL."
            )

    logger.info(
        f"Starting Financial-MCP-Server with transport={transport}, auth_mode={MCP_AUTH_MODE} on {HOST}:{PORT}"
    )
    try:
        mcp.run(transport=transport)
    except json.JSONDecodeError as je:
        logger.error(f"JSON decode error: {str(je)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Failed to start MCP server: {str(e)}", exc_info=True)
        raise