"""Tests del mensaje y de los datos de candidatos (sin red)."""

import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)

import candidates  # noqa: E402
from test_scripts import rising_bars_with_breakout  # noqa: E402

CFG = {"capital_eur": 700, "risk_pct": 0.02, "max_weight": 0.20, "commission_eur": 1.0,
       "regime": {"sma_days": 200, "vix_max": 25}}


class DescribeTest(unittest.TestCase):
    def test_candidate_carries_stop_size_and_invalidation(self):
        bars = rising_bars_with_breakout()
        item = candidates.describe("TEST", bars, "+10%", CFG, fx=1.10, exposure_factor=1.0)
        self.assertLess(item["stop"], item["close"])
        self.assertGreater(item["size"]["shares"], 0)
        self.assertIn("minimo de 10 dias", item["invalidation"])

    def test_size_is_none_without_exchange_rate(self):
        item = candidates.describe("TEST", rising_bars_with_breakout(), "+10%", CFG, fx=None, exposure_factor=1.0)
        self.assertIsNone(item["size"])


class MessageTest(unittest.TestCase):
    def test_message_shows_regime_and_size_in_euros(self):
        item = candidates.describe("TEST", rising_bars_with_breakout(), "+10%", CFG, fx=1.10, exposure_factor=0.5)
        text = candidates.format_message([item], {"state": "riesgo", "reasons": ["VIX en 30.0, por encima de 25"]})
        self.assertIn("Regimen: riesgo", text)
        self.assertIn("VIX en 30.0", text)
        self.assertIn("EUR", text)

    def test_no_message_without_candidates(self):
        self.assertIsNone(candidates.format_message([], {"state": "normal", "reasons": []}))


if __name__ == "__main__":
    unittest.main()
