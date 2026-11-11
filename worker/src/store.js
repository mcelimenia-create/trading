// Estado de las posiciones reales en D1 (una sola fila con el JSON).
import { emptyState } from "./commands.js";

export async function loadState(db) {
  const row = await db.prepare("SELECT json FROM state WHERE id = 1").first();
  return row ? JSON.parse(row.json) : emptyState();
}

export async function saveState(db, state) {
  await db
    .prepare("INSERT INTO state (id, json) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET json = excluded.json")
    .bind(JSON.stringify(state))
    .run();
}
