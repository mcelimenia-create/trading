import { test } from "node:test";
import assert from "node:assert/strict";
import { handleCommand, emptyState } from "../src/commands.js";

const CFG = {
  capital_eur: 700, risk_pct: 0.02, max_weight: 0.2, commission_eur: 1.0,
  max_monthly_loss_pct: 0.05, regime: { sma_days: 200, vix_max: 25 },
};

// Dependencias falsas: precios fijos, tipo de cambio y barras con ATR de 2.
function deps(overrides = {}) {
  const bars = Array.from({ length: 30 }, (_, i) => ({
    date: `2026-10-${String(i + 1).padStart(2, "0")}`, open: 100, high: 101, low: 99, close: 100, volume: 1,
  }));
  return {
    today: "2026-11-11",
    cfg: CFG,
    fx: 1.1,
    exposureFactor: 1.0,
    regimeState: "normal",
    getBars: async () => bars,
    getLastClose: async () => 110,
    getCandidates: async () => [{ symbol: "AMZN", date: "2026-11-10", close: 270.87, stop: 249.52 }],
    ...overrides,
  };
}

test("ayuda lists the commands", async () => {
  const r = await handleCommand(emptyState(), "ayuda", deps());
  assert.match(r.reply, /entre TICKER/);
});

test("entre registers a position with its ATR stop", async () => {
  const r = await handleCommand(emptyState(), "entre tsla 100 10", deps());
  assert.equal(r.state.open[0].symbol, "TSLA");
  assert.equal(r.state.open[0].shares, 10);
  assert.equal(r.state.open[0].stop, 96);
  assert.match(r.reply, /Registrada entrada en TSLA/);
});

test("entre accepts decimal commas", async () => {
  const r = await handleCommand(emptyState(), "entre TSLA 100,5 2", deps());
  assert.equal(r.state.open[0].entry, 100.5);
});

test("partial sali keeps the rest open", async () => {
  const opened = await handleCommand(emptyState(), "entre TSLA 100 10", deps());
  const r = await handleCommand(opened.state, "sali TSLA 110 4", deps());
  assert.equal(r.state.open[0].shares, 6);
  assert.equal(r.state.closed[0].shares, 4);
  assert.ok(Math.abs(r.state.closed[0].ret - 0.1) < 1e-9);
});

test("sali refuses more shares than held and zero shares", async () => {
  const opened = await handleCommand(emptyState(), "entre TSLA 100 10", deps());
  const more = await handleCommand(opened.state, "sali TSLA 110 50", deps());
  assert.match(more.reply, /solo tienes 10/);
  const zero = await handleCommand(opened.state, "sali TSLA 110 0", deps());
  assert.match(zero.reply, /mayor que cero/);
  assert.equal(zero.state.closed.length, 0);
});

test("sali without shares closes everything", async () => {
  const opened = await handleCommand(emptyState(), "entre TSLA 100 10", deps());
  const r = await handleCommand(opened.state, "sali TSLA 110", deps({ today: "2026-11-11" }));
  assert.equal(r.state.open.length, 0);
  assert.equal(r.state.closed[0].exit_date, "2026-11-11");
});

test("stop changes the stop of an open position", async () => {
  const opened = await handleCommand(emptyState(), "entre TSLA 100 10", deps());
  const r = await handleCommand(opened.state, "stop TSLA 95", deps());
  assert.equal(r.state.open[0].stop, 95);
});

test("riesgo gives shares and euros; rejects stop above entry", async () => {
  const ok = await handleCommand(emptyState(), "riesgo TSLA 110 100", deps());
  assert.match(ok.reply, /1\.3200 acciones/);
  const bad = await handleCommand(emptyState(), "riesgo TSLA 100 110", deps());
  assert.match(bad.reply, /por debajo/);
});

test("riesgo without exchange rate says so", async () => {
  const r = await handleCommand(emptyState(), "riesgo TSLA 110 100", deps({ fx: null }));
  assert.match(r.reply, /tipo de cambio/);
});

test("resumen shows price, return and distance to stop", async () => {
  const opened = await handleCommand(emptyState(), "entre TSLA 100 10", deps());
  const r = await handleCommand(opened.state, "resumen", deps());
  assert.match(r.reply, /TSLA: precio 110\.00 \(\+10\.0%\)/);
  assert.match(r.reply, /Regimen: normal/);
});

test("resumen on empty book", async () => {
  const r = await handleCommand(emptyState(), "resumen", deps());
  assert.match(r.reply, /No hay posiciones abiertas/);
});

test("candidatos lists the last close candidates", async () => {
  const r = await handleCommand(emptyState(), "candidatos", deps());
  assert.match(r.reply, /AMZN: cierre 270\.87/);
});

test("accents and capitals are accepted in commands", async () => {
  const opened = await handleCommand(emptyState(), "entre TSLA 100 10", deps());
  const r = await handleCommand(opened.state, "SALÍ TSLA 110", deps());
  assert.equal(r.state.open.length, 0);
});

test("unknown text gets a hint", async () => {
  const r = await handleCommand(emptyState(), "hola que tal", deps());
  assert.match(r.reply, /No entendi/);
});

test("numbers with several separators are rejected, not saved as NaN", async () => {
  const r = await handleCommand(emptyState(), "entre TSLA 1,2,3", deps());
  assert.equal(r.state.open.length, 0);
  assert.match(r.reply, /No entendi/);
});

test("zero prices are rejected for entries, exits and stops", async () => {
  const zeroEntry = await handleCommand(emptyState(), "entre TSLA 0 10", deps());
  assert.equal(zeroEntry.state.open.length, 0);
  assert.match(zeroEntry.reply, /mayor que cero/);
  const opened = await handleCommand(emptyState(), "entre TSLA 100 10", deps());
  const zeroExit = await handleCommand(opened.state, "sali TSLA 0", deps());
  assert.equal(zeroExit.state.closed.length, 0);
  const zeroStop = await handleCommand(opened.state, "stop TSLA 0", deps());
  assert.equal(zeroStop.state.open[0].stop, opened.state.open[0].stop);
});
