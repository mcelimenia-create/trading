#!/usr/bin/env python3
"""Bot de Telegram con las skills de skills/ (day-trader-skill, MIT) y la cartera de papel.

    python3 scripts/trader_bot.py news      # noticias de la lista vigilada
    python3 scripts/trader_bot.py session   # operacion de 1 dia: entrada, plan, simulacion, salida
    python3 scripts/trader_bot.py paper     # cartera de papel de la regla de precio (sin dinero real)
    python3 scripts/trader_bot.py candidates|scan  # candidatos de medio plazo y escaner de EEUU

Solo lee datos publicos y envia avisos. Nunca envia ordenes a un broker.
"""
import hashlib
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

import candidates
import catalysts
import fundamentals
import paper_trader
import real_crypto
import scanner

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
TRADER_DIR = Path(os.environ.get("TRADER_DIR") or ROOT / "trader")
CONFIG_FILE = ROOT / "config" / "watchlist.json"
ENV_FILE = ROOT / ".env"
PAPER_FILE = TRADER_DIR / "paper.json"
REAL_FILE = TRADER_DIR / "real.json"
EARNINGS_FILE = TRADER_DIR / "earnings_alerted.json"
WORKER_STATE_URL = "https://trading-bot.mcelimen-ia.workers.dev/state"
WORKER_AUDIENCE = "trading-bot-worker"
REAL_DIGEST_FILE = TRADER_DIR / "real_published.sha256"
REAL_PUBLIC_FILE = ROOT / "docs" / "data" / "real.enc"
CANDIDATE_CONFIG = ROOT / "config" / "candidates.json"
PORTFOLIO_FILE = ROOT / "config" / "portfolio.json"
SEC_EXCHANGES_URL = "https://www.sec.gov/files/company_tickers_exchange.json"
DOCS_DATA_DIR = ROOT / "docs" / "data"
CANDIDATES_PUBLIC_FILE = DOCS_DATA_DIR / "candidates.json"
DASHBOARD_JOBS = {"news", "paper", "candidates"}
NEW_YORK = ZoneInfo("America/New_York")
NEWS_PUBLIC_MAX = 40
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


def skill_env():
    env = dict(os.environ)
    if "SEC_USER_AGENT" in env:
        env["SEC_USER_AGENT"] = " ".join(env["SEC_USER_AGENT"].split())
    return env


def run_skill(script, args, ok_codes):
    result = subprocess.run(
        [sys.executable, str(SKILLS_DIR / script), *args],
        cwd=ROOT, capture_output=True, text=True, timeout=SKILL_TIMEOUT_S, env=skill_env(),
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


def write_public_news(items):
    """Ultimas noticias para el panel (titulares publicos, sin datos personales)."""
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    keep = ("ticker", "title", "link", "source", "time", "important")
    rows = [{key: item.get(key) for key in keep} for item in items[:NEWS_PUBLIC_MAX]]
    doc = {"generated": datetime.now(ZoneInfo("UTC")).isoformat(timespec="minutes"), "items": rows}
    (DOCS_DATA_DIR / "news.json").write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")


def news_job(notify):
    tickers = load_config()["tickers"]
    result = run_skill("trader-news/news.py", ["--tickers", *tickers, "--hours", "24", "--json"], NEWS_OK_CODES)
    if not result.stdout.strip():
        raise RuntimeError(f"news.py no devolvio datos: {result.stderr.strip()[-800:]}")
    items = json.loads(result.stdout)["items"]
    write_public_news(items)
    fresh = [item for item in items if item.get("new")]
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
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    weight = paper_trader.weight_for(plan["entry"], plan["stop"])
    size_text = (f"Tamano de referencia: {100 * weight:.1f}% de la cartera "
                 f"(riesgo 2%, maximo 20%). Simulacion, no una orden.")
    notify(f"OPERACION 1 DIA - ENTRADA {ticker}\n\n{entry_text}\n\n{size_text}\n\nPLAN Y SIMULACION\n\n{simulation.stdout}")


def watch_day_trade(ticker, notify):
    run_skill("trader-alerts/alerts.py", ["quote", ticker, "--write"], (0,))
    result = run_skill("trader-alerts/alerts.py", ["check"], ALERTS_OK_CODES)
    if result.returncode == 0:
        notify(f"OPERACION 1 DIA - SALIDA / AVISO {ticker}\n\n{result.stdout}")


def actions_id_token():
    """Token OIDC de este job: el Worker comprueba que viene de este repositorio y de main."""
    url = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL", "")
    bearer = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "")
    if not url or not bearer:
        raise RuntimeError("falta el token OIDC de GitHub (permiso id-token: write en el workflow)")
    request = urllib.request.Request(f"{url}&audience={WORKER_AUDIENCE}", headers={"Authorization": f"Bearer {bearer}"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        return json.loads(response.read().decode("utf-8"))["value"]


def sync_real_positions():
    """Copia las posiciones reales de la base del Worker a trader/real.json (para cifrarlas en el panel)."""
    request = urllib.request.Request(WORKER_STATE_URL, headers={"Authorization": f"Bearer {actions_id_token()}"})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        state = json.loads(response.read().decode("utf-8"))
    REAL_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


def earnings_alerts(notify):
    """Resultados proximos de las posiciones reales. Un aviso por valor y dia."""
    today = datetime.now(NEW_YORK).strftime("%Y-%m-%d")
    symbols = [p["symbol"] for p in load_json(REAL_FILE, {"open": []})["open"]]
    soon = catalysts.earnings_soon(symbols, today, load_portfolio()["earnings_window_days"],
                                   os.environ.get("FINNHUB_API_KEY", "")) or []
    sent = load_json(EARNINGS_FILE, {})
    pending = [(symbol, day) for symbol, day in soon if sent.get(symbol) != today]
    if not pending:
        return
    notify("RESULTADOS PROXIMOS: " + ", ".join(f"{symbol} el {day}" for symbol, day in pending)
           + ". Revisa la tesis antes.")
    sent.update({symbol: today for symbol, _ in pending})
    EARNINGS_FILE.write_text(json.dumps(sent), encoding="utf-8")


def session_job(notify):
    sync_real_positions()
    earnings_alerts(notify)
    today = datetime.now(NEW_YORK).strftime("%Y-%m-%d")
    marker = TRADER_DIR / f"trade-{today}.json"
    if marker.exists():
        watch_day_trade(json.loads(marker.read_text(encoding="utf-8"))["ticker"], notify)
        return
    open_day_trade(load_config()["tickers"], today, notify)


def paper_job(notify):
    paper_trader.paper_job(notify, load_config()["tickers"], PAPER_FILE)


def load_json(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def load_portfolio():
    return json.loads(PORTFOLIO_FILE.read_text(encoding="utf-8"))


def scan_job(notify):
    if not fundamentals.sec_user_agent():
        raise RuntimeError("falta SEC_USER_AGENT para leer la lista de la SEC")
    known = set(load_config()["tickers"]) | set(load_json(CANDIDATE_CONFIG, {"tickers": []})["tickers"])
    universe = [s for s in scanner.universe_from_sec(fundamentals.fetch_sec_json(SEC_EXCHANGES_URL))
                if s not in known]
    proposals, checked = scanner.scan_universe(universe, paper_trader.fetch_bars, pause_s=scanner.REQUEST_PAUSE_S)
    notify(scanner.format_message(proposals, checked, len(universe)))


def candidates_job(notify):
    tickers = load_json(CANDIDATE_CONFIG, {"tickers": []})["tickers"]
    candidates.candidates_job(notify, tickers, CANDIDATES_PUBLIC_FILE, load_portfolio())


def report_failure(job, error, notify):
    """Avisa por Telegram de un fallo. Si Telegram tampoco responde, el error original sigue su curso."""
    try:
        notify(f"FALLO del bot (tarea {job}): {error}")
    except OSError as send_error:
        print(f"No pude avisar del fallo por Telegram: {send_error}", file=sys.stderr)


def publish_real():
    """Publica las posiciones reales cifradas en docs/data, solo cuando cambian."""
    if not REAL_FILE.exists():
        return
    passphrase = os.environ.get("STATE_KEY", "")
    if not passphrase:
        raise RuntimeError("falta STATE_KEY: no puedo publicar las posiciones reales cifradas")
    plain = REAL_FILE.read_bytes()
    digest = hashlib.sha256(plain).hexdigest()
    if REAL_DIGEST_FILE.exists() and REAL_DIGEST_FILE.read_text(encoding="utf-8").strip() == digest:
        return
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    REAL_PUBLIC_FILE.write_bytes(real_crypto.encrypt(plain, passphrase))
    REAL_DIGEST_FILE.write_text(digest, encoding="utf-8")


def publish_dashboard(job, ok=True):
    """Copia el estado de papel y la hora de la ultima ejecucion a docs/data (panel de GitHub Pages)."""
    DOCS_DATA_DIR.mkdir(parents=True, exist_ok=True)
    status_path = DOCS_DATA_DIR / "status.json"
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path.exists() else {}
    stamp = datetime.now(ZoneInfo("UTC")).strftime("%Y-%m-%d %H:%M UTC")
    status[job] = stamp if ok else f"{stamp} (fallo)"
    status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    if job == "paper" and PAPER_FILE.exists():
        (DOCS_DATA_DIR / "paper.json").write_text(PAPER_FILE.read_text(encoding="utf-8"), encoding="utf-8")


def main(argv):
    jobs = {
        "news": news_job, "session": session_job, "paper": paper_job,
        "candidates": candidates_job, "scan": scan_job,
    }
    if len(argv) != 2 or argv[1] not in jobs:
        print("Uso: trader_bot.py news|session|paper|candidates|scan", file=sys.stderr)
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

    try:
        jobs[argv[1]](notify)
        if argv[1] == "session":
            publish_real()
    except Exception as error:
        report_failure(argv[1], error, notify)
        if argv[1] in DASHBOARD_JOBS:
            publish_dashboard(argv[1], ok=False)
        raise
    if argv[1] in DASHBOARD_JOBS:
        publish_dashboard(argv[1])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
