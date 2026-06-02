import unittest

from services.intent_parser import extract_financial_entities


class IntentParserTests(unittest.TestCase):
    def test_extracts_cashtag_and_upper_tickers(self):
        query = "Give me earnings impact for $aapl and MSFT this week."
        result = extract_financial_entities(query)
        self.assertEqual(result["tickers"], ["AAPL", "MSFT"])
        self.assertIn("earnings", result["keywords"])

    def test_extracts_hint_based_ticker(self):
        query = "Please check ticker: tsla and symbol brk.b forecast."
        result = extract_financial_entities(query)
        self.assertIn("TSLA", result["tickers"])
        self.assertIn("BRK.B", result["tickers"])
        self.assertIn("forecast", result["keywords"])

    def test_filters_common_uppercase_non_tickers(self):
        query = "How does SEC CPI and US inflation affect market outlook?"
        result = extract_financial_entities(query)
        self.assertEqual(result["tickers"], [])
        self.assertIn("sec", result["keywords"])
        self.assertIn("inflation", result["keywords"])
        self.assertIn("market", result["keywords"])


if __name__ == "__main__":
    unittest.main()
