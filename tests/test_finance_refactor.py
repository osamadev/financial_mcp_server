import asyncio
import json
import os
import tempfile
import unittest

from services import alerts, portfolio
from services.market_data import normalize_ticker
from services.security import StaticTokenVerifier


class MarketDataTests(unittest.TestCase):
    def test_normalize_ticker_accepts_dots(self):
        self.assertEqual(normalize_ticker("brk.b"), "BRK.B")

    def test_normalize_ticker_rejects_invalid_symbols(self):
        with self.assertRaises(ValueError):
            normalize_ticker("AAPL$")


class PortfolioMigrationTests(unittest.TestCase):
    def test_load_portfolio_migrates_legacy_tickers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = os.path.join(tmpdir, "portfolio.json")
            with open(test_file, "w", encoding="utf-8") as f:
                json.dump({"tickers": ["AAPL", "MSFT"]}, f)

            old_file = portfolio.PORTFOLIO_FILE
            portfolio.PORTFOLIO_FILE = test_file
            try:
                loaded = portfolio.load_portfolio()
                self.assertEqual(loaded["tickers"], ["AAPL", "MSFT"])
                self.assertEqual(len(loaded["positions"]), 2)
                self.assertIn("alerts", loaded)
            finally:
                portfolio.PORTFOLIO_FILE = old_file


class SecurityTests(unittest.TestCase):
    def test_static_token_verifier(self):
        verifier = StaticTokenVerifier("secret-token")
        token = asyncio.run(verifier.verify_token("secret-token"))
        bad = asyncio.run(verifier.verify_token("bad-token"))
        self.assertIsNotNone(token)
        self.assertIsNone(bad)


class AlertEngineTests(unittest.TestCase):
    def test_check_alerts_returns_triggered_event(self):
        original_quote = alerts.get_stock_quote
        original_get_price_alerts = alerts.get_price_alerts
        original_portfolio = alerts.load_portfolio
        try:
            alerts.get_stock_quote = lambda ticker: {"price": 210.0}
            alerts.get_price_alerts = lambda ticker=None: {"AAPL": {"above": 200.0, "below": None}}
            alerts.load_portfolio = lambda: {"positions": [{"ticker": "AAPL"}]}

            result = asyncio.run(alerts.check_alerts(send_notifications=False))
            self.assertEqual(result["checked_tickers"], ["AAPL"])
            self.assertEqual(len(result["events"]), 1)
            self.assertEqual(result["events"][0]["threshold_type"], "above")
        finally:
            alerts.get_stock_quote = original_quote
            alerts.get_price_alerts = original_get_price_alerts
            alerts.load_portfolio = original_portfolio


if __name__ == "__main__":
    unittest.main()
