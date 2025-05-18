import yfinance as yf
import httpx
from datetime import datetime
import os

def get_market_wrap():
    index_map = {
        "^GSPC": "S&P 500",
        "^IXIC": "NASDAQ",
        "^DJI": "DOW JONES",
        "^FTSE": "FTSE 100",
        "^N225": "Nikkei 225",
        "^HSI": "Hang Seng",
        "^BSESN": "BSE Sensex",
        "^FCHI": "CAC 40",
        "^GDAXI": "DAX",
        "^STOXX50E": "EURO STOXX 50"
    }

    indices_data = {}
    for symbol, name in index_map.items():
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            indices_data[name] = {
                "price": f"${info.get('regularMarketPrice', 0):,.2f}",
                "change": f"{info.get('regularMarketChange', 0):+.2f}",
                "percent": f"{info.get('regularMarketChangePercent', 0):+.2f}%"
            }
        except Exception as e:
            indices_data[name] = {"error": str(e)}

    tracked_tickers = ["AAPL", "TSLA", "GOOGL", "MSFT", "AMZN", "NVDA", "META"]
    gainers, losers = [], []

    for symbol in tracked_tickers:
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            change_pct = info.get("regularMarketChangePercent", 0)
            data = {
                "ticker": symbol,
                "price": f"${info.get('regularMarketPrice', 0):,.2f}",
                "change": f"{change_pct:+.2f}%"
            }
            if change_pct >= 0:
                gainers.append(data)
            else:
                losers.append(data)
        except:
            continue

    gainers = sorted(gainers, key=lambda x: float(x["change"].replace('%','')), reverse=True)[:3]
    losers = sorted(losers, key=lambda x: float(x["change"].replace('%','')))[:3]

    # Use SerpAPI for news
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    news = []
    if serpapi_key:
        try:
            response = httpx.get("https://serpapi.com/search.json", params={
                "q": "stock market news",
                "tbm": "nws",
                "api_key": serpapi_key
            })
            articles = response.json().get("news_results", [])[:5]
            news = [{"title": a["title"], "link": a["link"]} for a in articles]
        except Exception as e:
            news = [{"error": str(e)}]

    return {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "indices": indices_data,
        "top_gainers": gainers,
        "top_losers": losers,
        "news_headlines": news,
        "summary": "Live global market summary with top movers and headlines."
    }
