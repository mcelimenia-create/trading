"""Escaner de EEUU: propone acciones liquidas que cumplen hoy la regla de precio.

Solo propone. Cada propuesta necesita tu confirmacion antes de añadirla a la lista vigilada (CLAUDE.md).
El universo sale de la lista oficial de la SEC (NYSE y Nasdaq). Tiene presupuesto de tiempo: si se agota,
el mensaje dice cuantas acciones se revisaron.
"""
import re
import statistics
import time

import paper_trader

ALLOWED_EXCHANGES = {"NYSE", "Nasdaq"}
TICKER_RE = re.compile(r"[A-Z]{1,5}")
MIN_PRICE = 5.0
MIN_DOLLAR_VOLUME = 20_000_000
LIQUIDITY_DAYS = 20
SCAN_BUDGET_S = 2400
REQUEST_PAUSE_S = 0.2
SCAN_ERRORS = (OSError, KeyError, IndexError, ValueError)


TICKER_AT, EXCHANGE_AT = 2, 3   # fila SEC: [cik, nombre, ticker, bolsa]


def universe_from_sec(payload):
    return sorted({
        row[TICKER_AT] for row in payload["data"]
        if row[EXCHANGE_AT] in ALLOWED_EXCHANGES and TICKER_RE.fullmatch(row[TICKER_AT])
    })


def is_liquid(bars):
    if len(bars) < LIQUIDITY_DAYS or bars[-1]["close"] < MIN_PRICE:
        return False
    recent = bars[-LIQUIDITY_DAYS:]
    return statistics.median(b["close"] * b["volume"] for b in recent) >= MIN_DOLLAR_VOLUME


def scan_universe(symbols, fetch, budget_s=SCAN_BUDGET_S, clock=time.monotonic, pause_s=0.0):
    """Devuelve (propuestas, cuantas acciones se revisaron)."""
    start = clock()
    proposals, checked = [], 0
    for symbol in symbols:
        if clock() - start > budget_s:
            break
        checked += 1
        try:
            bars = fetch(symbol)
        except SCAN_ERRORS:
            continue
        finally:
            time.sleep(pause_s)
        last = len(bars) - 1
        if last < 0 or not is_liquid(bars) or not paper_trader.is_signal(bars, last):
            continue
        proposals.append({"symbol": symbol, "date": bars[last]["date"], "close": round(bars[last]["close"], 2)})
    return proposals, checked


def format_message(proposals, checked, total):
    head = (f"PROPUESTAS PARA VIGILAR (revisadas {checked} de {total} acciones de EEUU). "
            "No es una recomendacion ni una orden.")
    if not proposals:
        return head + "\nNinguna cumple hoy la regla."
    lines = [f"{p['symbol']}: cierre {p['close']:.2f} ({p['date']})" for p in proposals]
    return head + "\n" + "\n".join(lines) + "\nSi quieres vigilar alguna, dimelo y la añado."
