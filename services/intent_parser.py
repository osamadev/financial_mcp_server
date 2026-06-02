import re
from typing import Dict, List

# Common uppercase tokens frequently found in finance prompts but not tickers.
NON_TICKER_TOKENS = {
    "THE",
    "AND",
    "FOR",
    "WITH",
    "FROM",
    "THIS",
    "THAT",
    "WHAT",
    "WHEN",
    "WILL",
    "ARE",
    "YOU",
    "YOUR",
    "CAN",
    "NOT",
    "NEW",
    "NOW",
    "TODAY",
    "ETF",
    "SEC",
    "CPI",
    "GDP",
    "FOMC",
    "AI",
    "US",
    "USA",
}

TICKER_VALIDATION_RE = re.compile(r"^[A-Z][A-Z0-9]{0,4}(?:[.-][A-Z0-9]{1,4})?$")
CASHTAG_RE = re.compile(r"\$([A-Za-z][A-Za-z0-9]{0,4}(?:[.-][A-Za-z0-9]{1,4})?)")
PLAIN_UPPER_TICKER_RE = re.compile(r"\b([A-Z][A-Z0-9]{0,4}(?:[.-][A-Z0-9]{1,4})?)\b")
TICKER_HINT_RE = re.compile(
    r"\b(?:ticker|symbol|stock)\s*[:=]?\s*([A-Za-z][A-Za-z0-9]{0,4}(?:[.-][A-Za-z0-9]{1,4})?)\b",
    re.IGNORECASE,
)

KEYWORD_PATTERNS = {
    "stock": re.compile(r"\bstocks?\b", re.IGNORECASE),
    "earnings": re.compile(r"\bearnings?\b", re.IGNORECASE),
    "market": re.compile(r"\bmarkets?\b", re.IGNORECASE),
    "revenue": re.compile(r"\brevenues?\b", re.IGNORECASE),
    "forecast": re.compile(r"\bforecasts?\b|\bguidance\b|\boutlook\b", re.IGNORECASE),
    "dividend": re.compile(r"\bdividends?\b", re.IGNORECASE),
    "split": re.compile(r"\bsplits?\b|\bstock split\b", re.IGNORECASE),
    "sec": re.compile(r"\bsec\b|\bsecurities and exchange commission\b", re.IGNORECASE),
    "inflation": re.compile(r"\binflation\b|\bcpi\b", re.IGNORECASE),
}


def _normalize_ticker(candidate: str) -> str | None:
    value = candidate.strip().upper().lstrip("$")
    if not value:
        return None
    if not TICKER_VALIDATION_RE.fullmatch(value):
        return None
    return value


def _append_unique(items: List[str], value: str) -> None:
    if value not in items:
        items.append(value)


def extract_financial_entities(query: str) -> Dict[str, List[str]]:
    if not isinstance(query, str):
        return {"tickers": [], "keywords": []}

    tickers: List[str] = []

    # Strong signal: cashtags like $AAPL
    for candidate in CASHTAG_RE.findall(query):
        symbol = _normalize_ticker(candidate)
        if symbol:
            _append_unique(tickers, symbol)

    # Medium signal: explicit "ticker/symbol/stock <value>" hints.
    for candidate in TICKER_HINT_RE.findall(query):
        symbol = _normalize_ticker(candidate)
        if symbol:
            _append_unique(tickers, symbol)

    # Broad signal: plain uppercase ticker-like tokens.
    for candidate in PLAIN_UPPER_TICKER_RE.findall(query):
        symbol = _normalize_ticker(candidate)
        if not symbol:
            continue

        # Avoid many false positives in natural language.
        if symbol in NON_TICKER_TOKENS:
            continue

        # Single/double-letter symbols are too ambiguous unless explicitly hinted/cashtagged.
        if len(symbol) <= 2:
            continue

        _append_unique(tickers, symbol)

    matched_terms: List[str] = []
    for keyword, pattern in KEYWORD_PATTERNS.items():
        if pattern.search(query):
            _append_unique(matched_terms, keyword)

    return {"tickers": tickers, "keywords": matched_terms}
