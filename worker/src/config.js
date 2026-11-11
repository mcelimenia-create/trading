// Copia de config/portfolio.json del repositorio. Si cambias uno, cambia el otro.
export const PORTFOLIO = {
  capital_eur: 700,
  risk_pct: 0.02,
  max_weight: 0.2,
  max_monthly_loss_pct: 0.05,
  commission_eur: 1.0,
  regime: {
    index: "SPY",
    growth_index: "QQQ",
    volatility: "^VIX",
    fx: "EURUSD=X",
    sma_days: 200,
    vix_max: 25,
  },
  earnings_window_days: 10,
};
