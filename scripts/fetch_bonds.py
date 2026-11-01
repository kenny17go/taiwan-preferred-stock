#!/usr/bin/env python3
"""Fetch TPEx bond snapshots conservatively; only replace files after validation."""
import json, os, pathlib, time, urllib.error, urllib.request
from datetime import datetime, timezone
ROOT=pathlib.Path(__file__).resolve().parents[1]/"data"/"bonds"
ROOT.mkdir(parents=True,exist_ok=True)
status={"checked_at_utc":datetime.now(timezone.utc).isoformat(),"sources":{}}
for i,series in enumerate((3,4,10,11)):
    if i: time.sleep(4)
    url=f"https://www.tpex.org.tw/openapi/v1/bond_ISSBD{series}_data"
    req=urllib.request.Request(url,headers={"User-Agent":"TaiwanPreferredStockBondMonitor/0.1 (public open data; daily)" ,"Accept":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=35) as response:
            data=json.load(response)
        if not isinstance(data,list) or not data or not isinstance(data[0],dict) or "BondCode" not in data[0]:
            raise ValueError("Unexpected API schema / empty result; preserving prior snapshot")
        # Preserve raw API records: some endpoints contain duplicate rows. Deduplicate only in UI.
        target=ROOT/f"ISSBD{series}.json"
        new=json.dumps(data,ensure_ascii=False,separators=(",",":"),sort_keys=True)+"\n"
        if not target.exists() or target.read_text(encoding="utf-8")!=new:
            target.write_text(new,encoding="utf-8")
        status["sources"][f"ISSBD{series}"]={"ok":True,"records":len(data),"date":max(str(x.get("Date","")) for x in data)}
    except (urllib.error.URLError,TimeoutError,ValueError,KeyError,json.JSONDecodeError) as e:
        status["sources"][f"ISSBD{series}"]={"ok":False,"error":str(e)[:240]}
        print(f"ISSBD{series}: {e}",flush=True)
# No status timestamp committed: avoid commits when bond data is unchanged.
print(json.dumps(status,ensure_ascii=False,indent=2))
if not all(v["ok"] for v in status["sources"].values()):
    raise SystemExit("One or more API sources failed; prior successful files preserved")
