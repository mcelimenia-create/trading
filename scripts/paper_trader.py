#!/usr/bin/env python3
"""Cartera de papel: registra las senales de la regla de precio y su resultado.

Regla (fijada antes de probarla fuera de muestra):
  - Senal: cierre por encima de la media de 200 dias y del maximo de los 60 dias anteriores.
  - Entrada: apertura de la sesion siguiente a la senal.
  - Stop: 2 veces el ATR de 14 dias bajo la entrada.
  - Salida: stop, o cierre que pierde el minimo de los 10 dias anteriores, o 500 sesiones.
  - Tamano de referencia: 2% de riesgo sobre la cartera, con maximo 20% en una accion.
  - Coste: 0,2% por operacion.

No opera con dinero. Solo registra y avisa.
"""
import copy
import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

PAPER_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range={span}&interval=1d"
USER_AGENT = "Mozilla/5.0"
HTTP_TIMEOUT_S = 20
SMA_DAYS = 200
BREAKOUT_DAYS = 60
TRAIL_DAYS = 10
ATR_DAYS = 14
ATR_MULT = 2
MAX_HOLD_DAYS = 500
RISK_PCT = 0.02
MAX_WEIGHT = 0.20
COST = 0.002
DISCLAIMER = "PAPEL: simulacion. No es una orden ni una recomendacion personal."


def fetch_bars(symbol, span="5y"):
    url = PAPER_URL.format(symbol=urllib.parse.quote(symbol, safe=""), span=span)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        result = json.loads(response.read())["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    bars = []
    for ts, o, h, l, c in zip(result["timestamp"], quote["open"], quote["high"], quote["low"], quote["close"]):
        if None in (o, h, l, c):
            continue
        bars.append({
            "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
            "open": o, "high": h, "low": l, "close": c,
        })
    return bars


def sma(values, n):
    return sum(values[-n:]) / n


def atr(bars, i):
    trs = []
    for k in range(i - ATR_DAYS + 1, i + 1):
        high, low, prev_close = bars[k]["high"], bars[k]["low"], bars[k - 1]["close"]
        trs.append(max(high - low, abs(high - prev_close), abs(low - prev_close)))
    return sum(trs) / ATR_DAYS


def is_signal(bars, i):
    if i < max(SMA_DAYS, BREAKOUT_DAYS + 1):
        return False
    closes = [b["close"] for b in bars[: i + 1]]
    return closes[-1] > sma(closes, SMA_DAYS) and closes[-1] > max(closes[-BREAKOUT_DAYS - 1:-1])


def weight_for(entry, stop):
    stop_pct = (entry - stop) / entry
    return min(RISK_PCT / stop_pct, MAX_WEIGHT) if stop_pct > 0 else MAX_WEIGHT


def empty_state():
    return {"pending": [], "positions": [], "closed": []}


def fill_pending(state, symbol, bars, dates):
    events = []
    for pending in [p for p in state["pending"] if p["symbol"] == symbol]:
        if pending["signal_date"] not in dates:
            state["pending"].remove(pending)
            continue
        later = [j for j, d in enumerate(dates) if d > pending["signal_date"]]
        if not later:
            continue
        j = later[0]
        signal_i = dates.index(pending["signal_date"])
        entry = bars[j]["open"]
        stop = entry - ATR_MULT * atr(bars, signal_i)
        position = {
            "symbol": symbol, "signal_date": pending["signal_date"], "entry_date": dates[j],
            "entry": entry, "stop": stop, "weight": weight_for(entry, stop),
        }
        state["pending"].remove(pending)
        state["positions"].append(position)
        events.append(("ENTRADA", position))
    return events


def exit_for_bar(bars, start, k, stop):
    b = bars[k]
    if b["open"] <= stop:
        return b["open"], "STOP"
    if b["low"] <= stop:
        return stop, "STOP"
    if k > start and b["close"] < min(x["low"] for x in bars[k - TRAIL_DAYS:k]):
        return b["close"], "TRAILING"
    if k - start >= MAX_HOLD_DAYS:
        return b["close"], "TIEMPO"
    return None


def manage_positions(state, symbol, bars, dates):
    events = []
    for position in [p for p in state["positions"] if p["symbol"] == symbol]:
        if position["entry_date"] not in dates:
            continue
        start = dates.index(position["entry_date"])
        for k in range(start, len(bars)):
            found = exit_for_bar(bars, start, k, position["stop"])
            if found is None:
                continue
            price, reason = found
            closed = dict(
                position, exit_date=dates[k], exit=price, reason=reason,
                ret=(price - position["entry"]) / position["entry"] - COST,
            )
            state["positions"].remove(position)
            state["closed"].append(closed)
            events.append(("SALIDA", closed))
            break
    return events


def add_new_signal(state, symbol, bars, dates):
    last = len(bars) - 1
    if last < 0 or not is_signal(bars, last):
        return []
    if any(p["symbol"] == symbol for p in state["pending"] + state["positions"]):
        return []
    stop_estimate = bars[last]["close"] - ATR_MULT * atr(bars, last)
    pending = {"symbol": symbol, "signal_date": dates[last], "signal_close": bars[last]["close"],
               "stop_estimate": stop_estimate}
    state["pending"].append(pending)
    return [("SENAL", pending)]


def run_day(state, bars_by_symbol):
    """Advances the paper book one day. bars_by_symbol: {symbol: bars up to today}."""
    new_state = copy.deepcopy(state)
    events = []
    for symbol, bars in bars_by_symbol.items():
        if not bars:
            continue
        dates = [b["date"] for b in bars]
        events += fill_pending(new_state, symbol, bars, dates)
        events += manage_positions(new_state, symbol, bars, dates)
        events += add_new_signal(new_state, symbol, bars, dates)
    return new_state, events


def summary(closed):
    if not closed:
        return "todavia no hay operaciones cerradas"
    rets = [c["ret"] for c in closed]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    factor = sum(wins) / abs(sum(losses)) if losses else float("inf")
    return "cerradas %d, acierto %.0f%%, media %+.2f%%, factor %.2f" % (
        len(rets), 100 * len(wins) / len(rets), 100 * mean(rets), factor)


def format_events(events):
    lines = []
    for kind, item in events:
        if kind == "SENAL":
            lines.append(
                f"SENAL {item['symbol']} (cierre {item['signal_close']:.2f} del {item['signal_date']}). "
                f"Entrada prevista en la apertura siguiente. Stop orientativo {item['stop_estimate']:.2f}."
            )
        elif kind == "ENTRADA":
            lines.append(
                f"ENTRADA SIMULADA {item['symbol']} a {item['entry']:.2f} ({item['entry_date']}). "
                f"Stop {item['stop']:.2f}. Tamano de referencia {100 * item['weight']:.1f}% de la cartera."
            )
        else:
            lines.append(
                f"SALIDA SIMULADA {item['symbol']} por {item['reason']} a {item['exit']:.2f} "
                f"({item['exit_date']}), resultado {100 * item['ret']:+.2f}%."
            )
    return "\n".join(lines)


def load_state(path):
    if not path.exists():
        return empty_state()
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(path, state):
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def paper_job(notify, tickers, state_path):
    bars_by_symbol = {}
    failed = []
    for symbol in tickers:
        try:
            bars_by_symbol[symbol] = fetch_bars(symbol)
        except (OSError, KeyError, IndexError, ValueError):
            failed.append(symbol)
    state, events = run_day(load_state(state_path), bars_by_symbol)
    save_state(state_path, state)
    if events:
        text = DISCLAIMER + "\n\n" + format_events(events) + "\n\nResumen: " + summary(state["closed"])
        notify(text)
    else:
        print("Sin novedades en la cartera de papel")
    if failed:
        print("Sin datos para: " + ", ".join(failed))
