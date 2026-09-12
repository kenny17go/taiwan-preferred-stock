from __future__ import annotations
import json, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
import requests

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'data'/'dividend_events.json'
STOCKS=ROOT/'data'/'preferred_stocks.json'
TW=timezone(timedelta(hours=8))
URLS=[
 ('TWSE除權除息預告','https://openapi.twse.com.tw/v1/exchangeReport/TWT48U_ALL'),
 ('上市公司股利分派情形','https://openapi.twse.com.tw/v1/opendata/t187ap45_L'),
]

def roc_or_iso(v):
    if not v: return None
    s=str(v).strip().replace('/','-')
    m=re.fullmatch(r'(\d{3})(\d{2})(\d{2})',s.replace('-',''))
    if m: return f'{int(m.group(1))+1911:04d}-{m.group(2)}-{m.group(3)}'
    m=re.fullmatch(r'(\d{3})-(\d{1,2})-(\d{1,2})',s)
    if m: return f'{int(m.group(1))+1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m=re.fullmatch(r'(\d{4})-(\d{1,2})-(\d{1,2})',s)
    if m: return f'{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    return None

def num(v):
    try: return float(str(v).replace(',','').strip())
    except: return None

def first(row, needles):
    for k,v in row.items():
        kk=str(k).replace(' ','')
        if any(n in kk for n in needles) and v not in ('',None,'-'): return v
    return None

def normalize(row, allowed, source):
    code=str(first(row,['股票代號','公司代號','證券代號','Code']) or '').strip()
    if code not in allowed: return None
    ex=roc_or_iso(first(row,['除息交易日','除權息交易日','除權（息）交易日','除權除息日期']))
    pay=roc_or_iso(first(row,['現金股利發放日','股利發放日','發放日期','PaymentDate']))
    amt=num(first(row,['每股現金股利','現金股利每股','現金股利','CashDividend']))
    if not ex: return None
    return {'code':code,'exDate':ex,'paymentDate':pay,'amount':amt,'source':source,'status':'official-ex-date'}

def main():
    stocks=json.loads(STOCKS.read_text(encoding='utf-8'))['stocks']
    allowed={str(s['code']) for s in stocks}
    old=json.loads(OUT.read_text(encoding='utf-8')) if OUT.exists() else {'events':[]}
    # retain manually verified ex-date events
    keep=[e for e in old.get('events',[]) if e.get('exDate') and e.get('sourceType')=='manual-verified']
    got=[]; errors=[]
    sess=requests.Session(); sess.headers.update({'User-Agent':'Mozilla/5.0 TaiwanPreferredStockDashboard/1.3-exdate'})
    for label,url in URLS:
        try:
            r=sess.get(url,timeout=30); r.raise_for_status(); rows=r.json()
            if isinstance(rows,dict): rows=rows.get('data') or rows.get('aaData') or []
            for row in rows if isinstance(rows,list) else []:
                if not isinstance(row,dict): continue
                e=normalize(row,allowed,label)
                if e: got.append(e)
        except Exception as e: errors.append(f'{label}: {e}')
    merged={}
    for e in keep+got:
        key=(e.get('code'),e.get('exDate'),e.get('paymentDate'),e.get('amount'))
        merged[key]=e
    events=sorted(merged.values(),key=lambda e:(e.get('exDate') or '9999',e.get('code','')))
    cov={c:{'officialExDates':0,'status':'尚無已公告除息日'} for c in allowed}
    for e in events:
        if e.get('exDate'):
            cov[e['code']]['officialExDates']+=1
            cov[e['code']]['status']='已有官方/已公告除息日'
    payload={
      'version':'1.3-exdate','updatedAt':datetime.now(TW).isoformat(timespec='seconds'),
      'sourcePolicy':'XIRR 一律以官方已公告除息日（exDate）作為股息權利取得日期；paymentDate 僅保留作參考，不參與 XIRR。',
      'sources':[{'label':x,'url':y} for x,y in URLS]+[{'label':'公開資訊觀測站/發行公司公告','url':'https://mops.twse.com.tw/'}],
      'events':events,'coverage':cov,'errors':errors
    }
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'events':len(events),'withExDate':sum(bool(e.get('exDate')) for e in events),'errors':errors},ensure_ascii=False))
if __name__=='__main__': main()
