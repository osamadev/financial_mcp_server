import re

def extract_financial_entities(query: str):
    tickers = re.findall(r'\b[A-Z]{1,5}\b', query)
    terms = ["stock", "earnings", "market", "revenue", "forecast", "dividend", "split", "SEC", "inflation"]
    matched_terms = [term for term in terms if term in query.lower()]
    return {"tickers": tickers, "keywords": matched_terms}
