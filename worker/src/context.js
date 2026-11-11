// Fecha de Nueva York y contexto de mercado (regimen y tipo de cambio), compartidos por el webhook y el cron.
import { PORTFOLIO } from "./config.js";
import { fetchBars } from "./market.js";
import { classifyRegime } from "./regime.js";

export function todayNewYork() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
}

export async function marketContext() {
  const spec = PORTFOLIO.regime;
  const [index, growth, vix] = await Promise.all([
    fetchBars(spec.index, "2y"), fetchBars(spec.growth_index, "2y"), fetchBars(spec.volatility, "1mo"),
  ]).catch(() => [[], [], []]);
  const regime = classifyRegime(
    index.map((b) => b.close),
    growth.map((b) => b.close),
    vix.length ? vix[vix.length - 1].close : NaN,
    PORTFOLIO,
  );
  const fx = await fetchBars(spec.fx, "1mo").then((b) => b[b.length - 1].close).catch(() => null);
  return { regime, fx };
}
