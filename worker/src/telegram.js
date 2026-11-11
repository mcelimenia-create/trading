// Envio de mensajes con la API de Telegram.
const MAX_CHARS = 3500;

export async function sendMessage(token, chatId, text) {
  const chunks = [];
  for (let i = 0; i < text.length; i += MAX_CHARS) chunks.push(text.slice(i, i + MAX_CHARS));
  for (const chunk of chunks) {
    const res = await fetch(`https://api.telegram.org/bot${token}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text: chunk, disable_web_page_preview: true }),
    });
    if (!res.ok) throw new Error(`Telegram devolvio HTTP ${res.status}`);
  }
}
