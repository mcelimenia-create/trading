"""Tests del regimen de mercado y del tamano de posicion en EUR."""

import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)

import regime  # noqa: E402
import sizing  # noqa: E402

CFG = {"capital_eur": 700, "risk_pct": 0.02, "max_weight": 0.20, "commission_eur": 1.0,
       "regime": {"sma_days": 200, "vix_max": 25}}


def rising(days=250, start=100.0, step=0.5):
    return [start + i * step for i in range(days)]


class RegimeTest(unittest.TestCase):
    def test_normal_when_indices_above_average_and_vix_calm(self):
        result = regime.classify(rising(), rising(), 15.0, CFG)
        self.assertEqual(result["state"], "normal")
        self.assertEqual(result["exposure_factor"], 1.0)

    def test_risk_when_index_below_its_200_day_average(self):
        falling = [200 - i * 0.5 for i in range(250)]
        result = regime.classify(falling, rising(), 15.0, CFG)
        self.assertEqual(result["state"], "riesgo")
        self.assertEqual(result["exposure_factor"], 0.5)
        self.assertTrue(any("SPY" in reason for reason in result["reasons"]))

    def test_risk_when_vix_above_threshold(self):
        result = regime.classify(rising(), rising(), 31.0, CFG)
        self.assertEqual(result["state"], "riesgo")
        self.assertTrue(any("VIX" in reason for reason in result["reasons"]))

    def test_unknown_when_history_is_too_short(self):
        result = regime.classify(rising(days=50), rising(), 15.0, CFG)
        self.assertEqual(result["state"], "desconocido")
        self.assertEqual(result["exposure_factor"], 0.5)


class SizingTest(unittest.TestCase):
    def test_risks_two_percent_of_capital_including_round_trip_commission(self):
        # 700 EUR * 2% = 14 EUR; 2 EUR de comision ida y vuelta -> 12 EUR de riesgo
        # stop a 10 USD con cambio 1.10 USD/EUR -> 9.09 EUR por accion -> 1.3200 acciones
        result = sizing.size_position(entry_usd=110.0, stop_usd=100.0, fx_usd_per_eur=1.10, cfg=CFG)
        self.assertAlmostEqual(result["shares"], 1.32, places=4)
        self.assertLessEqual(result["risk_eur"], 14.0)

    def test_position_is_capped_at_twenty_percent_of_capital(self):
        result = sizing.size_position(entry_usd=110.0, stop_usd=109.0, fx_usd_per_eur=1.10, cfg=CFG)
        self.assertTrue(result["capped"])
        self.assertAlmostEqual(result["weight"], 0.20, places=2)

    def test_exposure_factor_halves_the_size(self):
        full = sizing.size_position(110.0, 100.0, 1.10, CFG)
        half = sizing.size_position(110.0, 100.0, 1.10, CFG, exposure_factor=0.5)
        self.assertAlmostEqual(half["shares"], full["shares"] / 2, places=4)

    def test_no_size_when_commissions_eat_the_risk_budget(self):
        tiny = {**CFG, "capital_eur": 3}
        result = sizing.size_position(110.0, 100.0, 1.10, tiny)
        self.assertEqual(result["shares"], 0)

    def test_stop_above_entry_is_rejected(self):
        with self.assertRaises(ValueError):
            sizing.size_position(100.0, 105.0, 1.10, CFG)


if __name__ == "__main__":
    unittest.main()
