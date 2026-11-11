"""Posiciones reales registradas por Telegram y avisos de la regla de salida.

Comandos (en el chat autorizado):
  entre TSLA 380.50 10     -> registra entrada (precio y acciones opcionales)
  sali TSLA 390            -> registra salida
  posiciones               -> lista las posiciones abiertas
  ayuda                    -> comandos

El bot no compra ni vende. Solo registra lo que tu le dices y te avisa
cuando la regla de salida se cumple.
"""
import re
from datetime import date

import paper_trader

ENTRY_RE = re.compile(r"^\s*entr[eé]\s+([A-Za-z.\-]{1,8})\s+([\d.,]+)(?:\s+([\d.,]+))?\s*$", re.I)
EXIT_RE = re.compile(r"^\s*sal[ií]\s+([A-Za-z.\-]{1,8})\s+([\d.,]+)\s*$", re.I)
HELP_TEXT = (
    "Comandos:\n"
    "entre TICKER PRECIO [ACCIONES]  - registrar entrada\n"
    "sali TICKER PRECIO  - registrar salida\n"
    "posiciones  - ver posiciones abiertas\n"
    "No es una orden: solo registro y avisos."
)


def parse_number(text):
    return float(text.replace(",", "."))


def empty_real_state():
    return {"open": [], "closed": []}


def stop_reference(symbol, entry, fetch):
    try:
        bars = fetch(symbol)
    except (OSError, KeyError, IndexError, ValueError):
        return None
    if len(bars) < paper_trader.ATR_DAYS + 1:
        return None
    return entry - paper_trader.ATR_MULT * paper_trader.atr(bars, len(bars) - 1)


def register_entry(state, symbol, entry, shares, today, fetch):
    stop = stop_reference(symbol, entry, fetch)
    position = {"symbol": symbol, "entry": entry, "shares": shares, "stop": stop,
                "entry_date": today, "last_alert": None}
    new_state = {**state, "open": state["open"] + [position]}
    stop_text = f"stop de referencia {stop:.2f} (2 ATR)" if stop else "sin stop: no pude calcular el ATR"
    return new_state, f"Registrada entrada en {symbol} a {entry:.2f}. {stop_text}."


def register_exit(state, symbol, price):
    matches = [p for p in state["open"] if p["symbol"] == symbol]
    if not matches:
        return state, f"No tengo ninguna posicion abierta en {symbol}."
    position = matches[0]
    ret = (price - position["entry"]) / position["entry"]
    closed = {**position, "exit": price, "ret": ret}
    new_state = {"open": [p for p in state["open"] if p is not position],
                 "closed": state["closed"] + [closed]}
    return new_state, f"Registrada salida de {symbol} a {price:.2f}: resultado {100 * ret:+.2f}% (antes de impuestos y comisiones)."


def list_open(state):
    if not state["open"]:
        return "No hay posiciones abiertas."
    lines = [f"{p['symbol']}: entrada {p['entry']:.2f} el {p['entry_date']}, stop {p['stop']:.2f}"
             if p["stop"] else f"{p['symbol']}: entrada {p['entry']:.2f} el {p['entry_date']}"
             for p in state["open"]]
    return "\n".join(lines)


def handle_command(state, text, fetch, today=None):
    today = today or date.today().isoformat()
    cleaned = text.strip().lower()
    if cleaned == "ayuda":
        return state, HELP_TEXT
    if cleaned == "posiciones":
        return state, list_open(state)
    entry_match = ENTRY_RE.match(text)
    if entry_match:
        symbol = entry_match.group(1).upper()
        shares = parse_number(entry_match.group(3)) if entry_match.group(3) else None
        return register_entry(state, symbol, parse_number(entry_match.group(2)), shares, today, fetch)
    exit_match = EXIT_RE.match(text)
    if exit_match:
        return register_exit(state, exit_match.group(1).upper(), parse_number(exit_match.group(2)))
    return state, "No entendi. Escribe 'ayuda'."


def exit_alerts(position, bars):
    """Avisos de la regla de salida para una posicion abierta (pura, sin red)."""
    dates = [b["date"] for b in bars]
    if position["entry_date"] not in dates:
        return []
    start = dates.index(position["entry_date"])
    alerts = []
    last = len(bars) - 1
    if last <= start or last < paper_trader.TRAIL_DAYS:
        return alerts
    if position["stop"] is not None and bars[last]["low"] <= position["stop"]:
        alerts.append(("stop", f"toco el stop de referencia {position['stop']:.2f} el {bars[last]['date']}"))
    if bars[last]["close"] < min(b["low"] for b in bars[last - paper_trader.TRAIL_DAYS:last]):
        alerts.append(("trailing", f"el cierre {bars[last]['close']:.2f} perdio el minimo de 10 dias"))
    return alerts


def monitor(state, fetch, today=None):
    """Devuelve (estado nuevo, avisos). Cada aviso se envia una sola vez por dia."""
    today = today or date.today().isoformat()
    messages, new_open = [], []
    for position in state["open"]:
        try:
            bars = fetch(position["symbol"])
        except (OSError, KeyError, IndexError, ValueError):
            new_open.append(position)
            continue
        alerts = exit_alerts(position, bars)
        if alerts and position.get("last_alert") != today:
            detail = "; ".join(text for _, text in alerts)
            messages.append(f"{position['symbol']}: {detail}. Regla de salida cumplida: revisa si sales.")
            position = {**position, "last_alert": today}
        new_open.append(position)
    return {**state, "open": new_open}, messages
