import { test } from "node:test";
import assert from "node:assert/strict";
import { atr, sma, isSignal } from "../src/indicators.js";
import { sizePosition } from "../src/sizing.js";
import { classifyRegime } from "../src/regime.js";

const CFG = {
  capital_eur: 700, risk_pct: 0.02, max_weight: 0.2, commission_eur: 1.0,
  regime: { sma_days: 200, vix_max: 25 },
};

function bars(closes) {
  return closes.map((close, i) => ({
    date: new Date(Date.UTC(2025, 0, 1 + i)).toISOString().slice(0, 10),
    open: close, high: close + 1, low: close - 1, close, volume: 1,
  }));
}

test("sma averages the last n values", () => {
  assert.equal(sma([1, 2, 3, 4], 2), 3.5);
});

test("atr averages true range over 14 bars", () => {
  const data = bars(Array.from({ length: 30 }, () => 100));
  assert.equal(atr(data, 29), 2);
});

test("signal needs a close above the 200-day average and the 60-day high", () => {
  const rising = Array.from({ length: 260 }, (_, i) => 100 + i * 0.1);
  rising.push(rising[rising.length - 1] + 20);
  assert.equal(isSignal(bars(rising), rising.length - 1), true);
  assert.equal(isSignal(bars(rising.slice(0, 100)), 99), false);
});

test("sizing risks 2% of capital including round-trip commission", () => {
  const r = sizePosition(110, 100, 1.1, CFG);
  assert.ok(Math.abs(r.shares - 1.32) < 1e-4);
  assert.ok(r.risk_eur <= 14);
});

test("sizing caps the position at 20% of capital", () => {
  const r = sizePosition(110, 109, 1.1, CFG);
  assert.equal(r.capped, true);
  assert.ok(Math.abs(r.weight - 0.2) < 1e-4);
});

test("sizing rejects a stop above the entry", () => {
  assert.throws(() => sizePosition(100, 105, 1.1, CFG));
});

test("regime is risk when VIX is above the threshold", () => {
  const up = Array.from({ length: 250 }, (_, i) => 100 + i * 0.5);
  const r = classifyRegime(up, up, 31, CFG);
  assert.equal(r.state, "riesgo");
  assert.equal(r.exposure_factor, 0.5);
});

test("regime is unknown with short history or missing VIX", () => {
  const up = Array.from({ length: 250 }, (_, i) => 100 + i * 0.5);
  assert.equal(classifyRegime(up.slice(0, 50), up, 15, CFG).state, "desconocido");
  assert.equal(classifyRegime(up, up, NaN, CFG).state, "desconocido");
});
