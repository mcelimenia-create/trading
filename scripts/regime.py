"""Regimen de mercado: SPY y QQQ frente a su media de 200 sesiones, y nivel del VIX.

Si hay algun motivo de riesgo, el factor de exposicion baja a la mitad (CLAUDE.md).
"""
import math
from statistics import mean

import paper_trader

NORMAL_FACTOR = 1.0
RISK_FACTOR = 0.5


def classify(index_closes, growth_closes, vix_last, cfg):
    days = cfg["regime"]["sma_days"]
    if len(index_closes) < days or len(growth_closes) < days or math.isnan(vix_last):
        return {"state": "desconocido", "reasons": ["historico insuficiente"], "exposure_factor": RISK_FACTOR}
    reasons = []
    if index_closes[-1] < mean(index_closes[-days:]):
        reasons.append(f"SPY por debajo de su media de {days} sesiones")
    if growth_closes[-1] < mean(growth_closes[-days:]):
        reasons.append(f"QQQ por debajo de su media de {days} sesiones")
    if vix_last > cfg["regime"]["vix_max"]:
        reasons.append(f"VIX en {vix_last:.1f}, por encima de {cfg['regime']['vix_max']}")
    if reasons:
        return {"state": "riesgo", "reasons": reasons, "exposure_factor": RISK_FACTOR}
    return {"state": "normal", "reasons": [], "exposure_factor": NORMAL_FACTOR}


def fetch_context(cfg):
    """Regimen y cambio EUR/USD (USD por EUR). Sin datos, el regimen queda 'desconocido' y el tipo None."""
    spec = cfg["regime"]
    try:
        index = paper_trader.fetch_bars(spec["index"])
        growth = paper_trader.fetch_bars(spec["growth_index"])
        vix = paper_trader.fetch_bars(spec["volatility"])
    except (OSError, KeyError, IndexError, ValueError):
        index, growth, vix = [], [], None
    state = classify(
        [b["close"] for b in index], [b["close"] for b in growth],
        vix[-1]["close"] if vix else float("nan"), cfg,
    )
    return state, fx_usd_per_eur(cfg)


def fx_usd_per_eur(cfg):
    """Cambio EUR/USD (USD por EUR) del ultimo cierre, o None si no hay datos."""
    try:
        return paper_trader.fetch_bars(cfg["regime"]["fx"])[-1]["close"]
    except (OSError, KeyError, IndexError, ValueError):
        return None
