import { test } from "node:test";
import assert from "node:assert/strict";
import { exitAlerts, limitWarnings, weeklyReview, newAlerts } from "../src/alerts.js";

const CFG = { capital_eur: 700, max_weight: 0.2, max_monthly_loss_pct: 0.05 };

// 12 sesiones de entrada en 2026-11-02; la ultima barra es la de hoy.
function bars(lows, lastLow, lastClose) {
  return lows.map((low, i) => ({
    date: `2026-11-${String(i + 2).padStart(2, "0")}`, open: 100, high: 101, low, close: 100, volume: 1,
  })).concat([{ date: "2026-11-14", open: 100, high: 101, low: lastLow, close: lastClose, volume: 1 }]);
}

test("exitAlerts fires stop when the low touches the stop", () => {
  const position = { symbol: "TSLA", entry_date: "2026-11-02", stop: 96 };
  const series = bars(Array(12).fill(100), 95, 97);
  const alerts = exitAlerts(position, series);
  assert.equal(alerts[0].kind, "stop");
});

test("exitAlerts fires trailing when close breaks the 10-day low", () => {
  const position = { symbol: "TSLA", entry_date: "2026-11-02", stop: null };
  const series = bars(Array(12).fill(100), 99, 98);
  assert.equal(exitAlerts(position, series)[0].kind, "trailing");
});

test("exitAlerts is silent before the entry day has passed", () => {
  const position = { symbol: "TSLA", entry_date: "2026-11-14", stop: 96 };
  assert.deepEqual(exitAlerts(position, bars(Array(12).fill(100), 50, 50)), []);
});

test("limitWarnings flags weight above 20% and monthly loss", () => {
  const state = {
    open: [{ symbol: "NVDA", entry: 100, shares: 2 }],
    closed: [{ symbol: "X", entry: 100, exit: 50, shares: 10, exit_date: "2026-11-05" }],
  };
  const warnings = limitWarnings(state, CFG, "2026-11-11", 1.0);
  assert.equal(warnings.length, 2);
  assert.match(warnings[0], /NVDA pesa 29%/);
  assert.match(warnings[1], /Perdida neta del mes -500 EUR/);
});

test("limitWarnings is silent without exchange rate", () => {
  assert.deepEqual(limitWarnings({ open: [], closed: [] }, CFG, "2026-11-11", null), []);
});

test("weeklyReview only on Sunday", () => {
  assert.equal(weeklyReview({ open: [] }, "2026-11-11"), null);
  assert.match(weeklyReview({ open: [] }, "2026-11-15"), /REVISION SEMANAL/);
});

test("newAlerts sends each key once per day and prunes old keys", () => {
  const items = [{ key: "stop:TSLA:2026-11-11", text: "aviso" }];
  const first = newAlerts({ sent: { "stop:TSLA:2026-11-10": true } }, items, "2026-11-11");
  assert.deepEqual(first.texts, ["aviso"]);
  assert.deepEqual(Object.keys(first.state.sent), ["stop:TSLA:2026-11-11"]);
  const second = newAlerts(first.state, items, "2026-11-11");
  assert.deepEqual(second.texts, []);
});
