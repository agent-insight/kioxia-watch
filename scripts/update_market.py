#!/usr/bin/env python3
import csv, io, json, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/"data"/"market.json"
UA={"User-Agent":"Mozilla/5.0 KIOXIA-WATCH/5.0"}

def get(url, timeout=25):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return r.read().decode("utf-8")

def fred(series):
    url=f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    rows={}
    for row in csv.DictReader(io.StringIO(get(url))):
        v=row.get(series,".")
        if v not in ("","."):
            try: rows[row["DATE"]]=float(v)
            except: pass
    return rows

def stooq(symbol):
    # Daily CSV; useful for US equities. If blocked/empty, caller simply leaves null.
    url=f"https://stooq.com/q/d/l/?s={urllib.parse.quote(symbol)}&i=d"
    txt=get(url)
    rows={}
    for row in csv.DictReader(io.StringIO(txt)):
        try:
            rows[row["Date"]]={"open":float(row["Open"]),"high":float(row["High"]),
                "low":float(row["Low"]),"close":float(row["Close"]),"volume":float(row.get("Volume") or 0)}
        except: pass
    return rows

def ret_series(rows, key=None):
    ds=sorted(rows); out={}
    for i,d in enumerate(ds):
        if i==0: continue
        a=rows[ds[i-1]] if key is None else rows[ds[i-1]][key]
        b=rows[d] if key is None else rows[d][key]
        if a: out[d]=(b/a-1)*100
    return out

def latest_before(rows, date):
    ds=[d for d in rows if d<date]
    return max(ds) if ds else None

m=json.loads(DATA.read_text(encoding="utf-8"))
sessions=m.get("sessions",[])
status={}

# Official macro/index feeds.
feeds={}
for name,series in [("sox","NASDAQSOX"),("us10y","DGS10"),("usdjpy","DEXJPUS")]:
    try:
        feeds[name]=fred(series); status[name]=f"ok:{len(feeds[name])}"
    except Exception as e:
        feeds[name]={}; status[name]=f"error:{type(e).__name__}"

# US equity distributed feed. Stooq symbols are attempted; no data is invented if unavailable.
stocks={}
for name,sym in [("sndk","sndk.us"),("mu","mu.us"),("nvda","nvda.us"),("wdc","wdc.us")]:
    try:
        stocks[name]=stooq(sym); status[name]=f"ok:{len(stocks[name])}"
    except Exception as e:
        stocks[name]={}; status[name]=f"error:{type(e).__name__}"

feed_rets={k:ret_series(v) for k,v in feeds.items()}
stock_rets={k:ret_series(v,"close") for k,v in stocks.items()}

for s in sessions:
    jd=s["date"]
    for name,rows in feeds.items():
        d=latest_before(rows,jd)
        if not d: continue
        if name=="sox":
            s[name]={"close":rows[d],"change_pct":feed_rets[name].get(d),"date":d,"source":"FRED NASDAQSOX / Nasdaq"}
            s["us_session_date"]=d
        else:
            s[name]={"value":rows[d],"change_pct":feed_rets[name].get(d),"date":d,
                     "source":"FRED "+("DGS10 / Federal Reserve" if name=="us10y" else "DEXJPUS / Federal Reserve")}
    for name,rows in stocks.items():
        d=latest_before(rows,jd)
        if d:
            s[name]={"close":rows[d]["close"],"change_pct":stock_rets[name].get(d),"date":d,"source":"Stooq daily CSV"}

jst=timezone(timedelta(hours=9))
m.setdefault("meta",{})["version"]="5.0-auto"
m["meta"]["last_automation_run_jst"]=datetime.now(jst).isoformat(timespec="seconds")
m["meta"]["automation_status"]=status
m["meta"]["no_imputation"]=True
DATA.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps(status,ensure_ascii=False,indent=2))
