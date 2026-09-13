from __future__ import annotations
import json, math, time
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from calendar import monthrange
from statistics import median
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'preferred_stocks.json'
MIS_URL='https://mis.twse.com.tw/stock/api/getStockInfo.jsp'
TWSE_DAY_URL='https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY'
TPEX_DAY_URL='https://www.tpex.org.tw/web/stock/aftertrading/daily_trading_info/st43_result.php'
TW=timezone(timedelta(hours=8))

def fnum(v):
    try:
        if v in (None,'','-','--'): return None
        x=float(str(v).replace(',','').strip())
        return x if math.isfinite(x) else None
    except: return None

def quote_one(session,code):
    for market in ('tse','otc'):
        r=session.get(MIS_URL,params={'ex_ch':f'{market}_{code}.tw','json':'1','delay':'0'},timeout=20)
        r.raise_for_status()
        arr=(r.json().get('msgArray') or [])
        if not arr: continue
        q=arr[0]
        price=fnum(q.get('z')) or fnum(q.get('y'))
        if price is None: continue
        return {'price':price,'market':market,'quoteDate':q.get('d'),'quoteTime':q.get('t'),
                'previousClose':fnum(q.get('y')),'open':fnum(q.get('o')),'high':fnum(q.get('h')),
                'low':fnum(q.get('l')),'volume':fnum(q.get('v'))}
    return None

def month_keys(asof,n=3):
    y,m=asof.year,asof.month
    out=[]
    for _ in range(n):
        out.append((y,m))
        m-=1
        if m==0:y-=1;m=12
    return out

def roc_to_iso(s):
    try:
        p=str(s).strip().split('/')
        return f'{int(p[0])+1911:04d}-{int(p[1]):02d}-{int(p[2]):02d}'
    except:return str(s)

def fetch_twse_volume_history(session,code,asof):
    rows=[]
    for y,m in month_keys(asof,3):
        r=session.get(TWSE_DAY_URL,params={'response':'json','date':f'{y}{m:02d}01','stockNo':code},timeout=20)
        r.raise_for_status()
        j=r.json()
        if j.get('stat')!='OK': continue
        for row in j.get('data',[]):
            if len(row)<2: continue
            vol=fnum(row[1])
            if vol is None: continue
            rows.append({'date':roc_to_iso(row[0]),'volume':round(vol/1000,3)})
        time.sleep(.08)
    dedup={x['date']:x for x in rows}
    return [dedup[k] for k in sorted(dedup)][-20:]

def fetch_tpex_volume_history(session,code,asof):
    rows=[]
    for y,m in month_keys(asof,3):
        roc_y=y-1911
        r=session.get(TPEX_DAY_URL,params={'l':'zh-tw','d':f'{roc_y}/{m:02d}','stkno':code},timeout=20)
        r.raise_for_status()
        j=r.json()
        for row in (j.get('aaData') or []):
            if len(row)<2: continue
            vol=fnum(row[1])
            if vol is None: continue
            rows.append({'date':roc_to_iso(row[0]),'volume':round(vol/1000,3)})
        time.sleep(.08)
    dedup={x['date']:x for x in rows}
    return [dedup[k] for k in sorted(dedup)][-20:]

def update_volume_median(session,stock,asof):
    code=str(stock.get('code','')).strip()
    market=stock.get('market')
    history=[]
    try:
        history = fetch_tpex_volume_history(session,code,asof) if market=='otc' else fetch_twse_volume_history(session,code,asof)
    except Exception as exc:
        # Historical endpoint may occasionally fail; keep accumulated history and append today's quote.
        history=list(stock.get('volumeHistory20') or [])
        qdate=str(stock.get('quoteDate') or '')
        if len(qdate)==8 and stock.get('volume') is not None:
            iso=f'{qdate[:4]}-{qdate[4:6]}-{qdate[6:8]}'
            history=[x for x in history if x.get('date')!=iso]
            history.append({'date':iso,'volume':fnum(stock.get('volume')) or 0})
        history=sorted(history,key=lambda x:x.get('date',''))[-20:]
        stock['volumeHistoryError']=str(exc)[:180]
    if history:
        stock['volumeHistory20']=history[-20:]
        vals=[fnum(x.get('volume')) for x in stock['volumeHistory20']]
        vals=[v for v in vals if v is not None]
        stock['volumeMedian20']=round(float(median(vals)),2) if vals else None
        stock['volumeMedian20Samples']=len(vals)
        stock['volumeMedian20AsOf']=stock['volumeHistory20'][-1].get('date')
    else:
        stock['volumeMedian20']=fnum(stock.get('volume'))
        stock['volumeMedian20Samples']=1 if stock.get('volume') is not None else 0

def add_months(dt,months):
    y=dt.year+(dt.month-1+months)//12
    m=(dt.month-1+months)%12+1
    return date(y,m,min(dt.day,monthrange(y,m)[1]))

def next_reset_date(stock,asof):
    fc=stock.get('firstCallDate');cyc=stock.get('resetCycleYears')
    if not fc or not cyc:return None
    try:dt=date.fromisoformat(fc);months=round(float(cyc)*12)
    except:return None
    while dt<=asof:dt=add_months(dt,months)
    return dt

def official_events_for(code,events):
    out=[]
    for e in events:
        if str(e.get('code'))!=str(code) or not e.get('exDate'):continue
        try:out.append((date.fromisoformat(e['exDate']),fnum(e.get('amount'))))
        except:pass
    return sorted(out)

def project_ex_dates(stock,asof,horizon,events):
    ev=official_events_for(stock.get('code'),events)
    future=[(dt,amt,'official') for dt,amt in ev if asof<dt<=horizon and (amt or stock.get('div'))]
    if future:return future
    anchor=ev[-1][0] if ev else None
    if anchor is None and stock.get('lastExDateHint'):
        try:anchor=date.fromisoformat(stock['lastExDateHint'])
        except:anchor=None
    if anchor is None:return []
    amount=fnum(stock.get('div'))
    if not amount or amount<=0:return []
    out=[]
    for y in range(asof.year,horizon.year+1):
        try:dt=date(y,anchor.month,anchor.day)
        except:dt=date(y,anchor.month,min(anchor.day,monthrange(y,anchor.month)[1]))
        if asof<dt<=horizon:out.append((dt,amount,'projected'))
    return out

def xnpv(rate,flows):
    if rate<=-0.999999:return float('inf')
    d0=flows[0][0]
    return sum(a/((1+rate)**((d-d0).days/365.0)) for d,a in flows)

def xirr(flows):
    flows=sorted(flows,key=lambda x:x[0])
    if len(flows)<2 or not any(a<0 for _,a in flows) or not any(a>0 for _,a in flows):return None
    lo,hi=-.95,10.0
    flo,fhi=xnpv(lo,flows),xnpv(hi,flows)
    if flo*fhi>0:return None
    for _ in range(180):
        mid=(lo+hi)/2;fm=xnpv(mid,flows)
        if abs(fm)<1e-10:break
        if flo*fm<=0:hi=mid;fhi=fm
        else:lo=mid;flo=fm
    return round((lo+hi)/2*100,2)

def lifecycle(stock,asof):
    if not stock.get('call'):return 'not_callable','不可贖回',None
    fc=stock.get('firstCallDate') or (stock.get('callDate') if stock.get('callDate') not in (None,'-','待核對') else None)
    if not fc:return 'callable_unknown_date','可贖回（首次日期待核對）',None
    try:d=date.fromisoformat(fc)
    except:return 'callable_unknown_date','可贖回（首次日期待核對）',None
    if d>asof:return 'future_first_call','尚未到首次可贖回日',d
    return 'callable_now','已進入可贖回期間',d

def recalc_returns(stock,asof,events):
    state,label,fc=lifecycle(stock,asof)
    stock['callability']=state;stock['callabilityLabel']=label
    nr=next_reset_date(stock,asof)
    stock['nextResetDate']=nr.isoformat() if nr else None
    price=fnum(stock.get('price'));div=fnum(stock.get('div'));callp=fnum(stock.get('callPrice')) or fnum(stock.get('par'))
    stock['callIrr']=None;stock['irr']=None
    horizon=None;mode=None
    if state=='future_first_call':horizon=fc;mode='first-call'
    elif state=='callable_now' and nr:horizon=nr;mode='continuation'
    if not horizon or not price or not div or not callp:
        stock['xirr']=None;stock['xirrStatus']='unavailable';stock['cashflowCoverage']='資料不足'
        stock['callIrrMethod']='不可贖回或缺少明確未來首次可贖回日' if state!='callable_now' else '已進入可隨時贖回期間，無單一未來贖回日'
        stock['xirrMethod']='缺少可定義情境終點或股息資料';return
    exs=project_ex_dates(stock,asof,horizon,events)
    flows=[(asof,-price)]+[(dt,float(amt or div)) for dt,amt,_ in exs]
    flows.append((horizon,callp))
    val=xirr(flows)
    stock['xirr']=val;stock['xirrCashflowCount']=len(flows)-1
    any_projected=any(src=='projected' for _,_,src in exs)
    if mode=='first-call':
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
    try:events=json.loads((ROOT/'data'/'dividend_events.json').read_text(encoding='utf-8')).get('events',[])
    except:events=[]
    sess=requests.Session()
    sess.headers.update({'User-Agent':'Mozilla/5.0 TaiwanPreferredStockDashboard/1.5.9','Referer':'https://mis.twse.com.tw/stock/fibest.jsp'})
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
            update_volume_median(sess,s,now.date())
            s['marketUpdatedAt']=now.isoformat(timespec='seconds')
            time.sleep(.08)
        except Exception as exc:
            fail.append(code);s['marketUpdateError']=str(exc)[:240]
    data['version']='1.5.9'
    data['marketDataAsOf']=now.date().isoformat()
    data['marketUpdatedAt']=now.isoformat(timespec='seconds')
    data['marketUpdateStatus']='ok' if ok else 'stale'
    data['marketUpdateSuccessCount']=ok
    data['marketUpdateFailCodes']=sorted(set(fail))
    data['marketSourceLabel']='TWSE MIS / TPEx quote fallback + official historical volume'
    data['marketSourceUrl']=MIS_URL
    data['scorePolicy']='V1.5.9：綜合評分=80%風險調整收益率+20%近20個交易日日成交量中位數；前端收益/流動性皆做29檔相對標準化，流動性採log尺度。'
    OUT.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'updated':ok,'failed':sorted(set(fail)),'asof':data['marketDataAsOf'],
                      'median20_samples':{s.get('code'):s.get('volumeMedian20Samples') for s in stocks}},ensure_ascii=False))

if __name__=='__main__':
    main()
