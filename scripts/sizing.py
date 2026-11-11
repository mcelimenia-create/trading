"""Tamano de posicion en EUR para Trade Republic (acciones fraccionadas).

Riesgo maximo por operacion = capital * risk_pct, descontando la comision de ida y vuelta.
Peso maximo = max_weight del capital. Los precios vienen en USD y se convierten con el cambio EUR/USD.
"""
import math

SHARE_DECIMALS = 4


def floor_shares(value):
    factor = 10 ** SHARE_DECIMALS
    return math.floor(value * factor + 1e-9) / factor


def size_position(entry_usd, stop_usd, fx_usd_per_eur, cfg, exposure_factor=1.0):
    if stop_usd >= entry_usd:
        raise ValueError("el stop debe estar por debajo de la entrada")
    capital = cfg["capital_eur"]
    commission = cfg["commission_eur"]
    entry_eur = entry_usd / fx_usd_per_eur
    stop_distance_eur = (entry_usd - stop_usd) / fx_usd_per_eur
    risk_budget = capital * cfg["risk_pct"] - 2 * commission
    if risk_budget <= 0:
        return {"shares": 0.0, "position_eur": 0.0, "risk_eur": 0.0, "weight": 0.0, "capped": False}
    shares_by_risk = risk_budget / stop_distance_eur
    shares_by_weight = capital * cfg["max_weight"] / entry_eur
    shares = floor_shares(min(shares_by_risk, shares_by_weight) * exposure_factor)
    position_eur = shares * entry_eur
    return {
        "shares": shares,
        "position_eur": round(position_eur, 2),
        "risk_eur": round(shares * stop_distance_eur + 2 * commission, 2),
        "weight": round(position_eur / capital, 4),
        "capped": shares_by_weight < shares_by_risk,
    }
