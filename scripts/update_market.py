from __future__ import annotations
import json, math, time
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from calendar import monthrange
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'preferred_stocks.json'
MIS_URL='https://mis.twse.com.tw/stock/api/getStockInfo.jsp'
TW=timezone(timedelta(hours=8))

def fnum(v):
    try:
        if v in (None,'','-','--'): return None
        x=float(str(v).replace(',','').strip()); return x if math.isfinite(x) else None
    except: return None

def quote_one(session,code):
    for market in ('tse','otc'):
        r=session.get(MIS_URL,params={'ex_ch':f'{market}_{code}.tw','json':'1','delay':'0'},timeout=20)
        r.raise_for_status(); arr=(r.json().get('msgArray') or [])
        if not arr: continue
        q=arr[0]; price=fnum(q.get('z')) or fnum(q.get('y'))
        if price is None: continue
        return {'price':price,'market':market,'quoteDate':q.get('d'),'quoteTime':q.get('t'),'previousClose':fnum(q.get('y')),
                'open':fnum(q.get('o')),'high':fnum(q.get('h')),'low':fnum(q.get('l')),'volume':fnum(q.get('v'))}
    return None

def add_months(dt,months):
    y=dt.year+(dt.month-1+months)//12; m=(dt.month-1+months)%12+1
    return date(y,m,min(dt.day,monthrange(y,m)[1]))

def next_reset_date(stock,asof):
    fc=stock.get('firstCallDate'); cyc=stock.get('resetCycleYears')
    if not fc or not cyc: return None
    try: dt=date.fromisoformat(fc); months=round(float(cyc)*12)
    except: return None
    while dt<=asof: dt=add_months(dt,months)
    return dt

def official_events_for(code,events):
    out=[]
    for e in events:
        if str(e.get('code'))!=str(code) or not e.get('exDate'): continue
        try: out.append((date.fromisoformat(e['exDate']),fnum(e.get('amount'))))
        except: pass
    return sorted(out)

def project_ex_dates(stock,asof,horizon,events):
    ev=official_events_for(stock.get('code'),events)
    future=[(dt,amt,'official') for dt,amt in ev if asof<dt<=horizon and (amt or stock.get('div'))]
    if future: return future
    # no future official announcement: infer seasonal month/day from newest official event, then from static hint
    anchor=ev[-1][0] if ev else None
    if anchor is None and stock.get('lastExDateHint'):
        try: anchor=date.fromisoformat(stock['lastExDateHint'])
        except: anchor=None
    if anchor is None: return []
    amount=fnum(stock.get('div'))
    if not amount or amount<=0:return []
    out=[]
    for y in range(asof.year,horizon.year+1):
        try: dt=date(y,anchor.month,anchor.day)
        except: dt=date(y,anchor.month,min(anchor.day,monthrange(y,anchor.month)[1]))
        if asof<dt<=horizon: out.append((dt,amount,'projected'))
    return out

def xnpv(rate,flows):
    if rate<=-0.999999:return float('inf')
    d0=flows[0][0]
    return sum(a/((1+rate)**((d-d0).days/365.0)) for d,a in flows)

def xirr(flows):
    flows=sorted(flows,key=lambda x:x[0])
    if len(flows)<2 or not any(a<0 for _,a in flows) or not any(a>0 for _,a in flows):return None
    lo,hi=-.95,10.0; flo,fhi=xnpv(lo,flows),xnpv(hi,flows)
    if flo*fhi>0:return None
    for _ in range(180):
        mid=(lo+hi)/2; fm=xnpv(mid,flows)
        if abs(fm)<1e-10:break
        if flo*fm<=0:hi=mid;fhi=fm
        else:lo=mid;flo=fm
    return round((lo+hi)/2*100,2)

def lifecycle(stock,asof):
    if not stock.get('call'): return 'not_callable','不可贖回',None
    fc=stock.get('firstCallDate') or (stock.get('callDate') if stock.get('callDate') not in (None,'-','待核對') else None)
    if not fc:return 'callable_unknown_date','可贖回（首次日期待核對）',None
    try:d=date.fromisoformat(fc)
    except:return 'callable_unknown_date','可贖回（首次日期待核對）',None
    if d>asof:return 'future_first_call','尚未到首次可贖回日',d
    return 'callable_now','已進入可贖回期間',d

def recalc_returns(stock,asof,events):
    state,label,fc=lifecycle(stock,asof)
    stock['callability']=state;stock['callabilityLabel']=label
    nr=next_reset_date(stock,asof);stock['nextResetDate']=nr.isoformat() if nr else None
    price=fnum(stock.get('price')); div=fnum(stock.get('div')); callp=fnum(stock.get('callPrice')) or fnum(stock.get('par'))
    stock['callIrr']=None; stock['irr']=None
    horizon=None; mode=None
    if state=='future_first_call':horizon=fc;mode='first-call'
    elif state=='callable_now' and nr:horizon=nr;mode='continuation'
    if not horizon or not price or not div or not callp:
        stock['xirr']=None;stock['xirrStatus']='unavailable';stock['cashflowCoverage']='資料不足'
        stock['callIrrMethod']='不可贖回或缺少明確未來首次可贖回日' if state!='callable_now' else '已進入可隨時贖回期間，無單一未來贖回日'
        stock['xirrMethod']='缺少可定義情境終點或股息資料';return
    exs=project_ex_dates(stock,asof,horizon,events)
    flows=[(asof,-price)]+[(dt,float(amt or div)) for dt,amt,_ in exs]
    # At redemption, preferred-share terms commonly settle redemption principal; V1.4 does not invent a separate accrued coupon unless contract-specific data is available.
    flows.append((horizon,callp))
    val=xirr(flows)
    stock['xirr']=val;stock['xirrCashflowCount']=len(flows)-1
    any_projected=any(src=='projected' for _,_,src in exs)
    if mode=='first-call':
        # Avoid misleading astronomical annualization when the first-call date is extremely close.
        days=(horizon-asof).days
        if days>=60:
            stock['callIrr']=val;stock['irr']=val;stock['callIrrStatus']='estimated' if any_projected else 'official-dates'
        else:
            stock['callIrr']=None;stock['irr']=None;stock['callIrrStatus']='too-short'
        stock['callIrrMethod']='首次可贖回情境 IRR：除息日股息 + 贖回本金，Actual/365；距可贖回日過短時不顯示年化值'
        stock['xirrMethod']='除息日基準 XIRR（未公告未來除息日採最近季節性估算）'
    else:
        stock['callIrrStatus']='callable-now';stock['callIrrMethod']='已進入可隨時贖回期間，無單一未來贖回日，不硬算單一 YTC'
        stock['xirrMethod']='續存至下一重設日情境 XIRR（終值以贖回價/面額作比較假設）'
    stock['xirrStatus']='estimated' if any_projected else 'official-dates'
    stock['cashflowCoverage']='估算（含未公告未來除息日）' if any_projected else '官方除息日覆蓋'

def main():
    data=json.loads(OUT.read_text(encoding='utf-8'));stocks=data.get('stocks',[])
    try: events=json.loads((ROOT/'data'/'dividend_events.json').read_text(encoding='utf-8')).get('events',[])
    except: events=[]
    sess=requests.Session();sess.headers.update({'User-Agent':'Mozilla/5.0 TaiwanPreferredStockDashboard/1.4','Referer':'https://mis.twse.com.tw/stock/fibest.jsp'})
    now=datetime.now(TW);ok=0;fail=[]
    for s in stocks:
        code=str(s.get('code','')).strip()
        try:
            q=quote_one(sess,code)
            if q:
                old=s.get('price');s.update(q);s['lastPriceBeforeUpdate']=old
                if fnum(s.get('div')) and q['price']>0:s['yield']=round(float(s['div'])/q['price']*100,2)
                if q.get('previousClose'):s['changePct']=round((q['price']/q['previousClose']-1)*100,2)
                ok+=1
            else:fail.append(code)
            recalc_returns(s,now.date(),events)
            s['marketUpdatedAt']=now.isoformat(timespec='seconds');time.sleep(.1)
        except Exception as exc:
            fail.append(code);s['marketUpdateError']=str(exc)[:240]
    data['version']='1.4';data['marketDataAsOf']=now.date().isoformat();data['marketUpdatedAt']=now.isoformat(timespec='seconds')
    data['marketUpdateStatus']='ok' if ok else 'stale';data['marketUpdateSuccessCount']=ok;data['marketUpdateFailCodes']=fail
    data['marketSourceLabel']='TWSE MIS / TPEx quote fallback';data['marketSourceUrl']=MIS_URL
    data['irrPolicy']='V1.4：首次可贖回日在未來才顯示可贖回情境 IRR；已進入可隨時贖回期間不強行指定唯一 YTC。XIRR 採除息日；未公告未來除息日採最近季節性估算並明確標示。'
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'updated':ok,'failed':fail,'asof':data['marketDataAsOf']},ensure_ascii=False))
if __name__=='__main__':main()
