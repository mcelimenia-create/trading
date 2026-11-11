"""Candidatos de medio plazo: acciones que cumplen hoy la regla de precio.

Solo avisa. Cada candidato trae su stop de referencia y la condicion que la invalida.
Los datos se guardan en docs/data/candidates.json (no contienen datos personales).
"""
import json
import os
from datetime import date

import fundamentals
import paper_trader

GROWTH_THRESHOLD = 0.15
DISCLAIMER = "Candidatos segun una regla de precio. No es una recomendacion personal ni una orden."


def describe(symbol, bars, growth_text):
    last = len(bars) - 1
    entry = bars[last]["close"]
    stop = entry - paper_trader.ATR_MULT * paper_trader.atr(bars, last)
    trailing = min(b["low"] for b in bars[last - paper_trader.TRAIL_DAYS:last])
    return {
        "symbol": symbol, "date": bars[last]["date"], "close": round(entry, 2),
        "stop": round(stop, 2), "invalidation": f"cierre bajo {trailing:.2f} (minimo de 10 dias) o toque del stop",
        "growth": growth_text,
    }


def growth_text(symbol, day):
    if not fundamentals.sec_user_agent():
        return "sin datos (falta SEC_USER_AGENT)"
    try:
        records = fundamentals.growth_for(symbol)
    except (OSError, KeyError, ValueError):
        return "no disponible"
    value = fundamentals.latest_growth(records, day)
    if value is None:
        return "sin datos"
    flag = " (supera 15%)" if value > GROWTH_THRESHOLD else ""
    return f"{100 * value:+.1f}% interanual{flag}"


def scan(tickers):
    found, failed = [], []
    for symbol in tickers:
        try:
            bars = paper_trader.fetch_bars(symbol)
        except (OSError, KeyError, IndexError, ValueError):
            failed.append(symbol)
            continue
        last = len(bars) - 1
        if last < 0 or not paper_trader.is_signal(bars, last):
            continue
        found.append(describe(symbol, bars, growth_text(symbol, bars[last]["date"])))
    return found, failed


def format_message(found):
    if not found:
        return None
    lines = [
        f"{c['symbol']}: cierre {c['close']:.2f}, stop de referencia {c['stop']:.2f}. "
        f"Ingresos: {c['growth']}. Invalida si: {c['invalidation']}."
        for c in found
    ]
    return DISCLAIMER + "\n\nCANDIDATOS DE MEDIO PLAZO (" + found[0]["date"] + ")\n\n" + "\n".join(lines)


def write_public_file(found, path):
    doc = {"generated": date.today().isoformat(), "note": DISCLAIMER, "candidates": found}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def candidates_job(notify, tickers, public_path):
    found, failed = scan(tickers)
    write_public_file(found, public_path)
    message = format_message(found)
    if message:
        notify(message)
    else:
        print("Sin candidatos hoy")
    if failed:
        print("Sin datos para: " + ", ".join(failed))
