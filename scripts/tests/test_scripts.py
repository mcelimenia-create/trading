"""Tests de las funciones puras de scripts/. Sin red: los datos se construyen en memoria."""

import os
import sys
import unittest
from datetime import date, timedelta

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)

import paper_trader  # noqa: E402
import real_positions  # noqa: E402
import fundamentals  # noqa: E402
import trader_bot  # noqa: E402


def make_bars(closes, start=date(2025, 1, 1)):
    bars = []
    for i, close in enumerate(closes):
        bars.append({
            "date": (start + timedelta(days=i)).isoformat(),
            "open": close, "high": close + 1, "low": close - 1, "close": close,
        })
    return bars


def rising_bars_with_breakout(days=260):
    closes = [100 + i * 0.1 for i in range(days - 1)]
    closes.append(closes[-1] + 20)
    return make_bars(closes)


class PaperSignalTest(unittest.TestCase):
    def test_same_signal_is_not_added_twice_on_the_same_day(self):
        bars = rising_bars_with_breakout()
        dates = [b["date"] for b in bars]
        state = {"pending": [], "positions": [], "closed": []}
        first = paper_trader.add_new_signal(state, "TEST", bars, dates)
        second = paper_trader.add_new_signal(state, "TEST", bars, dates)
        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(len(state["pending"]), 1)

    def test_signal_already_closed_for_that_date_is_not_added_again(self):
        bars = rising_bars_with_breakout()
        dates = [b["date"] for b in bars]
        state = {"pending": [], "positions": [], "closed": [{
            "symbol": "TEST", "signal_date": dates[-1], "entry_date": dates[-1],
            "exit_date": dates[-1], "ret": -0.01,
        }]}
        self.assertEqual(paper_trader.add_new_signal(state, "TEST", bars, dates), [])
        self.assertEqual(state["pending"], [])


class MarkToMarketTest(unittest.TestCase):
    def test_open_positions_get_their_last_close(self):
        bars = make_bars([100, 105, 110])
        state = {"pending": [], "positions": [{"symbol": "TEST", "entry": 100}], "closed": []}
        marked = paper_trader.mark_to_market(state, {"TEST": bars})
        self.assertEqual(marked["positions"][0]["last_close"], 110)
        self.assertEqual(marked["positions"][0]["last_date"], bars[-1]["date"])
        self.assertNotIn("last_close", state["positions"][0])


class WeightTest(unittest.TestCase):
    def test_weight_risks_two_percent_of_the_book(self):
        self.assertAlmostEqual(paper_trader.weight_for(100, 90), 0.2)

    def test_weight_is_capped_at_twenty_percent(self):
        self.assertEqual(paper_trader.weight_for(100, 99), paper_trader.MAX_WEIGHT)


class RealPositionsCommandTest(unittest.TestCase):
    def setUp(self):
        self.no_fetch = lambda symbol: []

    def test_entry_command_registers_position(self):
        state, reply = real_positions.handle_command(
            real_positions.empty_real_state(), "entre tsla 380,5 10", self.no_fetch, today="2026-11-11")
        self.assertEqual(state["open"][0]["symbol"], "TSLA")
        self.assertEqual(state["open"][0]["entry"], 380.5)
        self.assertEqual(state["open"][0]["shares"], 10)
        self.assertIn("Registrada entrada en TSLA", reply)

    def test_exit_without_open_position_says_so(self):
        state, reply = real_positions.handle_command(
            real_positions.empty_real_state(), "sali TSLA 390", self.no_fetch, today="2026-11-11")
        self.assertEqual(state["closed"], [])
        self.assertIn("No tengo ninguna posicion abierta", reply)

    def test_exit_moves_position_to_closed_with_return(self):
        opened, _ = real_positions.handle_command(
            real_positions.empty_real_state(), "entre TSLA 100", self.no_fetch, today="2026-11-11")
        state, _ = real_positions.handle_command(opened, "sali TSLA 110", self.no_fetch)
        self.assertEqual(state["open"], [])
        self.assertAlmostEqual(state["closed"][0]["ret"], 0.1)

    def test_unknown_text_gets_help_hint(self):
        _, reply = real_positions.handle_command(real_positions.empty_real_state(), "hola", self.no_fetch)
        self.assertIn("ayuda", reply)


class LimitWarningsTest(unittest.TestCase):
    CFG = {"capital_eur": 700, "max_weight": 0.20, "max_monthly_loss_pct": 0.05}

    def test_warns_when_one_position_exceeds_twenty_percent(self):
        state = {"open": [{"symbol": "TSLA", "entry": 100.0, "shares": 2.0}], "closed": []}
        warnings = real_positions.limit_warnings(state, self.CFG, "2026-11-11", fx=1.1)
        self.assertTrue(any("TSLA" in w and "20%" in w for w in warnings))

    def test_warns_when_monthly_net_loss_reaches_five_percent(self):
        state = {"open": [], "closed": [{"symbol": "TSLA", "entry": 100.0, "exit": 60.0, "shares": 2.0,
                                         "exit_date": "2026-11-05"}]}
        warnings = real_positions.limit_warnings(state, self.CFG, "2026-11-11", fx=1.1)
        self.assertTrue(any("mensual" in w for w in warnings))

    def test_no_warning_for_losses_in_previous_month(self):
        state = {"open": [], "closed": [{"symbol": "TSLA", "entry": 100.0, "exit": 60.0, "shares": 2.0,
                                         "exit_date": "2026-10-28"}]}
        self.assertEqual(real_positions.limit_warnings(state, self.CFG, "2026-11-11", fx=1.1), [])

    def test_exit_records_its_date(self):
        opened, _ = real_positions.handle_command(
            real_positions.empty_real_state(), "entre TSLA 100", lambda s: [], today="2026-11-01")
        state, _ = real_positions.handle_command(opened, "sali TSLA 110", lambda s: [], today="2026-11-11")
        self.assertEqual(state["closed"][0]["exit_date"], "2026-11-11")


class MonitorTest(unittest.TestCase):
    def test_stop_alert_is_sent_once_per_day(self):
        bars = make_bars([100] * 20)
        bars[-1] = dict(bars[-1], low=80)
        position = {"symbol": "TSLA", "entry": 100, "shares": 1, "stop": 90, "entry_date": bars[5]["date"],
                    "last_alert": None}
        state = {"open": [position], "closed": []}
        first, messages = real_positions.monitor(state, lambda s: bars, today="2026-11-11")
        second, again = real_positions.monitor(first, lambda s: bars, today="2026-11-11")
        self.assertEqual(len(messages), 1)
        self.assertEqual(again, [])
        self.assertEqual(second["open"][0]["last_alert"], "2026-11-11")


class FailureReportTest(unittest.TestCase):
    def test_failure_is_sent_with_job_name_and_error(self):
        sent = []
        trader_bot.report_failure("paper", RuntimeError("sin red"), sent.append)
        self.assertEqual(len(sent), 1)
        self.assertIn("paper", sent[0])
        self.assertIn("sin red", sent[0])

    def test_failure_to_send_does_not_hide_the_original_error(self):
        def broken_notify(text):
            raise OSError("Telegram caido")
        trader_bot.report_failure("paper", RuntimeError("sin red"), broken_notify)


class TickerMapTest(unittest.TestCase):
    def test_maps_upper_ticker_to_cik(self):
        payload = {"0": {"cik_str": 320193, "ticker": "aapl"}, "1": {"cik_str": 789019, "ticker": "MSFT"}}
        self.assertEqual(fundamentals.ticker_map(payload)["AAPL"], 320193)


class LatestGrowthTest(unittest.TestCase):
    def test_uses_only_reports_published_before_the_day(self):
        records = [("2026-02-01", 0.10, "2025-12-31"), ("2026-05-01", 0.20, "2026-03-31")]
        self.assertEqual(fundamentals.latest_growth(records, "2026-03-01"), 0.10)

    def test_none_when_no_report_is_published_yet(self):
        records = [("2026-02-01", 0.10, "2025-12-31")]
        self.assertIsNone(fundamentals.latest_growth(records, "2026-01-01"))


if __name__ == "__main__":
    unittest.main()
