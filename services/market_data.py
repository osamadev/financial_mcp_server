from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any, Dict, List

import yfinance as yf

from services.fetcher import fetch_web_data

TICKER_PATTERN = re.compile(r"^[A-Z][A-Z0-9\.\-]{0,9}$")


def normalize_ticker(ticker: str) -> str:
    if not isinstance(ticker, str):
        raise ValueError("Ticker must be a string.")
    symbol = ticker.strip().upper()
    if not symbol:
        raise ValueError("Ticker cannot be empty.")
    if not TICKER_PATTERN.fullmatch(symbol):
        raise ValueError(
            "Ticker must be alphanumeric and may include '.' or '-'."
        )
    return symbol


def _to_number(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_stock_quote(ticker: str) -> Dict[str, Any]:
    symbol = normalize_ticker(ticker)
    info = yf.Ticker(symbol).info or {}

    price = _to_number(info.get("regularMarketPrice"))
    previous_close = _to_number(info.get("regularMarketPreviousClose"))
    absolute_change = None
    percent_change = _to_number(info.get("regularMarketChangePercent"))
    if price is not None and previous_close is not None:
        absolute_change = price - previous_close

    return {
        "ticker": symbol,
        "short_name": info.get("shortName"),
        "price": price,
        "previous_close": previous_close,
        "change": absolute_change,
        "change_percent": percent_change,
        "currency": info.get("currency"),
        "exchange": info.get("exchange"),
        "volume": _to_number(info.get("volume")),
        "market_cap": _to_number(info.get("marketCap")),
        "timestamp": _utc_now_iso(),
    }


def get_company_overview(ticker: str) -> Dict[str, Any]:
    symbol = normalize_ticker(ticker)
    info = yf.Ticker(symbol).info or {}

    return {
        "ticker": symbol,
        "short_name": info.get("shortName"),
        "long_name": info.get("longName"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "country": info.get("country"),
        "website": info.get("website"),
        "summary": info.get("longBusinessSummary"),
        "full_time_employees": info.get("fullTimeEmployees"),
        "market_cap": _to_number(info.get("marketCap")),
        "trailing_pe": _to_number(info.get("trailingPE")),
        "forward_pe": _to_number(info.get("forwardPE")),
        "dividend_yield": _to_number(info.get("dividendYield")),
        "beta": _to_number(info.get("beta")),
        "fifty_two_week_high": _to_number(info.get("fiftyTwoWeekHigh")),
        "fifty_two_week_low": _to_number(info.get("fiftyTwoWeekLow")),
    }


def get_price_history(
    ticker: str, period: str = "1mo", interval: str = "1d"
) -> Dict[str, Any]:
    symbol = normalize_ticker(ticker)
    history = yf.Ticker(symbol).history(period=period, interval=interval)
    points: List[Dict[str, Any]] = []

    if history is not None and not history.empty:
        for index, row in history.iterrows():
            timestamp = (
                index.to_pydatetime().replace(tzinfo=timezone.utc).isoformat()
                if hasattr(index, "to_pydatetime")
                else str(index)
            )
            points.append(
                {
                    "timestamp": timestamp,
                    "open": _to_number(row.get("Open")),
                    "high": _to_number(row.get("High")),
                    "low": _to_number(row.get("Low")),
                    "close": _to_number(row.get("Close")),
                    "volume": _to_number(row.get("Volume")),
                }
            )

    return {
        "ticker": symbol,
        "period": period,
        "interval": interval,
        "points": points,
        "point_count": len(points),
    }


async def get_stock_news(ticker_or_query: str, max_results: int = 5) -> Dict[str, Any]:
    query = ticker_or_query.strip() if isinstance(ticker_or_query, str) else ""
    if not query:
        raise ValueError("ticker_or_query is required.")

    articles = await fetch_web_data(query=query, tickers=[], max_results=max_results)
    return {
        "query": query,
        "count": len(articles),
        "articles": articles,
    }
