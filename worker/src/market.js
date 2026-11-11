// Barras diarias desde Yahoo Finance (sin clave). Descarta las sesiones sin precio.
const CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range={span}&interval=1d";

export async function fetchBars(symbol, span = "5y") {
  const url = CHART_URL.replace("{symbol}", encodeURIComponent(symbol)).replace("{span}", span);
  const res = await fetch(url, { headers: { "User-Agent": "Mozilla/5.0" } });
  if (!res.ok) throw new Error(`Yahoo ${symbol} ${res.status}`);
  const result = (await res.json()).chart.result[0];
  const quote = result.indicators.quote[0];
  const volumes = quote.volume ?? [];
  const bars = [];
  result.timestamp.forEach((ts, i) => {
    const { open, high, low, close } = { open: quote.open[i], high: quote.high[i], low: quote.low[i], close: quote.close[i] };
    if ([open, high, low, close].some((v) => v === null || v === undefined)) return;
    bars.push({
      date: new Date(ts * 1000).toISOString().slice(0, 10),
      open, high, low, close, volume: volumes[i] ?? 0,
    });
  });
  return bars;
}
