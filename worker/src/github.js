// Lanza una tarea de GitHub Actions (workflow_dispatch del workflow trader-bot).
const REPO = "mcelimenia-create/trading";
const WORKFLOW_URL = `https://api.github.com/repos/${REPO}/actions/workflows/trader-bot.yml/dispatches`;

export async function dispatchJob(token, job) {
  const res = await fetch(WORKFLOW_URL, {
    method: "POST",
    headers: {
      Accept: "application/vnd.github+json",
      Authorization: `Bearer ${token}`,
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "trading-bot-worker",
    },
    body: JSON.stringify({ ref: "main", inputs: { job } }),
  });
  if (!res.ok) throw new Error(`GitHub devolvio HTTP ${res.status}`);
}
