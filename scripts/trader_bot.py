#!/usr/bin/env python3
"""Bot de Telegram con las skills de skills/ (day-trader-skill, MIT) y la cartera de papel.

    python3 scripts/trader_bot.py news      # noticias de la lista vigilada
    python3 scripts/trader_bot.py session   # operacion de 1 dia: entrada, plan, simulacion, salida
    python3 scripts/trader_bot.py paper     # cartera de papel de la regla de precio (sin dinero real)

Solo lee datos publicos y envia avisos. Nunca envia ordenes a un broker.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import paper_trader

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
TRADER_DIR = ROOT / "trader"
CONFIG_FILE = ROOT / "config" / "watchlist.json"
ENV_FILE = ROOT / ".env"
PAPER_FILE = TRADER_DIR / "paper.json"
NEW_YORK = ZoneInfo("America/New_York")
TELEGRAM_MAX_CHARS = 3500
HTTP_TIMEOUT_S = 20
SKILL_TIMEOUT_S = 300
ENTRY_OK_CODES = (0, 1)   # 0 = triggered, 1 = waiting / expired / no data
NEWS_OK_CODES = (0, 1)    # 0 = new items, 1 = none new
ALERTS_OK_CODES = (0, 1)  # 0 = something rang, 1 = nothing rang


def load_env(path):
    if not path.exists():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_config():
    return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))


def run_skill(script, args, ok_codes):
    result = subprocess.run(
        [sys.executable, str(SKILLS_DIR / script), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=SKILL_TIMEOUT_S,
    )
    if result.returncode not in ok_codes:
        raise RuntimeError(f"{script} {' '.join(args)} -> {result.returncode}: {result.stderr.strip()}")
    return result


def split_messages(text):
    chunks, current = [], ""
    pieces = [piece for line in text.splitlines(keepends=True)
              for piece in (line[i:i + TELEGRAM_MAX_CHARS] for i in range(0, len(line), TELEGRAM_MAX_CHARS))]
    for piece in pieces:
        if len(current) + len(piece) > TELEGRAM_MAX_CHARS:
            chunks.append(current)
            current = ""
        current += piece
    if current:
        chunks.append(current)
    return chunks


def send_telegram(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for chunk in split_messages(text):
        data = urllib.parse.urlencode({"chat_id": chat_id, "text": chunk, "disable_web_page_preview": "true"}).encode()
        try:
            with urllib.request.urlopen(url, data=data, timeout=HTTP_TIMEOUT_S) as response:
                response.read()
        except urllib.error.HTTPError as error:
            raise RuntimeError(f"Telegram devolvio HTTP {error.code}") from None


def news_job(notify):
    tickers = load_config()["tickers"]
    result = run_skill("trader-news/news.py", ["--tickers", *tickers, "--hours", "24", "--json"], NEWS_OK_CODES)
    fresh = [item for item in json.loads(result.stdout)["items"] if item.get("new")]
    if not fresh:
        print("Sin noticias nuevas")
        return
    lines = [f"- {item['ticker']}: {item['title']}\n  {item['link']}" for item in fresh]
    notify("Noticias nuevas:\n\n" + "\n\n".join(lines))


def find_triggered_entry(tickers, today):
    for ticker in tickers:
        entry_path = TRADER_DIR / f"entry-{today}-{ticker}.json"
        result = run_skill(
            "trader-entry/entry.py",
            ["check", ticker, "--setup", "orb", "--write", str(entry_path)],
            ENTRY_OK_CODES,
        )
        if result.returncode == 0:
            return ticker, entry_path, result.stdout
    return None


def open_day_trade(tickers, today, notify):
    found = find_triggered_entry(tickers, today)
    if found is None:
        print("Sin entrada de 1 dia activada hoy")
        return
    ticker, entry_path, entry_text = found
    plan_path = TRADER_DIR / "plan.json"
    run_skill("trader-exit/exit.py", ["plan", "--from", str(entry_path), "--write", str(plan_path)], (0,))
    simulation = run_skill("trader-timemachine/timemachine.py", ["run", "--plan", str(plan_path)], (0,))
    run_skill("trader-alerts/alerts.py", ["add", "--from-plan"], (0,))
    (TRADER_DIR / f"trade-{today}.json").write_text(json.dumps({"ticker": ticker}), encoding="utf-8")
    notify(f"OPERACION 1 DIA - ENTRADA {ticker}\n\n{entry_text}\n\nPLAN Y SIMULACION\n\n{simulation.stdout}")


def watch_day_trade(ticker, notify):
    run_skill("trader-alerts/alerts.py", ["quote", ticker, "--write"], (0,))
    result = run_skill("trader-alerts/alerts.py", ["check"], ALERTS_OK_CODES)
    if result.returncode == 0:
        notify(f"OPERACION 1 DIA - SALIDA / AVISO {ticker}\n\n{result.stdout}")


def session_job(notify):
    today = datetime.now(NEW_YORK).strftime("%Y-%m-%d")
    marker = TRADER_DIR / f"trade-{today}.json"
    if marker.exists():
        watch_day_trade(json.loads(marker.read_text(encoding="utf-8"))["ticker"], notify)
        return
    open_day_trade(load_config()["tickers"], today, notify)


def paper_job(notify):
    paper_trader.paper_job(notify, load_config()["tickers"], PAPER_FILE)


def main(argv):
    jobs = {"news": news_job, "session": session_job, "paper": paper_job}
    if len(argv) != 2 or argv[1] not in jobs:
        print("Uso: trader_bot.py news|session|paper", file=sys.stderr)
        return 2
    env = {**load_env(ENV_FILE), **os.environ}
    token = env.get("TELEGRAM_BOT_TOKEN")
    chat_id = env.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID", file=sys.stderr)
        return 1
    TRADER_DIR.mkdir(exist_ok=True)

    def notify(text):
        send_telegram(token, chat_id, text)

    jobs[argv[1]](notify)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
