// Webhook de Telegram: responde a los comandos al instante.
import { handleCommand } from "./commands.js";
import { PORTFOLIO } from "./config.js";
import { fetchBars } from "./market.js";
import { classifyRegime } from "./regime.js";
import { loadState, saveState } from "./store.js";
import { sendMessage } from "./telegram.js";

const CANDIDATES_URL = "https://raw.githubusercontent.com/mcelimenia-create/trading/main/docs/data/candidates.json";

function todayNewYork() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/New_York" }).format(new Date());
}

async function marketContext() {
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

async function candidates() {
  const res = await fetch(CANDIDATES_URL);
  if (!res.ok) throw new Error(`candidatos ${res.status}`);
  return (await res.json()).candidates ?? [];
}

async function processText(text, env) {
  const state = await loadState(env.DB);
  const market = await marketContext();
  const deps = {
    today: todayNewYork(),
    cfg: PORTFOLIO,
    fx: market.fx,
    exposureFactor: market.regime.exposure_factor,
    regimeState: market.regime.state,
    getBars: (symbol) => fetchBars(symbol, "6mo"),
    getLastClose: (symbol) => fetchBars(symbol, "1mo").then((b) => b[b.length - 1].close),
    getCandidates: candidates,
  };
  const result = await handleCommand(state, text, deps);
  await saveState(env.DB, result.state);
  return result.reply;
}

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return new Response("ok");
    if (request.headers.get("X-Telegram-Bot-Api-Secret-Token") !== env.WEBHOOK_SECRET) {
      return new Response("forbidden", { status: 403 });
    }
    const update = await request.json();
    const message = update.message;
    if (!message || typeof message.text !== "string" || String(message.chat?.id) !== String(env.TELEGRAM_CHAT_ID)) {
      return new Response("ignored");
    }
    let reply;
    try {
      reply = await processText(message.text, env);
    } catch (error) {
      reply = `Error al procesar el mensaje: ${error.message}`;
    }
    await sendMessage(env.TELEGRAM_BOT_TOKEN, env.TELEGRAM_CHAT_ID, reply);
    return new Response("ok");
  },
};
