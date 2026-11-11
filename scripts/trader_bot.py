#!/usr/bin/env python3
"""Bot de Telegram con las skills de skills/ (day-trader-skill, MIT).

    python3 scripts/trader_bot.py news      # noticias de la lista vigilada
    python3 scripts/trader_bot.py session   # operacion de 1 dia: entrada, plan, simulacion, salida
    python3 scripts/trader_bot.py swing     # candidatos de 1-20 sesiones y seguimiento de salidas

Solo lee datos publicos y envia avisos. Nunca envia ordenes a un broker.
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = ROOT / "skills"
TRADER_DIR = ROOT / "trader"
CONFIG_FILE = ROOT / "config" / "watchlist.json"
ENV_FILE = ROOT / ".env"
SWING_FILE = TRADER_DIR / "swing-open.json"
NEW_YORK = ZoneInfo("America/New_York")
TELEGRAM_MAX_CHARS = 3500
HTTP_TIMEOUT_S = 20
SKILL_TIMEOUT_S = 1800
USER_AGENT = "Mozilla/5.0"
CHART_URL = "https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?range=6mo&interval=1d"
SWING_SETUPS = {"breakout_20d", "bull_flag", "reclaim_ma20", "oversold_bounce"}
SWING_MAX_CANDIDATES = 10
SWING_MAX_SESSIONS = 20
SWING_STOP_LOOKBACK = 10
SWING_TARGET_R = 2
ENTRY_OK_CODES = (0, 1)  # 0 = triggered, 1 = waiting / expired / no data
NEWS_OK_CODES = (0, 1)   # 0 = new items, 1 = none new
ALERTS_OK_CODES = (0, 1)  # 0 = something rang, 1 = nothing rang
SCAN_OK_CODES = (0, 1)   # 0 = hits, 1 = no hits


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


def fetch_daily_bars(symbol):
    url = CHART_URL.format(symbol=urllib.parse.quote(symbol, safe=""))
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        result = json.loads(response.read())["chart"]["result"][0]
    quote = result["indicators"]["quote"][0]
    bars = []
    for ts, high, low, close in zip(result["timestamp"], quote["high"], quote["low"], quote["close"]):
        if None in (high, low, close):
            continue
        bars.append({
            "date": datetime.fromtimestamp(ts, timezone.utc).date().isoformat(),
            "high": high, "low": low, "close": close,
        })
    return bars


def split_messages(text):
    chunks, current = [], ""
    for line in text.splitlines(keepends=True):
        if len(current) + len(line) > TELEGRAM_MAX_CHARS:
            chunks.append(current)
            current = ""
        current += line
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


def build_swing_plan(symbol, bars, setups):
    last = bars[-1]
    stop = min(bar["low"] for bar in bars[-SWING_STOP_LOOKBACK:])
    if stop >= last["close"]:
        return None
    risk = last["close"] - stop
    return {
        "symbol": symbol, "setups": setups, "opened": last["date"],
        "entry": last["close"], "stop": stop,
        "target": round(last["close"] + SWING_TARGET_R * risk, 2), "sessions": 0,
    }


def review_swing_position(position, bars):
    """Returns (updated position, outcome or None). Outcome: STOP, OBJETIVO or TIEMPO."""
    sessions = 0
    for bar in bars:
        if bar["date"] <= position["opened"]:
            continue
        sessions += 1
        if bar["low"] <= position["stop"]:
            return dict(position, sessions=sessions), ("STOP", position["stop"])
        if bar["high"] >= position["target"]:
            return dict(position, sessions=sessions), ("OBJETIVO", position["target"])
        if sessions >= SWING_MAX_SESSIONS:
            return dict(position, sessions=sessions), ("TIEMPO", bar["close"])
    return dict(position, sessions=sessions), None


def load_swing_positions():
    if not SWING_FILE.exists():
        return []
    return json.loads(SWING_FILE.read_text(encoding="utf-8"))


def save_swing_positions(positions):
    TRADER_DIR.mkdir(exist_ok=True)
    SWING_FILE.write_text(json.dumps(positions, indent=2), encoding="utf-8")


def new_swing_plans(hits, open_symbols):
    plans = []
    for hit in hits[:SWING_MAX_CANDIDATES]:
        if hit["symbol"] in open_symbols:
            continue
        try:
            plan = build_swing_plan(hit["symbol"], fetch_daily_bars(hit["symbol"]), hit["setups"])
        except (urllib.error.URLError, KeyError, IndexError, ValueError):
            continue
        if plan:
            plans.append(plan)
    return plans


def monitor_swing_positions(positions):
    still_open, closed = [], []
    for position in positions:
        try:
            bars = fetch_daily_bars(position["symbol"])
        except (urllib.error.URLError, KeyError, IndexError, ValueError):
            still_open.append(position)
            continue
        updated, outcome = review_swing_position(position, bars)
        if outcome:
            closed.append((updated, outcome))
        else:
            still_open.append(updated)
    return still_open, closed


def format_swing_plans(plans, vix_close):
    lines = [
        f"{p['symbol']}  entrada {p['entry']:.2f}  stop {p['stop']:.2f}  objetivo {p['target']:.2f}  "
        f"({', '.join(p['setups'])})"
        for p in plans
    ]
    return (
        f"SWING candidatos (hasta {SWING_MAX_SESSIONS} sesiones), cierre de hoy. VIX {vix_close}.\n"
        "Stop: minimo de 10 sesiones. Objetivo: 2R. Salida por tiempo a las 20 sesiones. No es una orden.\n\n"
        + "\n".join(lines)
    )


def format_swing_closures(closed):
    return "SWING - salida\n\n" + "\n".join(
        f"{p['symbol']} cierra por {outcome} a {price:.2f} (entrada {p['entry']:.2f}, {p['sessions']} sesiones)"
        for p, (outcome, price) in closed
    )


def vix_close():
    try:
        return f"{fetch_daily_bars('^VIX')[-1]['close']:.2f}"
    except (urllib.error.URLError, KeyError, IndexError, ValueError):
        return "no disponible"


def swing_job(notify):
    run_skill("trader-scanner/scan.py", ["universe"], SCAN_OK_CODES)
    scan = run_skill("trader-scanner/scan.py", ["daily", "--json", "--out", str(TRADER_DIR / "swing-scan.json")], SCAN_OK_CODES)
    hits = [h for h in json.loads(scan.stdout)["hits"] if SWING_SETUPS & set(h["setups"])]
    positions = load_swing_positions()
    still_open, closed = monitor_swing_positions(positions)
    plans = new_swing_plans(hits, {p["symbol"] for p in still_open})
    save_swing_positions(still_open + plans)
    if closed:
        notify(format_swing_closures(closed))
    if plans:
        notify(format_swing_plans(plans, vix_close()))
    if not closed and not plans:
        print("Sin candidatos swing ni salidas hoy")


def main(argv):
    jobs = {"news": news_job, "session": session_job, "swing": swing_job}
    if len(argv) != 2 or argv[1] not in jobs:
        print("Uso: trader_bot.py news|session|swing", file=sys.stderr)
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
