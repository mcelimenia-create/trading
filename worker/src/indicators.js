// Indicadores sobre barras diarias: [{ date, open, high, low, close, volume }] ordenadas de antigua a reciente.

export const ATR_DAYS = 14;
export const ATR_MULT = 2;
export const SMA_DAYS = 200;
export const BREAKOUT_DAYS = 60;
export const TRAIL_DAYS = 10;

export function sma(values, n) {
  const slice = values.slice(-n);
  return slice.reduce((a, b) => a + b, 0) / n;
}

export function atr(bars, i) {
  let sum = 0;
  for (let k = i - ATR_DAYS + 1; k <= i; k++) {
    const { high, low } = bars[k];
    const prevClose = bars[k - 1].close;
    sum += Math.max(high - low, Math.abs(high - prevClose), Math.abs(low - prevClose));
  }
  return sum / ATR_DAYS;
}

// Senal de la regla de precio: cierre sobre la media de 200 dias y sobre el maximo de los 60 anteriores.
export function isSignal(bars, i) {
  if (i < Math.max(SMA_DAYS, BREAKOUT_DAYS + 1)) return false;
  const closes = bars.slice(0, i + 1).map((b) => b.close);
  const last = closes[closes.length - 1];
  const highest = Math.max(...closes.slice(-BREAKOUT_DAYS - 1, -1));
  return last > sma(closes, SMA_DAYS) && last > highest;
}
