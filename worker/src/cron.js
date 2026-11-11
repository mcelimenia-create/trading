// Tarea cada 5 minutos: lanza las tareas de GitHub a su hora, avisa de stops, trailing y limites, y repasa los domingos.
import { exitItems, limitWarnings, newAlerts, weeklyReview } from "./alerts.js";
import { PORTFOLIO } from "./config.js";
import { marketContext, todayNewYork } from "./context.js";
import { dispatchJob } from "./github.js";
import { fetchBars } from "./market.js";
import { jobsDue } from "./schedule.js";
import { loadState, saveState } from "./store.js";
import { sendMessage } from "./telegram.js";

const MARKET_FIRST_HOUR = 13;
const MARKET_LAST_HOUR = 21;
const REVIEW_HOUR = 17;

function inMarketWindow(date) {
  const dow = date.getUTCDay();
  const hour = date.getUTCHours();
  return dow >= 1 && dow <= 5 && hour >= MARKET_FIRST_HOUR && hour <= MARKET_LAST_HOUR;
}

async function positionItems(state, today) {
  const items = [];
  for (const position of state.open) {
    const bars = await fetchBars(position.symbol, "6mo").catch(() => null);
    if (bars) items.push(...exitItems(position, bars, today));
  }
  return items;
}

async function limitItems(state, today, fx) {
  return limitWarnings(state, PORTFOLIO, today, fx).map((text) => ({ key: `limit:${text}:${today}`, text }));
}

async function launchJobs(env, now, sendText) {
  for (const job of jobsDue(now)) {
    await dispatchJob(env.GITHUB_TOKEN, job).catch((error) => sendText(`FALLO al lanzar la tarea ${job}: ${error.message}`));
  }
}

export async function runScheduled(env, scheduledTime) {
  const now = new Date(scheduledTime);
  const today = todayNewYork();
  const sendText = (text) => sendMessage(env.TELEGRAM_BOT_TOKEN, env.TELEGRAM_CHAT_ID, text);
  await launchJobs(env, now, sendText);

  const marketOpen = inMarketWindow(now);
  const reviewDue = now.getUTCDay() === 0 && now.getUTCHours() === REVIEW_HOUR;
  if (!marketOpen && !reviewDue) return;

  const state = await loadState(env.DB);
  let items = [];
  if (marketOpen) {
    const market = await marketContext();
    items = [...await positionItems(state, today), ...await limitItems(state, today, market.fx)];
  }
  const review = reviewDue ? weeklyReview(state, today) : null;
  if (review) items.push({ key: `review:${today}`, text: review });

  const { state: next, texts } = newAlerts(state, items, today);
  if (!texts.length) return;
  await sendText(texts.join("\n"));
  await saveState(env.DB, next);
}
