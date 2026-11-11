"""Candidatos de medio plazo: acciones que cumplen hoy la regla de precio.

Solo avisa. Cada candidato trae su stop de referencia, el tamano en EUR y la condicion que la invalida.
Los datos se guardan en docs/data/candidates.json (no contienen datos personales).
"""
import json
from datetime import date

import fundamentals
import paper_trader
import regime
import sizing

GROWTH_THRESHOLD = 0.15
DISCLAIMER = "Candidatos segun una regla de precio. No es una recomendacion personal ni una orden."
SCAN_ERRORS = (OSError, KeyError, IndexError, ValueError)


def describe(symbol, bars, growth_text, cfg, fx, exposure_factor):
    last = len(bars) - 1
    entry = bars[last]["close"]
    stop = entry - paper_trader.ATR_MULT * paper_trader.atr(bars, last)
    trailing = min(b["low"] for b in bars[last - paper_trader.TRAIL_DAYS:last])
    size = None
    if fx:
        size = sizing.size_position(entry, stop, fx, cfg, exposure_factor)
    return {
        "symbol": symbol, "date": bars[last]["date"], "close": round(entry, 2),
        "stop": round(stop, 2), "invalidation": f"cierre bajo {trailing:.2f} (minimo de 10 dias) o toque del stop",
        "growth": growth_text, "size": size,
    }


def growth_text(symbol, day):
    if not fundamentals.sec_user_agent():
        return "sin datos (falta SEC_USER_AGENT)"
    try:
        records = fundamentals.growth_for(symbol)
    except SCAN_ERRORS:
        return "no disponible"
    value = fundamentals.latest_growth(records, day)
    if value is None:
        return "sin datos"
    flag = " (supera 15%)" if value > GROWTH_THRESHOLD else ""
    return f"{100 * value:+.1f}% interanual{flag}"


def scan(tickers, cfg, fx, exposure_factor):
    found, failed = [], []
    for symbol in tickers:
        try:
            bars = paper_trader.fetch_bars(symbol)
        except SCAN_ERRORS:
            failed.append(symbol)
            continue
        last = len(bars) - 1
        if last < 0 or not paper_trader.is_signal(bars, last):
            continue
        found.append(describe(symbol, bars, growth_text(symbol, bars[last]["date"]), cfg, fx, exposure_factor))
    return found, failed


def regime_line(state):
    if state["state"] == "normal":
        return "Regimen: normal"
    reasons = "; ".join(state["reasons"]) or "sin datos suficientes"
    return f"Regimen: {state['state']} ({reasons}). Tamano reducido a la mitad."


def size_text(size):
    if size is None:
        return "tamano en EUR no disponible (sin tipo de cambio)"
    if size["shares"] == 0:
        return "tamano en EUR: la comision consume el riesgo de la operacion"
    cap = " (limitado al 20% de la cartera)" if size["capped"] else ""
    return (f"tamano {size['shares']:.4f} acciones (~{size['position_eur']:.0f} EUR, "
            f"riesgo maximo {size['risk_eur']:.0f} EUR){cap}")


def format_message(found, state):
    if not found:
        return None
    lines = [
        f"{c['symbol']}: cierre {c['close']:.2f}, stop de referencia {c['stop']:.2f}. "
        f"Ingresos: {c['growth']}. {size_text(c['size'])}. Invalida si: {c['invalidation']}."
        for c in found
    ]
    return (DISCLAIMER + "\n" + regime_line(state) + "\n\nCANDIDATOS DE MEDIO PLAZO (" + found[0]["date"] + ")\n\n"
            + "\n".join(lines))


def write_public_file(found, state, fx, path):
    doc = {"generated": date.today().isoformat(), "note": DISCLAIMER, "regime": state,
           "usd_per_eur": fx, "candidates": found}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def candidates_job(notify, tickers, public_path, cfg):
    state, fx = regime.fetch_context(cfg)
    found, failed = scan(tickers, cfg, fx, state["exposure_factor"])
    write_public_file(found, state, fx, public_path)
    message = format_message(found, state)
    if message:
        notify(message)
    else:
        print("Sin candidatos hoy")
    if failed:
        print("Sin datos para: " + ", ".join(failed))
