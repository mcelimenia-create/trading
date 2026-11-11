// Tareas de GitHub Actions que el Worker lanza a sus horas (UTC, mismas horas que tenia el cron de GitHub).
const NEWS_HOURS = [7, 13, 18, 21];
const SESSION_FIRST_HOUR = 13;
const SESSION_LAST_HOUR = 21;

function isWeekday(dow) {
  return dow >= 1 && dow <= 5;
}

// Devuelve los nombres de las tareas que tocan en esa fecha (el cron del Worker corre cada 5 minutos).
export function jobsDue(date) {
  const hour = date.getUTCHours();
  const minute = date.getUTCMinutes();
  const dow = date.getUTCDay();
  const weekday = isWeekday(dow);
  const inSession = weekday && hour >= SESSION_FIRST_HOUR && hour <= SESSION_LAST_HOUR;
  const due = [];
  if (minute === 5 && NEWS_HOURS.includes(hour)) due.push("news");
  if (inSession && minute % 15 === 0) due.push("session");
  if (weekday && hour === 21 && minute === 35) due.push("paper");
  if (weekday && hour === 21 && minute === 50) due.push("candidates");
  if (dow === 5 && hour === 22 && minute === 0) due.push("scan");
  return due;
}
