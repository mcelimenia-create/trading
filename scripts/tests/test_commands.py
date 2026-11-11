"""Tests de los comandos de Telegram de fase 3 (sin red)."""

import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)

import real_positions  # noqa: E402

CFG = {"capital_eur": 700, "risk_pct": 0.02, "max_weight": 0.20, "commission_eur": 1.0,
       "max_monthly_loss_pct": 0.05, "regime": {"sma_days": 200, "vix_max": 25}}
MARKET = {"cfg": CFG, "fx": 1.10, "exposure_factor": 1.0, "state": "normal",
          "candidates": [{"symbol": "AMZN", "date": "2026-11-10", "close": 270.87, "stop": 249.52}]}


def bars_closing_at(price, days=30):
    return [{"date": f"2026-10-{i + 1:02d}", "open": price, "high": price, "low": price,
             "close": price, "volume": 1} for i in range(days)]


def opened(text="entre TSLA 100 10"):
    state, _ = real_positions.handle_command(real_positions.empty_real_state(), text, lambda s: [],
                                             today="2026-11-01")
    return state


class RiskCommandTest(unittest.TestCase):
    def test_gives_shares_and_euros_for_entry_and_stop(self):
        _, reply = real_positions.handle_command(real_positions.empty_real_state(),
                                                 "riesgo TSLA 110 100", lambda s: [], market=MARKET)
        self.assertIn("TSLA", reply)
        self.assertIn("EUR", reply)
        self.assertIn("acciones", reply)

    def test_stop_above_entry_is_reported(self):
        _, reply = real_positions.handle_command(real_positions.empty_real_state(),
                                                 "riesgo TSLA 100 110", lambda s: [], market=MARKET)
        self.assertIn("por debajo", reply)

    def test_no_exchange_rate_is_reported(self):
        _, reply = real_positions.handle_command(real_positions.empty_real_state(), "riesgo TSLA 110 100",
                                                 lambda s: [], market={**MARKET, "fx": None})
        self.assertIn("tipo de cambio", reply)


class StopCommandTest(unittest.TestCase):
    def test_updates_the_stop_of_an_open_position(self):
        state, reply = real_positions.handle_command(opened(), "stop TSLA 95", lambda s: [])
        self.assertEqual(state["open"][0]["stop"], 95.0)
        self.assertIn("95.00", reply)

    def test_without_position_says_so(self):
        _, reply = real_positions.handle_command(real_positions.empty_real_state(), "stop TSLA 95", lambda s: [])
        self.assertIn("No tengo ninguna posicion abierta", reply)


class PartialExitTest(unittest.TestCase):
    def test_partial_exit_keeps_the_rest_open(self):
        state, _ = real_positions.handle_command(opened(), "sali TSLA 110 4", lambda s: [], today="2026-11-11")
        self.assertEqual(state["open"][0]["shares"], 6)
        self.assertEqual(state["closed"][0]["shares"], 4)
        self.assertAlmostEqual(state["closed"][0]["ret"], 0.1)

    def test_cannot_sell_more_shares_than_held(self):
        state, reply = real_positions.handle_command(opened(), "sali TSLA 110 50", lambda s: [])
        self.assertEqual(state["open"][0]["shares"], 10)
        self.assertEqual(state["closed"], [])
        self.assertIn("solo tienes 10", reply)

    def test_exit_without_shares_closes_everything(self):
        state, _ = real_positions.handle_command(opened(), "sali TSLA 110", lambda s: [])
        self.assertEqual(state["open"], [])
        self.assertEqual(state["closed"][0]["shares"], 10)


class SummaryTest(unittest.TestCase):
    def test_shows_price_return_and_distance_to_stop(self):
        state = opened()
        state["open"][0]["stop"] = 90.0
        text = real_positions.summary_text(state, lambda s: bars_closing_at(110.0), MARKET)
        self.assertIn("TSLA", text)
        self.assertIn("+10.0%", text)
        self.assertIn("Regimen: normal", text)

    def test_empty_book(self):
        self.assertIn("No hay posiciones abiertas", real_positions.summary_text(
            real_positions.empty_real_state(), lambda s: [], MARKET))


class CandidatesCommandTest(unittest.TestCase):
    def test_lists_last_candidates(self):
        _, reply = real_positions.handle_command(real_positions.empty_real_state(), "candidatos",
                                                 lambda s: [], market=MARKET)
        self.assertIn("AMZN", reply)

    def test_none_when_no_candidates(self):
        _, reply = real_positions.handle_command(real_positions.empty_real_state(), "candidatos",
                                                 lambda s: [], market={**MARKET, "candidates": []})
        self.assertIn("No hay candidatos", reply)


class WeeklyReviewTest(unittest.TestCase):
    def test_runs_once_on_sunday(self):
        state = opened()
        state, text = real_positions.weekly_review(state, "2026-11-15")  # domingo
        self.assertIn("TSLA", text)
        again, second = real_positions.weekly_review(state, "2026-11-15")
        self.assertIsNone(second)

    def test_does_not_run_on_other_days(self):
        _, text = real_positions.weekly_review(opened(), "2026-11-11")  # miercoles
        self.assertIsNone(text)


if __name__ == "__main__":
    unittest.main()
