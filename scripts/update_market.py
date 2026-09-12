from __future__ import annotations
import json, math, time
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "preferred_stocks.json"
MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"
TW = timezone(timedelta(hours=8))


def fnum(v):
    try:
        if v in (None, "", "-", "--"):
            return None
        s = str(v).replace(",", "").strip()
        x = float(s)
        return x if math.isfinite(x) else None
    except Exception:
        return None


def quote_one(session, code):
    # Most preferred shares are listed. Try TWSE first, then TPEx.
    for market in ("tse", "otc"):
        params = {"ex_ch": f"{market}_{code}.tw", "json": "1", "delay": "0"}
        r = session.get(MIS_URL, params=params, timeout=20)
        r.raise_for_status()
        j = r.json()
        arr = j.get("msgArray") or []
        if not arr:
            continue
        q = arr[0]
        price = fnum(q.get("z"))
        if price is None:
            # During non-trading periods z can be '-'. Prefer previous close over bid/ask guesses.
            price = fnum(q.get("y"))
        if price is None:
            continue
        return {
            "price": price,
            "market": market,
            "name": q.get("n") or q.get("nf"),
            "quoteDate": q.get("d"),
            "quoteTime": q.get("t"),
            "previousClose": fnum(q.get("y")),
            "open": fnum(q.get("o")),
            "high": fnum(q.get("h")),
            "low": fnum(q.get("l")),
            "volume": fnum(q.get("v")),
        }
    return None


def approx_ytc(price, annual_div, call_price, call_date):
    if not all(isinstance(x, (int,float)) and x > 0 for x in (price, annual_div, call_price)):
        return None
    try:
        d = date.fromisoformat(call_date)
    except Exception:
        return None
    days = (d - datetime.now(TW).date()).days
    if days <= 7:
        return None
    years = days / 365.25
    # Approximate annual-coupon YTC using fractional-year annuity formula.
    def pv(r):
        if r <= -0.9999:
            return float("inf")
        if abs(r) < 1e-9:
            coupons = annual_div * years
        else:
            coupons = annual_div * (1 - (1+r) ** (-years)) / r
        return coupons + call_price / ((1+r) ** years)
    lo, hi = -0.95, 3.0
    if pv(lo) < price or pv(hi) > price:
        return None
    for _ in range(120):
        mid = (lo+hi)/2
        if pv(mid) > price:
            lo = mid
        else:
            hi = mid
    return round((lo+hi)/2*100, 2)


def main():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    stocks = data.get("stocks", [])
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; TaiwanPreferredStockDashboard/1.2; +https://github.com/)",
        "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
        "Referer": "https://mis.twse.com.tw/stock/fibest.jsp",
    })
    now = datetime.now(TW)
    ok, fail = 0, []
    for s in stocks:
        code = str(s.get("code", "")).strip()
        try:
            q = quote_one(session, code)
            if not q:
                fail.append(code)
                continue
            old_price = s.get("price")
            s["price"] = q["price"]
            s["market"] = q["market"]
            s["quoteDate"] = q.get("quoteDate")
            s["quoteTime"] = q.get("quoteTime")
            s["previousClose"] = q.get("previousClose")
            s["open"] = q.get("open")
            s["high"] = q.get("high")
            s["low"] = q.get("low")
            s["volume"] = q.get("volume")
            if q.get("previousClose"):
                s["changePct"] = round((q["price"] / q["previousClose"] - 1) * 100, 2)
            if isinstance(s.get("div"), (int,float)) and q["price"] > 0:
                s["yield"] = round(s["div"] / q["price"] * 100, 2)
            auto_irr = approx_ytc(q["price"], s.get("div"), s.get("callPrice"), s.get("callDate"))
            if auto_irr is not None:
                s["irr"] = auto_irr
                s["irrMethod"] = "自動估算YTC（年配息近似）"
            else:
                s["irrMethod"] = "無法自動估算（缺少未來可贖回日/現金流）"
            s["lastPriceBeforeUpdate"] = old_price
            s["marketUpdatedAt"] = now.isoformat(timespec="seconds")
            ok += 1
            time.sleep(0.12)
        except Exception as e:
            fail.append(code)
            s["marketUpdateError"] = str(e)[:240]
    data["version"] = "1.2"
    data["marketDataAsOf"] = now.date().isoformat()
    data["marketUpdatedAt"] = now.isoformat(timespec="seconds")
    data["marketUpdateStatus"] = "ok" if ok else "stale"
    data["marketUpdateSuccessCount"] = ok
    data["marketUpdateFailCodes"] = fail
    data["marketSourceLabel"] = "TWSE MIS / TPEx quote fallback"
    data["marketSourceUrl"] = MIS_URL
    data["irrPolicy"] = "IRR/YTC 僅在有未來可贖回日、贖回價及年股息時自動估算；採年配息近似模型。"
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"updated": ok, "failed": fail, "asof": data["marketDataAsOf"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
