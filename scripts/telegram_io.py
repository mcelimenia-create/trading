"""Lectura y envio de mensajes de Telegram (solo stdlib)."""
import json
import urllib.parse
import urllib.request

HTTP_TIMEOUT_S = 20


def get_updates(token, offset):
    query = urllib.parse.urlencode({"timeout": 0, "offset": offset})
    url = f"https://api.telegram.org/bot{token}/getUpdates?{query}"
    with urllib.request.urlopen(url, timeout=HTTP_TIMEOUT_S) as response:
        return json.loads(response.read()).get("result", [])


def text_messages(updates, chat_id):
    """Devuelve (update_id, texto) solo de los mensajes del chat autorizado."""
    out = []
    for update in updates:
        message = update.get("message") or {}
        if str((message.get("chat") or {}).get("id")) != str(chat_id):
            continue
        if "text" in message:
            out.append((update["update_id"], message["text"]))
    return out
