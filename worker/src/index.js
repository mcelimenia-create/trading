// Webhook de Telegram (comandos al instante) y cron (avisos y tareas de GitHub).
import { handleCommand } from "./commands.js";
import { runScheduled } from "./cron.js";
import { marketContext, todayNewYork } from "./context.js";
import { PORTFOLIO } from "./config.js";
import { fetchBars } from "./market.js";
import { loadState, saveState } from "./store.js";
import { sendMessage } from "./telegram.js";

const CANDIDATES_URL = "https://raw.githubusercontent.com/mcelimenia-create/trading/main/docs/data/candidates.json";

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

// Estado de las posiciones reales para la copia de GitHub (lo lee el job session).
function serveState(request, env) {
  if (request.headers.get("Authorization") !== `Bearer ${env.SYNC_TOKEN}`) {
    return new Response("forbidden", { status: 403 });
  }
  return loadState(env.DB).then((state) => Response.json(state));
}

export default {
  async fetch(request, env) {
    if (request.method === "GET") {
      return new URL(request.url).pathname === "/state" ? serveState(request, env) : new Response("ok");
    }
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

  scheduled(event, env, ctx) {
    ctx.waitUntil(runScheduled(env, event.scheduledTime));
  },
};
