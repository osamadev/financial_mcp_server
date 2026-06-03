import json
import logging
import os
import sys
from typing import Any, Dict

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.auth.settings import AuthSettings

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
OAUTH_REQUIRED_SCOPES = [
    scope for scope in os.getenv("OAUTH_REQUIRED_SCOPES", "mcp.tools").split() if scope
]
MCP_RESOURCE_SERVER_URL = os.getenv("MCP_RESOURCE_SERVER_URL", "").strip()
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
            required_scopes=OAUTH_REQUIRED_SCOPES or None,
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
            audience=OAUTH_AUDIENCE,
            required_scopes=OAUTH_REQUIRED_SCOPES,
            jwks_url=(OAUTH_JWKS_URL or None),
        )
        auth_settings = AuthSettings(
            issuer_url=OAUTH_ISSUER_URL,
            resource_server_url=MCP_RESOURCE_SERVER_URL,
            required_scopes=OAUTH_REQUIRED_SCOPES,
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