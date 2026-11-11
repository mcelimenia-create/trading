"""Tests del calendario de resultados (sin red)."""

import os
import sys
import unittest

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)

import catalysts  # noqa: E402

EVENTS = [
    {"symbol": "TSLA", "date": "2026-11-15"},
    {"symbol": "TSLA", "date": "2026-12-30"},
    {"symbol": "NVDA", "date": "2026-11-13"},
    {"symbol": "KO", "date": "2026-11-12"},
]


class UpcomingTest(unittest.TestCase):
    def test_keeps_only_held_symbols_inside_the_window(self):
        found = catalysts.upcoming(EVENTS, ["TSLA", "NVDA"], "2026-11-11", 10)
        self.assertEqual(found, [("NVDA", "2026-11-13"), ("TSLA", "2026-11-15")])


class EarningsSoonTest(unittest.TestCase):
    def test_no_key_means_no_data(self):
        self.assertIsNone(catalysts.earnings_soon(["TSLA"], "2026-11-11", 10, "", fetch=lambda *a: []))

    def test_failed_request_means_no_data(self):
        def broken(*args):
            raise OSError("sin red")
        self.assertIsNone(catalysts.earnings_soon(["TSLA"], "2026-11-11", 10, "k", fetch=broken))

    def test_asks_for_the_window_and_filters(self):
        asked = []

        def fake(start, end, token):
            asked.append((start, end))
            return EVENTS

        found = catalysts.earnings_soon(["TSLA"], "2026-11-11", 10, "k", fetch=fake)
        self.assertEqual(asked, [("2026-11-11", "2026-11-21")])
        self.assertEqual(found, [("TSLA", "2026-11-15")])


if __name__ == "__main__":
    unittest.main()
