import logging
import os
from typing import Any, Dict, Iterable, List

from services.market_data import get_stock_quote, normalize_ticker
from services.portfolio import get_price_alerts, load_portfolio
from services.telegram_alerts import send_telegram_alert

logger = logging.getLogger(__name__)


def _is_telegram_enabled() -> bool:
    enabled = os.getenv("ENABLE_TELEGRAM_ALERTS", "false").lower()
    return enabled in ("1", "true", "yes")


def _portfolio_tickers() -> List[str]:
    portfolio = load_portfolio()
    positions = portfolio.get("positions", [])
    return [item["ticker"] for item in positions if item.get("ticker")]


def _evaluate_thresholds(
    ticker: str, quote: Dict[str, Any], rules: Dict[str, Any]
) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    price = quote.get("price")
    if price is None:
        return events

    above = rules.get("above")
    below = rules.get("below")
    if above is not None and price >= float(above):
        events.append(
            {
                "ticker": ticker,
                "price": price,
                "threshold_type": "above",
                "threshold_value": float(above),
                "message": f"{ticker} crossed above {above} (price={price})",
            }
        )
    if below is not None and price <= float(below):
        events.append(
            {
                "ticker": ticker,
                "price": price,
                "threshold_type": "below",
                "threshold_value": float(below),
                "message": f"{ticker} crossed below {below} (price={price})",
            }
        )
    return events


async def get_alerts(ticker: str | None = None) -> Dict[str, Any]:
    alerts = get_price_alerts(ticker=ticker)
    if ticker:
        symbol = normalize_ticker(ticker)
        return {"alerts": {symbol: alerts.get(symbol)}}
    return {"alerts": alerts}


async def check_alerts(
    tickers: Iterable[str] | None = None, send_notifications: bool = False
) -> Dict[str, Any]:
    alerts_map = get_price_alerts()
    if not alerts_map:
        return {"events": [], "checked_tickers": [], "reason": "No alert rules configured."}

    if tickers:
        checked_tickers = [normalize_ticker(t) for t in tickers]
    else:
        checked_tickers = [t for t in _portfolio_tickers() if t in alerts_map]
        if not checked_tickers:
            checked_tickers = list(alerts_map.keys())

    events: List[Dict[str, Any]] = []
    for symbol in checked_tickers:
        rules = alerts_map.get(symbol)
        if not isinstance(rules, dict):
            continue
        quote = get_stock_quote(symbol)
        events.extend(_evaluate_thresholds(symbol, quote, rules))

    if send_notifications and events and _is_telegram_enabled():
        summary_lines = ["Price alerts triggered:"]
        summary_lines.extend([f"- {event['message']}" for event in events])
        try:
            await send_telegram_alert("\n".join(summary_lines))
        except Exception as exc:
            logger.error(f"Failed to send Telegram alert: {exc}")

    return {"events": events, "checked_tickers": checked_tickers}


async def check_trading_opportunities(ticker: str) -> Dict[str, Any]:
    symbol = normalize_ticker(ticker)
    quote = get_stock_quote(symbol)
    rules = get_price_alerts(symbol).get(symbol) or {}
    events = _evaluate_thresholds(symbol, quote, rules)
    if not events:
        return {
            "ticker": symbol,
            "opportunities": [],
            "message": "No threshold opportunities currently triggered.",
        }
    return {"ticker": symbol, "opportunities": events}


async def send_trading_alert(ticker: str) -> Dict[str, Any]:
    result = await check_trading_opportunities(ticker)
    opportunities = result.get("opportunities", [])
    if opportunities and _is_telegram_enabled():
        await send_telegram_alert(
            "\n".join(["Trading opportunities:"] + [f"- {x['message']}" for x in opportunities])
        )
    return result
