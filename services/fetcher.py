import os
import logging
from dotenv import load_dotenv
from serpapi import GoogleSearch
import asyncio
from typing import List, Dict, Any

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# Get API key from environment
SERPAPI_API_KEY = os.getenv('SERPAPI_API_KEY')
if not SERPAPI_API_KEY:
    raise ValueError("SERPAPI_API_KEY environment variable is not set")

async def fetch_web_data(query: str, tickers: List[str] = [], max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Fetch news data from Google News using SerpAPI.
    
    Args:
        query (str): Search query
        tickers (List[str]): List of stock tickers to include in search
        max_results (int): Maximum number of results to return
        
    Returns:
        List[Dict[str, Any]]: List of article data
    """
    logger.debug(f"Fetching web data for query: {query} with tickers: {tickers}")
    
    # Enhance query with tickers if provided
    if tickers:
        query = f"{query} {' '.join(tickers)}"
    
    try:
        # Run the API call in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        search = GoogleSearch({
            "q": query,
            "location": "United States",
            "hl": "en",
            "gl": "us",
            "api_key": SERPAPI_API_KEY,
            "tbm": "nws"
        })
        
        results = await loop.run_in_executor(None, search.get_dict)
        logger.debug(f"API Response keys: {results.keys()}")
        
        if "error" in results:
            error_msg = results['error']
            logger.error(f"SerpAPI error: {error_msg}")
            raise ValueError(f"SerpAPI error: {error_msg}")
            
        news_results = results.get("news_results", [])
        logger.info(f"Found {len(news_results)} news results")
        
        articles = []
        for item in news_results[:max_results]:
            article = {
                "title": item.get("title", ""),
                "content": item.get("snippet") or item.get("title", ""),
                "link": item.get("link", ""),
                "source": item.get("source", ""),
                "date": item.get("date", "")
            }
            articles.append(article)
            
        return articles
    except Exception as e:
        logger.error(f"Error fetching web data: {str(e)}", exc_info=True)
        raise  # Re-raise the exception to be handled by the caller
