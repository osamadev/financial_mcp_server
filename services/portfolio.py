import json
import os
import logging
from typing import Any, Dict, List

from services.market_data import normalize_ticker

logger = logging.getLogger(__name__)
# Override with a path on a mounted volume to persist across redeploys
PORTFOLIO_FILE = os.getenv(
    "PORTFOLIO_FILE", os.path.join(os.path.dirname(__file__), "user_portfolio.json")
)


def _default_portfolio() -> Dict[str, Any]:
    return {"positions": [], "alerts": {}, "schema_version": 2}


def _migrate_portfolio(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return _default_portfolio()

    positions: List[Dict[str, Any]] = []
    if isinstance(data.get("positions"), list):
        for item in data["positions"]:
            if isinstance(item, dict) and item.get("ticker"):
                try:
                    ticker = normalize_ticker(item["ticker"])
                except ValueError:
                    continue
                positions.append(
                    {
                        "ticker": ticker,
                        "quantity": float(item.get("quantity", 0) or 0),
                        "avg_cost": item.get("avg_cost"),
                    }
                )
    elif isinstance(data.get("tickers"), list):
        seen = set()
        for ticker in data["tickers"]:
            try:
                symbol = normalize_ticker(ticker)
            except ValueError:
                continue
            if symbol in seen:
                continue
            seen.add(symbol)
            positions.append({"ticker": symbol, "quantity": 0.0, "avg_cost": None})

    alerts = data.get("alerts")
    if not isinstance(alerts, dict):
        alerts = {}

    normalized = {
        "positions": positions,
        "alerts": alerts,
        "schema_version": 2,
    }
    return normalized


def _with_tickers(portfolio: Dict[str, Any]) -> Dict[str, Any]:
    output = dict(portfolio)
    output["tickers"] = [item["ticker"] for item in portfolio.get("positions", [])]
    return output


def load_portfolio() -> Dict[str, Any]:
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, "r") as f:
                data = json.load(f)
            portfolio = _migrate_portfolio(data)
            save_portfolio(portfolio)
            return _with_tickers(portfolio)
        else:
            # Create initial portfolio file if it doesn't exist
            initial_portfolio = _default_portfolio()
            save_portfolio(initial_portfolio)
            return _with_tickers(initial_portfolio)
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding portfolio file: {str(e)}")
        return _with_tickers(_default_portfolio())
    except Exception as e:
        logger.error(f"Error loading portfolio: {str(e)}")
        return _with_tickers(_default_portfolio())


def save_portfolio(data: Dict[str, Any]) -> bool:
    try:
        logger.debug(f"Attempting to save portfolio: {data}")
        if not isinstance(data, dict):
            raise ValueError("Invalid portfolio data structure")

        portfolio = _migrate_portfolio(data)
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
        
        # Write with proper formatting
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(portfolio, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        
        logger.debug("Portfolio saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving portfolio: {str(e)}")
        raise


def add_ticker(ticker: str, quantity: float = 0.0, avg_cost: float | None = None):
    try:
        symbol = normalize_ticker(ticker)
        portfolio = load_portfolio()
        positions = portfolio.get("positions", [])

        existing = next((p for p in positions if p["ticker"] == symbol), None)
        if existing:
            existing["quantity"] = float(quantity or existing.get("quantity", 0))
            if avg_cost is not None:
                existing["avg_cost"] = float(avg_cost)
        else:
            positions.append(
                {
                    "ticker": symbol,
                    "quantity": float(quantity or 0),
                    "avg_cost": float(avg_cost) if avg_cost is not None else None,
                }
            )
        portfolio["positions"] = positions
        save_portfolio(portfolio)
        return portfolio
    except Exception as e:
        logger.error(f"Error adding ticker {ticker}: {str(e)}")
        return {"error": str(e), "tickers": []}


def remove_ticker(ticker: str):
    try:
        symbol = normalize_ticker(ticker)
        portfolio = load_portfolio()
        positions = portfolio.get("positions", [])
        portfolio["positions"] = [p for p in positions if p.get("ticker") != symbol]
        portfolio.get("alerts", {}).pop(symbol, None)
        save_portfolio(portfolio)
        return portfolio
    except Exception as e:
        logger.error(f"Error removing ticker {ticker}: {str(e)}")
        return {"error": str(e), "tickers": []}


def set_price_alert(ticker: str, above: float | None = None, below: float | None = None):
    symbol = normalize_ticker(ticker)
    if above is None and below is None:
        raise ValueError("At least one threshold is required (above or below).")

    portfolio = load_portfolio()
    alerts = portfolio.get("alerts", {})
    alerts[symbol] = {
        "above": float(above) if above is not None else None,
        "below": float(below) if below is not None else None,
    }
    portfolio["alerts"] = alerts
    save_portfolio(portfolio)
    return {"ticker": symbol, "alert": alerts[symbol]}


def get_price_alerts(ticker: str | None = None):
    portfolio = load_portfolio()
    alerts = portfolio.get("alerts", {})
    if ticker:
        symbol = normalize_ticker(ticker)
        return {symbol: alerts.get(symbol)}
    return alerts
