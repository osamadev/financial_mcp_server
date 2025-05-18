import json
import os
import logging

logger = logging.getLogger(__name__)
PORTFOLIO_FILE = os.path.join(os.path.dirname(__file__), "user_portfolio.json")

def load_portfolio():
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
        else:
            # Create initial portfolio file if it doesn't exist
            initial_portfolio = {"tickers": []}
            with open(PORTFOLIO_FILE, "w") as f:
                json.dump(initial_portfolio, f, indent=4)
            return initial_portfolio
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding portfolio file: {str(e)}")
        return {"tickers": []}
    except Exception as e:
        logger.error(f"Error loading portfolio: {str(e)}")
        return {"tickers": []}

def save_portfolio(data):
    try:
        logger.debug(f"Attempting to save portfolio: {data}")
        # Ensure the data has the correct structure
        if not isinstance(data, dict) or "tickers" not in data:
            raise ValueError("Invalid portfolio data structure")
        
        # Ensure the directory exists
        os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
        
        # Write with proper formatting
        with open(PORTFOLIO_FILE, "w") as f:
            json.dump(data, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        
        logger.debug("Portfolio saved successfully")
        return True
    except Exception as e:
        logger.error(f"Error saving portfolio: {str(e)}")
        raise

def add_ticker(ticker: str):
    try:
        if not isinstance(ticker, str):
            raise ValueError("Ticker must be a string")
            
        portfolio = load_portfolio()
        if ticker.upper() not in portfolio["tickers"]:
            portfolio["tickers"].append(ticker.upper())
            save_portfolio(portfolio)
        return portfolio
    except Exception as e:
        logger.error(f"Error adding ticker {ticker}: {str(e)}")
        return {"error": str(e), "tickers": []}

def remove_ticker(ticker: str):
    try:
        if not isinstance(ticker, str):
            raise ValueError("Ticker must be a string")
            
        portfolio = load_portfolio()
        if ticker.upper() in portfolio["tickers"]:
            portfolio["tickers"].remove(ticker.upper())
            save_portfolio(portfolio)
        return portfolio
    except Exception as e:
        logger.error(f"Error removing ticker {ticker}: {str(e)}")
        return {"error": str(e), "tickers": []}
