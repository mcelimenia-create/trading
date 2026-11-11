"""Tests del escaner de EEUU (sin red)."""

import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)

import scanner  # noqa: E402
from test_scripts import rising_bars_with_breakout  # noqa: E402


def with_volume(bars, volume):
    return [dict(b, volume=volume) for b in bars]


class UniverseTest(unittest.TestCase):
    def test_keeps_only_nyse_and_nasdaq_plain_tickers(self):
        payload = {"data": [
            [1, "A", "AAPL", "Nasdaq"], [2, "B", "BRK-B", "NYSE"], [3, "C", "XYZ", "OTC"],
            [4, "D", "KO", "NYSE"], [5, "E", "TOOLONGX", "Nasdaq"],
        ]}
        self.assertEqual(scanner.universe_from_sec(payload), ["AAPL", "KO"])


class LiquidityTest(unittest.TestCase):
    def test_liquid_stock_passes(self):
        bars = with_volume(rising_bars_with_breakout(), 1_000_000)
        self.assertTrue(scanner.is_liquid(bars))

    def test_thin_stock_is_rejected(self):
        bars = with_volume(rising_bars_with_breakout(), 1_000)
        self.assertFalse(scanner.is_liquid(bars))

    def test_penny_stock_is_rejected(self):
        bars = with_volume(rising_bars_with_breakout(), 1_000_000)
        bars[-1] = dict(bars[-1], close=2.0)
        self.assertFalse(scanner.is_liquid(bars))


class ScanUniverseTest(unittest.TestCase):
    def test_proposes_liquid_breakouts_and_counts_failures(self):
        good = with_volume(rising_bars_with_breakout(), 1_000_000)
        thin = with_volume(rising_bars_with_breakout(), 10)

        def fetch(symbol):
            if symbol == "BROKEN":
                raise OSError("sin red")
            return {"GOOD": good, "THIN": thin}[symbol]

        proposals, checked = scanner.scan_universe(["GOOD", "THIN", "BROKEN"], fetch, clock=lambda: 0.0)
        self.assertEqual([p["symbol"] for p in proposals], ["GOOD"])
        self.assertEqual(checked, 3)

    def test_stops_when_the_time_budget_is_spent(self):
        times = iter([0.0, 0.0, 100.0])
        proposals, checked = scanner.scan_universe(["A", "B", "C"],
                                                   lambda s: [], budget_s=50, clock=lambda: next(times))
        self.assertEqual(checked, 1)


class MessageTest(unittest.TestCase):
    def test_message_says_it_is_a_proposal_not_an_order(self):
        text = scanner.format_message([{"symbol": "GOOD", "date": "2026-11-10", "close": 12.3}], 500, 6000)
        self.assertIn("PROPUESTAS PARA VIGILAR", text)
        self.assertIn("revisadas 500 de 6000", text)
        self.assertIn("GOOD", text)

    def test_message_when_nothing_qualifies(self):
        self.assertIn("Ninguna", scanner.format_message([], 500, 6000))


if __name__ == "__main__":
    unittest.main()
