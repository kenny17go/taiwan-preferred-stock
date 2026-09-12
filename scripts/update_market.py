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


def approx_ytc(price, annual_div, call_price, call_date, asof=None):
    """可贖回日 IRR/YTC：年配息近似，但期限使用實際可贖回日。"""
    if not all(isinstance(x, (int,float)) and x > 0 for x in (price, annual_div, call_price)):
        return None
    try:
        d = date.fromisoformat(str(call_date))
    except Exception:
        return None
    base = asof or datetime.now(TW).date()
    days = (d - base).days
    if days <= 7:
        return None
    years = days / 365.25
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
    for _ in range(140):
        mid=(lo+hi)/2
        if pv(mid) > price: lo=mid
        else: hi=mid
    return round((lo+hi)/2*100, 2)


def xnpv(rate, cashflows):
    if rate <= -0.999999: return float('inf')
    d0=cashflows[0][0]
    return sum(amount / ((1+rate)**((d-d0).days/365.0)) for d,amount in cashflows)


def xirr(cashflows):
    cashflows=sorted(cashflows,key=lambda x:x[0])
    if len(cashflows)<2 or not any(a<0 for _,a in cashflows) or not any(a>0 for _,a in cashflows): return None
    lo,hi=-0.95,5.0
    flo,fhi=xnpv(lo,cashflows),xnpv(hi,cashflows)
    if flo*fhi>0: return None
    for _ in range(160):
        mid=(lo+hi)/2; fm=xnpv(mid,cashflows)
        if abs(fm)<1e-10: break
        if flo*fm<=0: hi=mid; fhi=fm
        else: lo=mid; flo=fm
    return round((lo+hi)/2*100,2)


def date_aware_xirr(stock, price, asof, events):
    try: call_date=date.fromisoformat(str(stock.get('callDate')))
    except Exception: return None,'缺少未來可贖回日',0
    call_price=stock.get('callPrice')
    if not isinstance(call_price,(int,float)) or call_price<=0 or call_date<=asof: return None,'缺少有效贖回價/日期',0
    ev=[]
    for e in events:
        if str(e.get('code'))!=str(stock.get('code')): continue
        try:
            ex=date.fromisoformat(e['exDate']) if e.get('exDate') else None
            amt=float(e.get('amount'))
        except Exception: continue
        # V1.3 policy: use ex-dividend date as the dividend entitlement date for XIRR.
        if ex and amt>0 and ex<=call_date and ex>asof: ev.append((ex,amt))
    if not ev: return None,'尚無未來已公告除息日期；不以年化近似冒充 XIRR',0
    flows=[(asof,-price)]+ev+[(call_date,float(call_price))]
    return xirr(flows),'除息日基準 XIRR（官方除息日 + 精確贖回日）',len(ev)

def main():
    data = json.loads(OUT.read_text(encoding="utf-8"))
    stocks = data.get("stocks", [])
    div_path = ROOT / "data" / "dividend_events.json"
    try:
        div_data = json.loads(div_path.read_text(encoding="utf-8"))
        dividend_events = div_data.get("events", [])
    except Exception:
        dividend_events = []
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (compatible; TaiwanPreferredStockDashboard/1.3.2; +https://github.com/)",
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
            asof = now.date()

            # 1) 可贖回日 IRR / YTC：獨立存在，絕不受除息日資料影響。
            prev_call_irr = s.get("callIrr")
            call_irr = approx_ytc(q["price"], s.get("div"), s.get("callPrice"), s.get("callDate"), asof)
            if call_irr is not None:
                s["callIrr"] = call_irr
                s["irr"] = call_irr  # backward-compatible alias
                s["callIrrMethod"] = "可贖回日 IRR/YTC（最新市價＋年配息近似＋實際贖回日）"
                s["callIrrStatus"] = "refreshed"
            else:
                # 已過可贖回日或條件不足時，不因 XIRR 更新而清除既有 IRR。
                if isinstance(prev_call_irr,(int,float)):
                    s["callIrr"] = prev_call_irr
                    s["irr"] = prev_call_irr
                    s["callIrrMethod"] = s.get("callIrrMethod") or "沿用既有可贖回日 IRR"
                    s["callIrrStatus"] = "carried-forward"
                else:
                    s["callIrr"] = None
                    s["irr"] = None
                    s["callIrrMethod"] = "缺少未來可贖回日／贖回價／年股息，無法估算"
                    s["callIrrStatus"] = "unavailable"

            # 2) 除息日基準 XIRR：完全獨立欄位。除息資料只刷新 XIRR，不碰 IRR。
            prev_xirr = s.get("xirr")
            prev_method = s.get("xirrMethod") or s.get("irrMethod")
            prev_count = s.get("xirrCashflowCount")
            xv, method, event_count = date_aware_xirr(s, q["price"], asof, dividend_events)
            if xv is not None:
                s["xirr"] = xv
                s["xirrMethod"] = method
                s["irrMethod"] = method  # legacy display compatibility only
                s["xirrCashflowCount"] = event_count
                s["cashflowCoverage"] = "可計算（除息日資料完整）"
                s["xirrStatus"] = "refreshed"
            else:
                if isinstance(prev_xirr,(int,float)):
                    s["xirr"] = prev_xirr
                    s["xirrMethod"] = (prev_method or "前次有效 XIRR") + "；除息日資料不足，本次不覆蓋"
                    s["irrMethod"] = s["xirrMethod"]
                    s["xirrCashflowCount"] = prev_count
                    s["cashflowCoverage"] = "沿用前次有效 XIRR"
                    s["xirrStatus"] = "carried-forward"
                else:
                    s["xirr"] = None
                    s["xirrMethod"] = method
                    s["irrMethod"] = method
                    s["xirrCashflowCount"] = event_count
                    s["cashflowCoverage"] = "尚無可用 XIRR"
                    s["xirrStatus"] = "unavailable"
            s["lastPriceBeforeUpdate"] = old_price
            s["marketUpdatedAt"] = now.isoformat(timespec="seconds")
            ok += 1
            time.sleep(0.12)
        except Exception as e:
            fail.append(code)
            s["marketUpdateError"] = str(e)[:240]
    data["version"] = "1.3.2"
    data["marketDataAsOf"] = now.date().isoformat()
    data["marketUpdatedAt"] = now.isoformat(timespec="seconds")
    data["marketUpdateStatus"] = "ok" if ok else "stale"
    data["marketUpdateSuccessCount"] = ok
    data["marketUpdateFailCodes"] = fail
    data["marketSourceLabel"] = "TWSE MIS / TPEx quote fallback"
    data["marketSourceUrl"] = MIS_URL
    data["irrPolicy"] = "V1.3.2：可贖回日 IRR/YTC 與除息日基準 XIRR 完全分離；除息資料不足不會影響 IRR。"
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"updated": ok, "failed": fail, "asof": data["marketDataAsOf"]}, ensure_ascii=False))

if __name__ == "__main__":
    main()
