import yfinance as yf
from services.telegram_alerts import send_telegram_alert
import logging
import json
from pathlib import Path

logger = logging.getLogger(__name__)

def load_tech_alerts_config():
    """Load tech alerts configuration from JSON file."""
    try:
        config_path = Path(__file__).parent.parent / 'config' / 'tech_alerts_config.json'
        with open(config_path, 'r') as f:
            config = json.load(f)
        
        # Flatten the sector-based structure into a simple ticker-rules dictionary
        alerts = {}
        for sector in config.values():
            for ticker, details in sector.items():
                alerts[ticker] = {
                    "above": details["above"],
                    "below": details["below"],
                    "description": details["description"]
                }
        return alerts
    except Exception as e:
        logger.error(f"Error loading tech alerts configuration: {str(e)}")
        return {}

async def check_tech_alerts():
    """Check alerts for tech stocks only."""
    triggered = []
    tech_summary = []
    try:
        alerts_config = load_tech_alerts_config()
        if not alerts_config:
            logger.error("No tech alerts configuration loaded")
            return ["⚠️ Error: Could not load tech alerts configuration"]

        for ticker, rules in alerts_config.items():
            try:
                data = yf.Ticker(ticker)
                price = data.info.get("regularMarketPrice")
                if price:
                    logger.info(f"Current price for {ticker}: ${price}")
                    description = rules.get("description", "")
                    
                    # Add to tech summary
                    tech_summary.append(f"{ticker}: ${price} ({description})")
                    
                    if "above" in rules and price > rules["above"]:
                        msg = f"📈 {ticker} is above ${rules['above']} (${price}) - {description}"
                        triggered.append(msg)
                    if "below" in rules and price < rules["below"]:
                        msg = f"🔔 Buying Opportunity: {ticker} at ${price}\n" \
                             f"Below buy threshold of ${rules['below']}\n" \
                             f"Description: {description}"
                        triggered.append(msg)
                else:
                    logger.warning(f"Could not get price for {ticker}")
            except Exception as e:
                logger.error(f"Error checking alerts for {ticker}: {str(e)}")
                triggered.append(f"⚠️ Error checking {ticker}: {str(e)}")
                
        if triggered:
            # Add summary header
            summary = "🚨 Tech Stocks Alert Summary:\n\n" + "\n".join(triggered)
            try:
                await send_telegram_alert(summary)
                logger.info("Tech alerts sent successfully")
            except Exception as e:
                logger.error(f"Error sending tech alerts: {str(e)}")
                
        return triggered
    except Exception as e:
        logger.error(f"Unexpected error in check_tech_alerts: {str(e)}")
        return [f"⚠️ System error: {str(e)}"]

if __name__ == "__main__":
    import asyncio
    logging.basicConfig(level=logging.INFO)
    asyncio.run(check_tech_alerts()) 