// Avisos de la cartera real (funciones puras: los precios y el tipo de cambio se pasan).
import { TRAIL_DAYS } from "./indicators.js";

const EXIT_RULE_TEXT = "Regla de salida cumplida: revisa si sales.";

function utcWeekday(today) {
  return new Date(`${today}T12:00:00Z`).getUTCDay();
}

// Stop tocado (minimo del dia) o cierre que pierde el minimo de los 10 dias anteriores.
export function exitAlerts(position, bars) {
  const start = bars.findIndex((b) => b.date === position.entry_date);
  const last = bars.length - 1;
  if (start < 0 || last <= start || last < TRAIL_DAYS) return [];
  const alerts = [];
  if (position.stop && bars[last].low <= position.stop) {
    alerts.push({ kind: "stop", text: `toco el stop de referencia ${position.stop.toFixed(2)}` });
  }
  const lowest = Math.min(...bars.slice(last - TRAIL_DAYS, last).map((b) => b.low));
  if (bars[last].close < lowest) {
    alerts.push({ kind: "trailing", text: `el cierre ${bars[last].close.toFixed(2)} perdio el minimo de ${TRAIL_DAYS} dias` });
  }
  return alerts;
}

// Peso maximo por accion y perdida neta del mes (en EUR). Sin tipo de cambio no hay avisos.
export function limitWarnings(state, cfg, today, fx) {
  if (!fx) return [];
  const capital = cfg.capital_eur;
  const warnings = [];
  for (const p of state.open) {
    const weight = (p.shares * p.entry) / fx / capital;
    if (weight > cfg.max_weight) {
      warnings.push(`${p.symbol} pesa ${Math.round(100 * weight)}% del capital, por encima del ${Math.round(100 * cfg.max_weight)}%.`);
    }
  }
  const month = today.slice(0, 7);
  const net = state.closed
    .filter((c) => c.exit_date?.slice(0, 7) === month)
    .reduce((sum, c) => sum + ((c.exit - c.entry) * c.shares) / fx, 0);
  if (net <= -cfg.max_monthly_loss_pct * capital) {
    warnings.push(`Perdida neta del mes ${Math.round(net)} EUR: alcanza el limite mensual del ${Math.round(100 * cfg.max_monthly_loss_pct)}%.`);
  }
  return warnings;
}

// Repaso de tesis: solo los domingos.
export function weeklyReview(state, today) {
  if (utcWeekday(today) !== 0) return null;
  if (!state.open.length) return "REVISION SEMANAL: no hay posiciones abiertas.";
  const lines = state.open.map((p) => (p.stop
    ? `${p.symbol}: revisa si la tesis sigue vigente; invalida si toca el stop ${p.stop.toFixed(2)}`
    : `${p.symbol}: revisa si la tesis sigue vigente`));
  return ["REVISION SEMANAL DE TESIS", ...lines].join("\n");
}

// Un aviso por tipo (stop o trailing) y por dia.
export function exitItems(position, bars, today) {
  return exitAlerts(position, bars).map((alert) => ({
    key: `${alert.kind}:${position.symbol}:${today}`,
    text: `${position.symbol}: ${alert.text}. ${EXIT_RULE_TEXT}`,
  }));
}

// items: [{ key, text }]. Cada clave lleva la fecha y se envia una vez; se borran las claves de otros dias.
export function newAlerts(state, items, today) {
  const sent = Object.fromEntries(Object.entries(state.sent ?? {}).filter(([key]) => key.endsWith(today)));
  const texts = [];
  for (const { key, text } of items) {
    if (sent[key]) continue;
    sent[key] = true;
    texts.push(text);
  }
  return { state: { ...state, sent }, texts };
}
