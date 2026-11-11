// Regimen de mercado: SPY y QQQ frente a su media de 200 sesiones, y VIX.
import { sma } from "./indicators.js";

export const NORMAL_FACTOR = 1;
export const RISK_FACTOR = 0.5;

export function classifyRegime(indexCloses, growthCloses, vixLast, cfg) {
  const days = cfg.regime.sma_days;
  if (indexCloses.length < days || growthCloses.length < days || Number.isNaN(vixLast)) {
    return { state: "desconocido", reasons: ["historico insuficiente"], exposure_factor: RISK_FACTOR };
  }
  const reasons = [];
  if (indexCloses[indexCloses.length - 1] < sma(indexCloses, days)) {
    reasons.push(`SPY por debajo de su media de ${days} sesiones`);
  }
  if (growthCloses[growthCloses.length - 1] < sma(growthCloses, days)) {
    reasons.push(`QQQ por debajo de su media de ${days} sesiones`);
  }
  if (vixLast > cfg.regime.vix_max) {
    reasons.push(`VIX en ${vixLast.toFixed(1)}, por encima de ${cfg.regime.vix_max}`);
  }
  if (reasons.length) return { state: "riesgo", reasons, exposure_factor: RISK_FACTOR };
  return { state: "normal", reasons: [], exposure_factor: NORMAL_FACTOR };
}
