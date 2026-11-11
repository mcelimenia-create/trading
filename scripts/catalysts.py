"""Resultados trimestrales proximos (catalizador) para posiciones y candidatos.

Fuente: calendario de resultados de Finnhub. Necesita la variable FINNHUB_API_KEY; sin ella no hay avisos.
"""
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

EARNINGS_URL = "https://finnhub.io/api/v1/calendar/earnings?{query}"
HTTP_TIMEOUT_S = 20


def upcoming(events, symbols, today, days):
    """Resultados de 'symbols' entre hoy y hoy + days. events: [{"symbol", "date"}]."""
    start = date.fromisoformat(today)
    end = start + timedelta(days=days)
    wanted = set(symbols)
    return sorted(
        (e["symbol"], e["date"]) for e in events
        if e["symbol"] in wanted and start <= date.fromisoformat(e["date"]) <= end
    )


def fetch_earnings(start, end, token):
    query = urllib.parse.urlencode({"from": start, "to": end, "token": token})
    with urllib.request.urlopen(EARNINGS_URL.format(query=query), timeout=HTTP_TIMEOUT_S) as response:
        return json.loads(response.read()).get("earningsCalendar", [])


def earnings_soon(symbols, today, days, token, fetch=fetch_earnings):
    """Lista de (simbolo, fecha). None si no hay clave o la consulta falla."""
    if not token or not symbols:
        return None
    start = date.fromisoformat(today)
    try:
        events = fetch(start.isoformat(), (start + timedelta(days=days)).isoformat(), token)
    except (OSError, ValueError, KeyError):
        return None
    return upcoming(events, symbols, today, days)
