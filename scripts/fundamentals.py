"""Crecimiento anual de ingresos desde la SEC, con la fecha en que se publico (sin mirar al futuro)."""
import bisect
import json
import os
import urllib.request
from datetime import date

TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
CONCEPTS = [
    ("us-gaap", "Revenues"),
    ("us-gaap", "RevenueFromContractWithCustomerExcludingAssessedTax"),
    ("us-gaap", "SalesRevenueNet"),
    ("ifrs-full", "Revenue"),
]
ANNUAL_FORMS = {"10-K", "20-F", "10-K/A", "20-F/A"}
HTTP_TIMEOUT_S = 60


def sec_user_agent():
    return " ".join(os.environ.get("SEC_USER_AGENT", "").split())


def fetch_sec_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": sec_user_agent()})
    with urllib.request.urlopen(request, timeout=HTTP_TIMEOUT_S) as response:
        return json.loads(response.read())


def cik_for(ticker):
    for entry in fetch_sec_json(TICKERS_URL).values():
        if entry["ticker"].upper() == ticker.upper():
            return entry["cik_str"]
    return None


def annual_growth(facts):
    """[(fecha_publicacion, crecimiento, fin_ejercicio)] ordenado por publicacion."""
    best = []
    for taxonomy, concept in CONCEPTS:
        node = facts.get(taxonomy, {}).get(concept)
        if not node:
            continue
        units = next(iter(node["units"].values()))
        annual = {}
        for fact in units:
            if fact.get("fp") != "FY" or fact.get("form") not in ANNUAL_FORMS or "start" not in fact:
                continue
            duration = (date.fromisoformat(fact["end"]) - date.fromisoformat(fact["start"])).days
            if not 340 <= duration <= 380:
                continue
            previous = annual.get(fact["end"])
            if previous is None or fact["filed"] < previous[1]:
                annual[fact["end"]] = (fact["val"], fact["filed"])
        records = []
        for end, (value, filed) in annual.items():
            prev_ends = [e for e in annual if abs((date.fromisoformat(e) - date.fromisoformat(end)).days + 365) <= 15]
            if not prev_ends or annual[prev_ends[0]][0] <= 0:
                continue
            records.append((filed, value / annual[prev_ends[0]][0] - 1, end))
        records.sort()
        if records and (not best or records[-1][0] > best[-1][0]):
            best = records
    return best


def growth_for(ticker):
    cik = cik_for(ticker)
    if cik is None:
        return []
    return annual_growth(fetch_sec_json(COMPANYFACTS_URL.format(cik=cik))["facts"])


def latest_growth(records, day):
    """Ultimo crecimiento publicado antes de 'day' (YYYY-MM-DD), o None."""
    filed = [r[0] for r in records]
    k = bisect.bisect_right(filed, day)
    return records[k - 1][1] if k else None
