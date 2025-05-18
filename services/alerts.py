import yfinance as yf
from services.telegram_alerts import send_telegram_alert
import logging
import json
import os
from pathlib import Path

logger = logging.getLogger(__name__)

def load_alerts_config():
    """Load alerts configuration from JSON file."""
    try:
        config_path = Path(__file__).parent.parent / 'config' / 'alerts_config.json'
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Flatten the sector-based structure into a simple ticker-rules dictionary
        alerts = {}
        for sector in config.values():
            for ticker, details in sector.items():
                # Copy all alert parameters
                alerts[ticker] = details.copy()
        return alerts
    except Exception as e:
        logger.error(f"Error loading alerts configuration: {str(e)}")
        return {}

async def check_alerts(tickers=None):
    """
    Check alerts for stocks with focus on trading signals.
    Args:
        tickers (list): Optional list of ticker symbols to check. If None, checks all stocks.
    """
    triggered = []
    try:
        alerts_config = load_alerts_config()
        if not alerts_config:
            logger.error("No alerts configuration loaded")
            return ["⚠️ Error: Could not load alerts configuration"]

        # Filter tickers if specific ones are requested
        check_tickers = tickers if tickers else alerts_config.keys()
        
        for ticker in check_tickers:
            try:
                if ticker not in alerts_config:
                    if tickers:  # Only show error if specifically requested
                        triggered.append(f"⚠️ No configuration found for {ticker}")
                    continue

                rules = alerts_config[ticker]
                data = yf.Ticker(ticker)
                price = data.info.get("regularMarketPrice")
                description = rules.get("description", "")

                if price:
                    logger.info(f"Current price for {ticker}: ${price}")
                    
                    # Strong buy signal
                    if "strong_buy" in rules and price <= rules["strong_buy"]:
                        msg = f"🟢 Strong Buy Signal: {ticker} at ${price}\n" \
                             f"• Price at/below strong buy level ${rules['strong_buy']}"
                        if description:
                            msg += f"\nNote: {description}"
                        triggered.append(msg)
                    # Regular buy signal
                    elif "below" in rules and price < rules["below"]:
                        msg = f"🟢 Buy Signal: {ticker} at ${price}\n" \
                             f"• Price below buy threshold ${rules['below']}"
                        if description:
                            msg += f"\nNote: {description}"
                        triggered.append(msg)
                    # Strong sell signal
                    elif "strong_sell" in rules and price >= rules["strong_sell"]:
                        msg = f"🔴 Strong Sell Signal: {ticker} at ${price}\n" \
                             f"• Price at/above strong sell level ${rules['strong_sell']}"
                        if description:
                            msg += f"\nNote: {description}"
                        triggered.append(msg)
                    # Regular sell signal
                    elif "above" in rules and price > rules["above"]:
                        msg = f"🔴 Sell Signal: {ticker} at ${price}\n" \
                             f"• Price above sell threshold ${rules['above']}"
                        if description:
                            msg += f"\nNote: {description}"
                        triggered.append(msg)
                    # No signals but ticker was specifically requested
                    elif tickers:
                        msg = f"ℹ️ {ticker} at ${price} - No trading signals triggered"
                        if description:
                            msg += f"\nNote: {description}"
                        triggered.append(msg)

            except Exception as e:
                logger.error(f"Error checking alerts for {ticker}: {str(e)}")
                if tickers:  # Only show errors for specifically requested tickers
                    triggered.append(f"⚠️ Error checking {ticker}: {str(e)}")

        if triggered:
            header = "💰 Trading Signals Alert"
            if tickers:
                header += f" for {', '.join(tickers)}"
            summary = f"{header}:\n\n" + "\n\n".join(triggered)
            try:
                await send_telegram_alert(summary)
                logger.info("Trading signals sent successfully")
            except Exception as e:
                logger.error(f"Error sending alerts: {str(e)}")

        return triggered
    except Exception as e:
        logger.error(f"Unexpected error in check_alerts: {str(e)}")
        return [f"⚠️ System error: {str(e)}"]

async def check_trading_opportunities(ticker):
    """
    Check for buying and selling opportunities for a specific stock.
    Args:
        ticker (str): The stock ticker to check
    Returns:
        list: List of trading opportunities
    """
    try:
        alerts_config = load_alerts_config()
        if not alerts_config or ticker.upper() not in alerts_config:
            return [f"⚠️ No configuration found for {ticker}"]

        rules = alerts_config[ticker.upper()]
        data = yf.Ticker(ticker)
        ticker_info = data.info
        
        if not ticker_info:
            return [f"⚠️ Could not get data for {ticker}"]

        price = ticker_info.get("regularMarketPrice")
        if not price:
            return [f"⚠️ Could not get current price for {ticker}"]

        opportunities = []
        description = rules.get("description", "")

        # Check for buying opportunities
        if price <= rules.get("strong_buy", float('inf')):
            opportunities.append(f"🟢 Strong Buy Signal for {ticker} at ${price}")
            opportunities.append(f"• Price at/below strong buy level ${rules['strong_buy']}")
        elif price <= rules.get("below", float('inf')):
            opportunities.append(f"🟢 Buy Signal for {ticker} at ${price}")
            opportunities.append(f"• Price below buy threshold ${rules['below']}")

        # Check for selling opportunities
        if price >= rules.get("strong_sell", float('-inf')):
            opportunities.append(f"🔴 Strong Sell Signal for {ticker} at ${price}")
            opportunities.append(f"• Price at/above strong sell level ${rules['strong_sell']}")
        elif price >= rules.get("above", float('-inf')):
            opportunities.append(f"🔴 Sell Signal for {ticker} at ${price}")
            opportunities.append(f"• Price above sell threshold ${rules['above']}")

        # Check support/resistance levels
        if "support_levels" in rules:
            for level in rules["support_levels"]:
                if abs(price - level) <= (level * 0.01):  # Within 1% of support
                    opportunities.append(f"📊 Near support level ${level} (potential buy zone)")

        if "resistance_levels" in rules:
            for level in rules["resistance_levels"]:
                if abs(price - level) <= (level * 0.01):  # Within 1% of resistance
                    opportunities.append(f"📊 Near resistance level ${level} (potential sell zone)")

        if opportunities:
            if description:
                opportunities.append(f"\nNote: {description}")
        else:
            opportunities = [f"ℹ️ No immediate trading opportunities for {ticker} at ${price}"]

        return opportunities

    except Exception as e:
        logger.error(f"Error checking trading opportunities for {ticker}: {str(e)}")
        return [f"⚠️ Error checking {ticker}: {str(e)}"]

async def send_trading_alert(ticker):
    """
    Send trading opportunities alert for a specific stock.
    Args:
        ticker (str): The stock ticker to check
    """
    try:
        opportunities = await check_trading_opportunities(ticker)
        if opportunities:
            summary = f"💰 Trading Opportunities for {ticker}:\n\n" + "\n".join(opportunities)
            await send_telegram_alert(summary)
            return opportunities
    except Exception as e:
        logger.error(f"Error sending trading alert for {ticker}: {str(e)}")
        return [f"⚠️ Error: {str(e)}"]
