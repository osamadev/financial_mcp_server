from mcp.server.fastmcp import FastMCP
from services.fetcher import fetch_web_data
from services.summarizer import summarize_articles
from services.context_builder import build_final_prompt
from services.intent_parser import extract_financial_entities
from services.portfolio import load_portfolio, add_ticker, remove_ticker
from services.alerts import check_alerts, check_trading_opportunities, send_trading_alert
from services.market_summary import get_market_wrap
import logging
import json
import sys
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler('financial_mcp.log')
    ]
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

mcp = FastMCP("Financial-MCP-Server")

@mcp.tool()
async def financial_context(query: str) -> dict:
    try:
        if not query or not isinstance(query, str):
            logger.error(f"Invalid query input: {query}")
            return {
                "error": "Invalid query input",
                "query": str(query),
                "tickers": [],
                "keywords": [],
                "context": [],
                "final_prompt": ""
            }
            
        logger.debug(f"Processing financial context query: {query}")
        
        try:
            parsed = extract_financial_entities(query)
            logger.debug(f"Parsed entities: {parsed}")
        except Exception as e:
            logger.error(f"Error parsing entities: {str(e)}", exc_info=True)
            return {
                "error": f"Failed to parse query: {str(e)}",
                "query": query,
                "tickers": [],
                "keywords": [],
                "context": [],
                "final_prompt": ""
            }
        
        try:
            articles = await fetch_web_data(query, tickers=parsed["tickers"])
            logger.debug(f"Fetched {len(articles)} articles")
        except Exception as e:
            logger.error(f"Error fetching articles: {str(e)}", exc_info=True)
            return {
                "error": f"Failed to fetch articles: {str(e)}",
                "query": query,
                "tickers": parsed["tickers"],
                "keywords": parsed["keywords"],
                "context": [],
                "final_prompt": f"Error fetching market data: {str(e)}"
            }
        
        if not articles:
            logger.warning("No articles found")
            return {
                "query": query,
                "tickers": parsed["tickers"],
                "keywords": parsed["keywords"],
                "context": [],
                "final_prompt": "No recent market data found for the query."
            }
        
        try:
            summaries = await summarize_articles(articles)
            logger.debug(f"Generated summaries: {json.dumps(summaries, indent=2)}")
        except Exception as e:
            logger.error(f"Error summarizing articles: {str(e)}", exc_info=True)
            return {
                "error": f"Failed to summarize articles: {str(e)}",
                "query": query,
                "tickers": parsed["tickers"],
                "keywords": parsed["keywords"],
                "context": articles,  # Return raw articles if summarization fails
                "final_prompt": f"Error summarizing market data: {str(e)}"
            }
        
        final_prompt = build_final_prompt(query, summaries)
        
        response = {
            "query": query,
            "tickers": parsed["tickers"],
            "keywords": parsed["keywords"],
            "context": summaries,
            "final_prompt": final_prompt
        }
        logger.debug(f"Returning response: {json.dumps(response, indent=2)}")
        return response
    except Exception as e:
        logger.error(f"Unhandled error in financial_context: {str(e)}", exc_info=True)
        return {
            "error": str(e),
            "query": query if isinstance(query, str) else str(query),
            "tickers": [],
            "keywords": [],
            "context": [],
            "final_prompt": f"Unhandled error: {str(e)}"
        }
    
@mcp.tool()
def market_summary() -> dict:
    return get_market_wrap()

@mcp.tool()
def get_portfolio() -> dict:
    logger.debug("Loading portfolio data from resource endpoint")
    return load_portfolio()

@mcp.resource("financial://market-summary")
def market_summary() -> dict:
    return get_market_wrap()

@mcp.resource("portfolio://data")
def get_portfolio() -> dict:
    logger.debug("Loading portfolio data from resource endpoint")
    return load_portfolio()

# Cache invalidation helper
def invalidate_portfolio_cache():
    logger.debug("Invalidating portfolio cache")
    if hasattr(mcp, '_resource_cache'):
        mcp._resource_cache.pop('portfolio://data', None)

@mcp.tool()
def add_stock(ticker: str) -> dict:
    try:
        logger.debug(f"Adding stock {ticker}")
        result = add_ticker(ticker)
        logger.debug(f"Add stock result: {result}")
        # Invalidate the portfolio cache
        invalidate_portfolio_cache()
        # Verify the change was saved
        current = load_portfolio()
        logger.debug(f"Current portfolio after add: {current}")
        return current
    except Exception as e:
        logger.error(f"Error in add_stock: {str(e)}")
        return {"error": str(e), "tickers": []}

@mcp.tool()
def remove_stock(ticker: str) -> dict:
    try:
        logger.debug(f"Removing stock {ticker}")
        result = remove_ticker(ticker)
        logger.debug(f"Remove stock result: {result}")
        # Invalidate the portfolio cache
        invalidate_portfolio_cache()
        # Verify the change was saved
        current = load_portfolio()
        logger.debug(f"Current portfolio after remove: {current}")
        return current
    except Exception as e:
        logger.error(f"Error in remove_stock: {str(e)}")
        return {"error": str(e), "tickers": []}

@mcp.tool()
async def portfolio_alerts(random_string: str) -> dict:
    """
    Check alerts for stocks. Can handle both all stocks and specific tickers.
    Args:
        random_string: Can be either "all" for all stocks, or a specific ticker symbol
    Returns:
        dict: Dictionary containing alerts
    """
    try:
        # If a specific ticker is requested, check trading opportunities
        if random_string and random_string.upper() != "ALL":
            opportunities = await check_trading_opportunities(random_string)
            return {"alerts": opportunities}
        
        # Otherwise get alerts for all stocks
        alerts = await check_alerts(None)
        return {"alerts": alerts}
    except Exception as e:
        logger.error(f"Error in portfolio_alerts: {str(e)}")
        return {"alerts": [f"⚠️ Error: {str(e)}"]}

@mcp.tool()
async def check_stock_alerts(ticker: str) -> dict:
    """
    Check alerts for a specific stock.
    Args:
        ticker: The stock ticker to check alerts for
    Returns:
        dict: Dictionary containing alerts for the specified stock
    """
    try:
        if not ticker:
            return {"alerts": ["⚠️ No ticker provided"]}
            
        # Convert to list with single ticker
        ticker_list = [ticker.strip().upper()]
        alerts = await check_alerts(ticker_list)
        
        # Filter alerts to only show those for the requested ticker
        filtered_alerts = [alert for alert in alerts 
                         if ticker.upper() in alert]
        return {"alerts": filtered_alerts}
    except Exception as e:
        logger.error(f"Error in check_stock_alerts: {str(e)}")
        return {"alerts": [f"⚠️ Error checking {ticker}: {str(e)}"]}

@mcp.tool()
async def single_stock_alert(ticker: str) -> dict:
    """
    Check alerts for a specific stock only.
    Args:
        ticker: The stock ticker to check alerts for
    Returns:
        dict: Dictionary containing alerts for the specified stock
    """
    try:
        if not ticker:
            return {"alerts": ["⚠️ No ticker provided"]}
        
        alerts = await check_alerts([ticker.strip().upper()])
        return {"alerts": alerts}
    except Exception as e:
        logger.error(f"Error in single_stock_alert: {str(e)}")
        return {"alerts": [f"⚠️ Error: {str(e)}"]}

if __name__ == "__main__":
    logger.debug("Starting Financial-MCP-Server...")
    try:
        logger.info("Initializing MCP server with stdio transport")
        mcp.run(transport="stdio")
        logger.debug("MCP server started successfully")
    except json.JSONDecodeError as je:
        logger.error(f"JSON decode error: {str(je)}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Failed to start MCP server: {str(e)}", exc_info=True)
        raise