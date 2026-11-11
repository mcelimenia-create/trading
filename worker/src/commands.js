// Comandos de Telegram sobre las posiciones reales. Funciones puras: las dependencias (precios, mercado) se pasan.
import { atr, ATR_MULT, ATR_DAYS } from "./indicators.js";
import { sizePosition } from "./sizing.js";

const TICKER = "([a-z.\\-]{1,8})";
const NUMBER = "(\\d+(?:[.,]\\d+)?)";
const ENTRY_RE = new RegExp(`^entre\\s+${TICKER}\\s+${NUMBER}(?:\\s+${NUMBER})?$`);
const EXIT_RE = new RegExp(`^sali\\s+${TICKER}\\s+${NUMBER}(?:\\s+${NUMBER})?$`);
const STOP_RE = new RegExp(`^stop\\s+${TICKER}\\s+${NUMBER}$`);
const RISK_RE = new RegExp(`^riesgo\\s+${TICKER}\\s+${NUMBER}\\s+${NUMBER}$`);

export const HELP_TEXT = [
  "Comandos:",
  "entre TICKER PRECIO [ACCIONES]  - registrar entrada",
  "sali TICKER PRECIO [ACCIONES]  - registrar salida (total o parcial)",
  "stop TICKER PRECIO  - cambiar el stop",
  "riesgo TICKER ENTRADA STOP  - tamano en acciones y EUR",
  "posiciones  - ver posiciones abiertas",
  "resumen  - precio, resultado y distancia al stop",
  "candidatos  - candidatos del ultimo cierre",
  "No es una orden: solo registro y avisos.",
].join("\n");

export function emptyState() {
  return { open: [], closed: [] };
}

// Quita tildes y pasa a minusculas para que "SALÍ" o "sali" den igual.
export function normalize(text) {
  return text.normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase();
}

function num(text) {
  return Number(text.replace(",", "."));
}

function listOpen(state) {
  if (!state.open.length) return "No hay posiciones abiertas.";
  return state.open
    .map((p) => `${p.symbol}: entrada ${p.entry.toFixed(2)} el ${p.entry_date}` +
      (p.stop ? `, stop ${p.stop.toFixed(2)}` : ""))
    .join("\n");
}

async function registerEntry(state, symbol, entry, shares, today, d) {
  const bars = await d.getBars(symbol).catch(() => []);
  const stop = bars.length > ATR_DAYS ? entry - ATR_MULT * atr(bars, bars.length - 1) : null;
  const position = { symbol, entry, shares, stop, entry_date: today };
  const stopText = stop ? `stop de referencia ${stop.toFixed(2)} (2 ATR)` : "sin stop: no pude calcular el ATR";
  return {
    state: { ...state, open: [...state.open, position] },
    reply: `Registrada entrada en ${symbol} a ${entry.toFixed(2)}. ${stopText}.`,
  };
}

function registerExit(state, symbol, price, today, shares) {
  const position = state.open.find((p) => p.symbol === symbol);
  if (!position) return { state, reply: `No tengo ninguna posicion abierta en ${symbol}.` };
  if (shares !== null && shares <= 0) return { state, reply: "Las acciones a vender tienen que ser mayor que cero." };
  const held = position.shares;
  if (shares !== null && held !== null && shares > held) {
    return { state, reply: `No puedo vender ${shares} acciones de ${symbol}: solo tienes ${held}.` };
  }
  const ret = (price - position.entry) / position.entry;
  const partial = shares !== null && held !== null && shares < held;
  const sold = partial ? shares : held;
  const closed = { ...position, shares: sold, exit: price, ret, exit_date: today };
  const open = partial
    ? state.open.map((p) => (p === position ? { ...p, shares: held - shares } : p))
    : state.open.filter((p) => p !== position);
  const kind = partial ? `Salida parcial de ${shares} acciones de ${symbol}` : `Registrada salida de ${symbol}`;
  return {
    state: { open, closed: [...state.closed, closed] },
    reply: `${kind} a ${price.toFixed(2)}: resultado ${(100 * ret >= 0 ? "+" : "")}${(100 * ret).toFixed(2)}% (antes de impuestos y comisiones).`,
  };
}

function updateStop(state, symbol, stop) {
  if (!state.open.some((p) => p.symbol === symbol)) {
    return { state, reply: `No tengo ninguna posicion abierta en ${symbol}.` };
  }
  const open = state.open.map((p) => (p.symbol === symbol ? { ...p, stop } : p));
  return { state: { ...state, open }, reply: `Stop de ${symbol} cambiado a ${stop.toFixed(2)}.` };
}

function riskText(symbol, entry, stop, d) {
  if (!d.fx) return "No tengo el tipo de cambio EUR/USD ahora mismo. Prueba mas tarde.";
  let size;
  try {
    size = sizePosition(entry, stop, d.fx, d.cfg, d.exposureFactor);
  } catch (error) {
    return `${error.message}.`;
  }
  if (size.shares === 0) return "La comision consume el riesgo de la operacion: no compensa.";
  const cap = size.capped ? " (limitado al 20% de la cartera)" : "";
  return `${symbol}: ${size.shares.toFixed(4)} acciones (~${Math.round(size.position_eur)} EUR), ` +
    `riesgo maximo ${size.risk_eur.toFixed(0)} EUR con comisiones${cap}. ` +
    `Regimen ${d.regimeState}, factor de exposicion ${d.exposureFactor}.`;
}

async function summaryText(state, d) {
  if (!state.open.length) return "No hay posiciones abiertas.";
  const lines = [];
  for (const p of state.open) {
    const price = await d.getLastClose(p.symbol).catch(() => null);
    if (price === null) {
      lines.push(`${p.symbol}: sin precio ahora`);
      continue;
    }
    const ret = (price - p.entry) / p.entry;
    let line = `${p.symbol}: precio ${price.toFixed(2)} (${100 * ret >= 0 ? "+" : ""}${(100 * ret).toFixed(1)}%)`;
    if (p.stop) line += `, stop ${p.stop.toFixed(2)} a ${(100 * (price - p.stop) / price).toFixed(1)}%`;
    lines.push(line);
  }
  lines.push(`Regimen: ${d.regimeState}`);
  return lines.join("\n");
}

async function candidatesText(d) {
  const found = await d.getCandidates().catch(() => []);
  if (!found.length) return "No hay candidatos en el ultimo cierre.";
  return found
    .map((c) => `${c.symbol}: cierre ${c.close.toFixed(2)}, stop ${c.stop.toFixed(2)} (${c.date})`)
    .join("\n");
}

// Devuelve { state, reply }. Nunca lanza por un texto no reconocido.
export async function handleCommand(state, rawText, d) {
  const text = normalize(rawText);
  if (text === "ayuda") return { state, reply: HELP_TEXT };
  if (text === "posiciones") return { state, reply: listOpen(state) };
  if (text === "resumen") return { state, reply: await summaryText(state, d) };
  if (text === "candidatos") return { state, reply: await candidatesText(d) };

  const entry = text.match(ENTRY_RE);
  if (entry) {
    const symbol = entry[1].toUpperCase();
    const shares = entry[3] ? num(entry[3]) : null;
    return registerEntry(state, symbol, num(entry[2]), shares, d.today, d);
  }
  const exit = text.match(EXIT_RE);
  if (exit) {
    const shares = exit[3] ? num(exit[3]) : null;
    return registerExit(state, exit[1].toUpperCase(), num(exit[2]), d.today, shares);
  }
  const stop = text.match(STOP_RE);
  if (stop) return updateStop(state, stop[1].toUpperCase(), num(stop[2]));
  const risk = text.match(RISK_RE);
  if (risk) {
    return { state, reply: riskText(risk[1].toUpperCase(), num(risk[2]), num(risk[3]), d) };
  }
  return { state, reply: "No entendi. Escribe 'ayuda'." };
}
