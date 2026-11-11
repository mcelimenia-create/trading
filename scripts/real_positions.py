"""Posiciones reales registradas por Telegram y avisos de la regla de salida.

Comandos (en el chat autorizado):
  entre TSLA 380.50 10     -> registra entrada (precio y acciones opcionales)
  sali TSLA 390 [4]        -> registra salida total o parcial (acciones opcionales)
  stop TSLA 370            -> cambia el stop de una posicion abierta
  riesgo TSLA 380 370      -> tamano en acciones y EUR con un riesgo maximo por operacion (entrada, stop)
  posiciones               -> lista las posiciones abiertas
  resumen                  -> precio, resultado, distancia al stop y regimen
  candidatos               -> candidatos del ultimo cierre
  ayuda                    -> comandos

El bot no compra ni vende. Solo registra lo que tu le dices y te avisa
cuando la regla de salida se cumple.
"""
import re
from datetime import date

import paper_trader
import sizing

TICKER = r"([A-Za-z.\-]{1,8})"
NUMBER = r"([\d.,]+)"
ENTRY_RE = re.compile(rf"^\s*entr[eé]\s+{TICKER}\s+{NUMBER}(?:\s+{NUMBER})?\s*$", re.I)
EXIT_RE = re.compile(rf"^\s*sal[ií]\s+{TICKER}\s+{NUMBER}(?:\s+{NUMBER})?\s*$", re.I)
STOP_RE = re.compile(rf"^\s*stop\s+{TICKER}\s+{NUMBER}\s*$", re.I)
RISK_RE = re.compile(rf"^\s*riesgo\s+{TICKER}\s+{NUMBER}\s+{NUMBER}\s*$", re.I)
HELP_TEXT = (
    "Comandos:\n"
    "entre TICKER PRECIO [ACCIONES]  - registrar entrada\n"
    "sali TICKER PRECIO [ACCIONES]  - registrar salida (total o parcial)\n"
    "stop TICKER PRECIO  - cambiar el stop\n"
    "riesgo TICKER ENTRADA STOP  - tamano en acciones y EUR\n"
    "posiciones  - ver posiciones abiertas\n"
    "resumen  - precio, resultado y distancia al stop\n"
    "candidatos  - candidatos del ultimo cierre\n"
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


def last_close(symbol, fetch):
    try:
        return fetch(symbol)[-1]["close"]
    except (OSError, KeyError, IndexError, ValueError):
        return None


def register_entry(state, symbol, entry, shares, today, fetch):
    stop = stop_reference(symbol, entry, fetch)
    position = {"symbol": symbol, "entry": entry, "shares": shares, "stop": stop,
                "entry_date": today, "last_alert": None}
    new_state = {**state, "open": state["open"] + [position]}
    stop_text = f"stop de referencia {stop:.2f} (2 ATR)" if stop else "sin stop: no pude calcular el ATR"
    return new_state, f"Registrada entrada en {symbol} a {entry:.2f}. {stop_text}."


def register_exit(state, symbol, price, today, shares=None):
    matches = [p for p in state["open"] if p["symbol"] == symbol]
    if not matches:
        return state, f"No tengo ninguna posicion abierta en {symbol}."
    position = matches[0]
    held = position.get("shares")
    if shares is not None and held is not None and shares > held:
        return state, f"No puedo vender {shares:g} acciones de {symbol}: solo tienes {held:g}."
    ret = (price - position["entry"]) / position["entry"]
    partial = shares is not None and held is not None and shares < held
    sold = shares if partial else held
    closed = {**position, "shares": sold, "exit": price, "ret": ret, "exit_date": today}
    if partial:
        remaining = {**position, "shares": held - shares}
        new_open = [remaining if p is position else p for p in state["open"]]
        kind = f"Salida parcial de {shares:g} acciones de {symbol}"
    else:
        new_open = [p for p in state["open"] if p is not position]
        kind = f"Registrada salida de {symbol}"
    new_state = {"open": new_open, "closed": state["closed"] + [closed]}
    return new_state, f"{kind} a {price:.2f}: resultado {100 * ret:+.2f}% (antes de impuestos y comisiones)."


def update_stop(state, symbol, stop):
    if not any(p["symbol"] == symbol for p in state["open"]):
        return state, f"No tengo ninguna posicion abierta en {symbol}."
    new_open = [{**p, "stop": stop} if p["symbol"] == symbol else p for p in state["open"]]
    return {**state, "open": new_open}, f"Stop de {symbol} cambiado a {stop:.2f}."


def list_open(state):
    if not state["open"]:
        return "No hay posiciones abiertas."
    lines = [f"{p['symbol']}: entrada {p['entry']:.2f} el {p['entry_date']}, stop {p['stop']:.2f}"
             if p["stop"] else f"{p['symbol']}: entrada {p['entry']:.2f} el {p['entry_date']}"
             for p in state["open"]]
    return "\n".join(lines)


def risk_text(symbol, entry, stop, market):
    if not market or not market.get("fx"):
        return "No tengo el tipo de cambio EUR/USD ahora mismo. Prueba mas tarde."
    try:
        size = sizing.size_position(entry, stop, market["fx"], market["cfg"], market["exposure_factor"])
    except ValueError as error:
        return f"{error}."
    if size["shares"] == 0:
        return "La comision consume el riesgo de la operacion: no compensa."
    cap = " (limitado al 20% de la cartera)" if size["capped"] else ""
    return (f"{symbol}: {size['shares']:.4f} acciones (~{size['position_eur']:.0f} EUR), riesgo maximo "
            f"{size['risk_eur']:.0f} EUR con comisiones{cap}. Regimen {market['state']}, "
            f"factor de exposicion {market['exposure_factor']}.")


def summary_text(state, fetch, market):
    if not state["open"]:
        return "No hay posiciones abiertas."
    lines = []
    for p in state["open"]:
        price = last_close(p["symbol"], fetch)
        if price is None:
            lines.append(f"{p['symbol']}: sin precio ahora")
            continue
        ret = (price - p["entry"]) / p["entry"]
        text = f"{p['symbol']}: precio {price:.2f} ({100 * ret:+.1f}%)"
        if p["stop"]:
            text += f", stop {p['stop']:.2f} a {100 * (price - p['stop']) / price:.1f}%"
        lines.append(text)
    if market:
        lines.append(f"Regimen: {market['state']}")
    return "\n".join(lines)


def candidates_text(market):
    found = (market or {}).get("candidates") or []
    if not found:
        return "No hay candidatos en el ultimo cierre."
    return "\n".join(f"{c['symbol']}: cierre {c['close']:.2f}, stop {c['stop']:.2f} ({c['date']})" for c in found)


def handle_command(state, text, fetch, today=None, market=None):
    today = today or date.today().isoformat()
    cleaned = text.strip().lower()
    if cleaned == "ayuda":
        return state, HELP_TEXT
    if cleaned == "posiciones":
        return state, list_open(state)
    if cleaned == "resumen":
        return state, summary_text(state, fetch, market)
    if cleaned == "candidatos":
        return state, candidates_text(market)
    entry_match = ENTRY_RE.match(text)
    if entry_match:
        symbol = entry_match.group(1).upper()
        shares = parse_number(entry_match.group(3)) if entry_match.group(3) else None
        return register_entry(state, symbol, parse_number(entry_match.group(2)), shares, today, fetch)
    exit_match = EXIT_RE.match(text)
    if exit_match:
        shares = parse_number(exit_match.group(3)) if exit_match.group(3) else None
        return register_exit(state, exit_match.group(1).upper(), parse_number(exit_match.group(2)), today, shares)
    stop_match = STOP_RE.match(text)
    if stop_match:
        return update_stop(state, stop_match.group(1).upper(), parse_number(stop_match.group(2)))
    risk_match = RISK_RE.match(text)
    if risk_match:
        symbol = risk_match.group(1).upper()
        entry, stop = parse_number(risk_match.group(2)), parse_number(risk_match.group(3))
        return state, risk_text(symbol, entry, stop, market)
    return state, "No entendi. Escribe 'ayuda'."


def weekly_review(state, today):
    """Repaso de tesis los domingos: una vez por semana. Devuelve (estado nuevo, texto o None)."""
    if date.fromisoformat(today).weekday() != 6 or state.get("last_review") == today:
        return state, None
    if not state["open"]:
        text = "Revision semanal: no hay posiciones abiertas."
    else:
        lines = [f"{p['symbol']}: revisa si la tesis sigue vigente; invalida si toca el stop {p['stop']:.2f}"
                 if p["stop"] else f"{p['symbol']}: revisa si la tesis sigue vigente"
                 for p in state["open"]]
        text = "REVISION SEMANAL DE TESIS\n" + "\n".join(lines)
    return {**state, "last_review": today}, text


def monthly_net_eur(state, today, fx):
    month = today[:7]
    return sum((c["exit"] - c["entry"]) * c["shares"] / fx
               for c in state["closed"]
               if c.get("exit_date", "")[:7] == month and c.get("shares"))


def limit_warnings(state, cfg, today, fx):
    """Avisos de limites de cartera: peso maximo por accion y perdida neta del mes (en EUR)."""
    if not fx:
        return []
    capital = cfg["capital_eur"]
    warnings = []
    for p in state["open"]:
        if not p.get("shares"):
            continue
        weight = p["shares"] * p["entry"] / fx / capital
        if weight > cfg["max_weight"]:
            warnings.append(f"{p['symbol']} pesa {100 * weight:.0f}% del capital, por encima del {100 * cfg['max_weight']:.0f}%.")
    net = monthly_net_eur(state, today, fx)
    if net <= -cfg["max_monthly_loss_pct"] * capital:
        warnings.append(f"Perdida neta del mes {net:.0f} EUR: alcanza el limite mensual del {100 * cfg['max_monthly_loss_pct']:.0f}%.")
    return warnings


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
