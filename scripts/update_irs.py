from __future__ import annotations
import json, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests
from bs4 import BeautifulSoup

URL = "https://cbonds.com/indexes/219623/"
OUT = Path(__file__).resolve().parents[1] / "data" / "irs.json"
TENORS = ["6M","1Y","2Y","3Y","4Y","5Y","7Y","10Y","12Y","15Y"]

def load_old():
    try:
        return json.loads(OUT.read_text(encoding="utf-8"))
    except Exception:
        return {"rates": {}}

def fetch_text():
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; PreferredStockDashboard/1.0; +https://github.com/)",
        "Accept-Language": "en-US,en;q=0.9"
    }
    r = requests.get(URL, headers=headers, timeout=30)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    return soup.get_text(" ", strip=True)

def parse(text):
    rates = {}
    dates = []
    for tenor in TENORS:
        # Example: IRS TWD (...) 7Y 2.5534 % 11/09/2026
        pat = rf"{re.escape(tenor)}\s+([0-9]+(?:\.[0-9]+)?)\s*%\s+(\d{{2}}/\d{{2}}/\d{{4}})"
        m = re.search(pat, text, re.I)
        if m:
            rates[tenor] = float(m.group(1))
            dates.append(datetime.strptime(m.group(2), "%d/%m/%Y").date())
    if not rates:
        raise RuntimeError("No IRS tenors found in Cbonds page text")
    asof = max(dates).isoformat() if dates else None
    return rates, asof

def main():
    old = load_old()
    tw = timezone(timedelta(hours=8))
    now = datetime.now(tw).isoformat(timespec="seconds")
    try:
        text = fetch_text()
        rates, asof = parse(text)
        merged = dict(old.get("rates", {}))
        merged.update(rates)
        payload = {
            "status": "ok",
            "source": URL,
            "source_label": "IRS TWD (Quarterly Money vs 3M TAIBOR)",
            "asof": asof or old.get("asof"),
            "updated_at": now,
            "rates": merged,
            "note": "Automatically refreshed by GitHub Actions."
        }
    except Exception as e:
        payload = dict(old)
        payload["status"] = "stale"
        payload["updated_at"] = now
        payload["last_error"] = str(e)
        payload.setdefault("source", URL)
        payload.setdefault("source_label", "IRS TWD (Quarterly Money vs 3M TAIBOR)")
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
