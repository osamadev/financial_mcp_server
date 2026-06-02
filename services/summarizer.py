import httpx
import os
import json
import string
import logging
from typing import List, Dict
from openai import AsyncOpenAI  # type: ignore[reportMissingImports]

logger = logging.getLogger(__name__)

# Configurable summarizer backend:
# - ollama: local/remote Ollama endpoint
# - openai: OpenAI-compatible API
# - auto: prefer OpenAI when OPENAI_API_KEY is set, otherwise Ollama
SUMMARIZER_PROVIDER = os.getenv("SUMMARIZER_PROVIDER", "ollama").lower()
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "mistral")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL")
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


def _resolve_provider() -> str:
    provider = SUMMARIZER_PROVIDER
    if provider == "auto":
        return "openai" if OPENAI_API_KEY else "ollama"
    if provider in ("ollama", "openai"):
        return provider
    logger.warning(f"Unknown SUMMARIZER_PROVIDER={provider}; falling back to ollama")
    return "ollama"


def _build_prompt(article: dict) -> str:
    return f"""You are a financial news analyst. Analyze the following article and provide:

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


async def _summarize_with_ollama(client: httpx.AsyncClient, prompt: str, title: str) -> str:
    response = await client.post(
        f"{OLLAMA_HOST}/api/generate",
        json={"model": OLLAMA_MODEL, "prompt": prompt, "stream": False},
        timeout=TIMEOUT_SECONDS,
    )
    response_json = response.json()
    full_response = response_json.get("response", "")
    logger.debug(f"Received response from Ollama for article: {title}")
    if not full_response:
        raise ValueError("Empty response from Ollama")
    return full_response


async def _summarize_with_openai(client: AsyncOpenAI, prompt: str, title: str) -> str:
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is required when SUMMARIZER_PROVIDER=openai")

    response = await client.responses.create(
        model=OPENAI_MODEL,
        input=prompt,
    )
    full_response = getattr(response, "output_text", "") or ""
    logger.debug(f"Received response from OpenAI for article: {title}")
    if not full_response:
        raise ValueError("Empty response from OpenAI")
    return full_response


async def summarize_articles(articles: list) -> List[Dict]:
    summaries = []
    provider = _resolve_provider()

    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=TIMEOUT_SECONDS)) as ollama_client:
        openai_client = (
            AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL or None)
            if provider == "openai"
            else None
        )

        for article in articles:
            try:
                prompt = _build_prompt(article)

                if provider == "openai":
                    full_response = await _summarize_with_openai(
                        openai_client, prompt, article["title"]
                    )
                else:
                    full_response = await _summarize_with_ollama(
                        ollama_client, prompt, article["title"]
                    )

                if "Summary:" in full_response and "Sentiment:" in full_response:
                    try:
                        _, content = full_response.split("Summary:", 1)
                        summary_part, sentiment_part = content.split("Sentiment:", 1)

                        summary = summary_part.strip()
                        sentiment = clean_sentiment(sentiment_part)
                        logger.debug(
                            f"Successfully parsed summary and sentiment for: {article['title']}"
                        )
                    except Exception as e:
                        logger.error(f"Error parsing response format: {str(e)}")
                        summary = full_response.strip()
                        sentiment = "NEUTRAL"
                else:
                    logger.warning(
                        f"Missing Summary/Sentiment markers in response for: {article['title']}"
                    )
                    summary = full_response.strip()
                    sentiment = "NEUTRAL"

                summary_obj = {
                    "title": article["title"],
                    "summary": summary,
                    "sentiment": sentiment,
                    "provider": provider,
                }

                try:
                    json.dumps(summary_obj)
                    summaries.append(summary_obj)
                except (TypeError, json.JSONDecodeError) as e:
                    logger.error(f"Error serializing summary object: {str(e)}")
                    summaries.append(
                        {
                            "title": article["title"],
                            "summary": "Error: Failed to create valid summary",
                            "sentiment": "NEUTRAL",
                            "provider": provider,
                        }
                    )

            except httpx.TimeoutException:
                logger.error(f"Timeout processing article: {article['title']}")
                summaries.append(
                    {
                        "title": article["title"],
                        "summary": "Error: Request timed out",
                        "sentiment": "NEUTRAL",
                        "provider": provider,
                    }
                )
            except Exception as e:
                logger.error(
                    f"Unexpected error processing article: {article['title']}, Error: {str(e)}"
                )
                summaries.append(
                    {
                        "title": article["title"],
                        "summary": f"Error: {str(e)}",
                        "sentiment": "NEUTRAL",
                        "provider": provider,
                    }
                )
    return summaries
