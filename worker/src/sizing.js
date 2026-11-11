// Tamano de posicion en EUR (acciones fraccionadas). Precios en USD; fx = USD por EUR.

const SHARE_DECIMALS = 4;

export function floorShares(value) {
  const factor = 10 ** SHARE_DECIMALS;
  return Math.floor(value * factor + 1e-9) / factor;
}

export function sizePosition(entryUsd, stopUsd, fxUsdPerEur, cfg, exposureFactor = 1) {
  if (stopUsd >= entryUsd) throw new Error("el stop debe estar por debajo de la entrada");
  const capital = cfg.capital_eur;
  const commission = cfg.commission_eur;
  const entryEur = entryUsd / fxUsdPerEur;
  const stopDistanceEur = (entryUsd - stopUsd) / fxUsdPerEur;
  const riskBudget = capital * cfg.risk_pct - 2 * commission;
  if (riskBudget <= 0) return { shares: 0, position_eur: 0, risk_eur: 0, weight: 0, capped: false };
  const sharesByRisk = riskBudget / stopDistanceEur;
  const sharesByWeight = (capital * cfg.max_weight) / entryEur;
  const shares = floorShares(Math.min(sharesByRisk, sharesByWeight) * exposureFactor);
  const positionEur = shares * entryEur;
  return {
    shares,
    position_eur: Math.round(positionEur * 100) / 100,
    risk_eur: Math.round((shares * stopDistanceEur + 2 * commission) * 100) / 100,
    weight: Math.round((positionEur / capital) * 10000) / 10000,
    capped: sharesByWeight < sharesByRisk,
  };
}
