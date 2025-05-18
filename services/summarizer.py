import httpx
import os
import json
import string
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

OLLAMA_HOST = "http://localhost:11434"
MODEL = "mistral"
# Increased timeout for longer articles
TIMEOUT_SECONDS = 60

def clean_sentiment(sentiment: str) -> str:
    """Clean and validate the sentiment value."""
    # Remove punctuation and whitespace, convert to upper case
    cleaned = sentiment.strip().strip(string.punctuation).upper()
    
    # Map similar words to our standard values
    sentiment_map = {
        "POSITIVE": "POSITIVE",
        "NEGATIVE": "NEGATIVE",
        "NEUTRAL": "NEUTRAL",
        "BULLISH": "POSITIVE",
        "BEARISH": "NEGATIVE",
        "MIXED": "NEUTRAL"
    }
    
    return sentiment_map.get(cleaned, "NEUTRAL")

async def summarize_articles(articles: list) -> List[Dict]:
    summaries = []
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=TIMEOUT_SECONDS)) as client:
        for article in articles:
            try:
                prompt = f"""You are a financial news analyst. Analyze the following article and provide:

1. A detailed summary that includes:
   - Main story/event
   - Key players involved
   - Important numbers or statistics
   - Market implications or potential impact
   - Any relevant context or background
   - Notable quotes or statements

2. The overall market sentiment (MUST be exactly one of: POSITIVE, NEGATIVE, or NEUTRAL)
   - POSITIVE: Good news that could boost market/stock performance
   - NEGATIVE: Bad news that could hurt market/stock performance
   - NEUTRAL: Limited market impact or mixed implications

Format your response exactly as follows:
Summary: [Your detailed summary here in one paragraph]
Sentiment: [POSITIVE/NEGATIVE/NEUTRAL]

News Article:
{article['content']}
"""
                response = await client.post(
                    f"{OLLAMA_HOST}/api/generate",
                    json={"model": MODEL, "prompt": prompt, "stream": False},  # Disable streaming
                    timeout=TIMEOUT_SECONDS
                )
                
                try:
                    response_json = response.json()
                    full_response = response_json.get('response', '')
                    logger.debug(f"Received response from Ollama for article: {article['title']}")
                    
                    if not full_response:
                        raise ValueError("Empty response from Ollama")
                    
                    if "Summary:" in full_response and "Sentiment:" in full_response:
                        try:
                            _, content = full_response.split("Summary:", 1)
                            summary_part, sentiment_part = content.split("Sentiment:", 1)
                            
                            summary = summary_part.strip()
                            sentiment = clean_sentiment(sentiment_part)
                            
                            logger.debug(f"Successfully parsed summary and sentiment for: {article['title']}")
                        except Exception as e:
                            logger.error(f"Error parsing response format: {str(e)}")
                            summary = full_response.strip()
                            sentiment = "NEUTRAL"
                    else:
                        logger.warning(f"Missing Summary/Sentiment markers in response for: {article['title']}")
                        summary = full_response.strip()
                        sentiment = "NEUTRAL"
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error in Ollama response: {str(e)}")
                    summary = "Error: Invalid response format"
                    sentiment = "NEUTRAL"
                
                summary_obj = {
                    "title": article["title"],
                    "summary": summary,
                    "sentiment": sentiment
                }
                
                # Validate JSON serialization before adding
                try:
                    json.dumps(summary_obj)  # Test if object is JSON serializable
                    summaries.append(summary_obj)
                except (TypeError, json.JSONDecodeError) as e:
                    logger.error(f"Error serializing summary object: {str(e)}")
                    summaries.append({
                        "title": article["title"],
                        "summary": "Error: Failed to create valid summary",
                        "sentiment": "NEUTRAL"
                    })
                    
            except httpx.TimeoutException:
                logger.error(f"Timeout processing article: {article['title']}")
                summaries.append({
                    "title": article["title"],
                    "summary": "Error: Request timed out",
                    "sentiment": "NEUTRAL"
                })
            except Exception as e:
                logger.error(f"Unexpected error processing article: {article['title']}, Error: {str(e)}")
                summaries.append({
                    "title": article["title"],
                    "summary": f"Error: {str(e)}",
                    "sentiment": "NEUTRAL"
                })
    return summaries
