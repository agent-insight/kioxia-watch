#!/usr/bin/env python3
import csv, io, json, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime, timezone, timedelta

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data' / 'market.json'
UA = {'User-Agent':'Mozilla/5.0 (compatible; KIOXIA-WATCH/9.0; +https://agent-insight.github.io/kioxia-watch/)'}
JST = timezone(timedelta(hours=9))

def get(url, timeout=30):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8')

def yahoo_chart(symbol, days=500):
    now = datetime.now(timezone.utc)
    p2 = int((now + timedelta(days=1)).timestamp())
    p1 = int((now - timedelta(days=days)).timestamp())
    url = ('https://query1.finance.yahoo.com/v8/finance/chart/' + urllib.parse.quote(symbol) +
           f'?period1={p1}&period2={p2}&interval=1d&events=div%2Csplits&includeAdjustedClose=true')
    obj = json.loads(get(url))
    res = obj['chart']['result'][0]
    ts = res.get('timestamp') or []
    q = res['indicators']['quote'][0]
    adj = (res['indicators'].get('adjclose') or [{}])[0].get('adjclose') or q.get('close') or []
    rows = {}
    for i,t in enumerate(ts):
        try:
            raw_close = q['close'][i]
            adj_close = adj[i] if i < len(adj) else raw_close
            if raw_close is None or adj_close is None: continue
            factor = adj_close/raw_close if raw_close else 1.0
            d = datetime.fromtimestamp(t, timezone.utc).date().isoformat()
            rows[d] = {
                'open': q['open'][i]*factor if q['open'][i] is not None else None,
                'high': q['high'][i]*factor if q['high'][i] is not None else None,
                'low': q['low'][i]*factor if q['low'][i] is not None else None,
                'close': adj_close,
                'volume': q['volume'][i] if q.get('volume') and q['volume'][i] is not None else None,
            }
        except (IndexError, TypeError, KeyError, ZeroDivisionError):
            continue
    return rows

def fred(series):
    # FRED CSV's date column has appeared as both DATE and observation_date.
    # Detect it instead of hard-coding the header.
    txt = get(f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}')
    reader = csv.DictReader(io.StringIO(txt))
    rows = {}
    fields = reader.fieldnames or []
    date_col = next((c for c in fields if c.lower() in ('date','observation_date')), fields[0] if fields else None)
    value_col = series if series in fields else next((c for c in fields if c != date_col), None)
    if not date_col or not value_col:
        raise ValueError(f'Unexpected FRED columns: {fields}')
    for row in reader:
        v = row.get(value_col,'.')
        d = row.get(date_col)
        if d and v not in ('','.'):
            try: rows[d] = float(v)
            except ValueError: pass
    if not rows:
        raise ValueError(f'FRED {series}: no observations parsed')
    return rows

def stooq(symbol):
    txt = get(f'https://stooq.com/q/d/l/?s={urllib.parse.quote(symbol)}&i=d')
    rows = {}
    for row in csv.DictReader(io.StringIO(txt)):
        try:
            rows[row['Date']]={'open':float(row['Open']),'high':float(row['High']),'low':float(row['Low']),
                               'close':float(row['Close']),'volume':float(row.get('Volume') or 0)}
        except (ValueError, KeyError): pass
    return rows

def returns(rows, field=None):
    ds=sorted(rows); out={}
    for i in range(1,len(ds)):
        try:
            a=rows[ds[i-1]] if field is None else rows[ds[i-1]][field]
            b=rows[ds[i]] if field is None else rows[ds[i]][field]
            if a not in (None,0) and b is not None: out[ds[i]]=(b/a-1)*100
        except (TypeError,KeyError): pass
    return out

def latest_before(rows, date):
    ds=[d for d in rows if d < date]
    return max(ds) if ds else None

def latest_on_or_before(rows, date):
    ds=[d for d in rows if d <= date]
    return max(ds) if ds else None

m=json.loads(DATA.read_text(encoding='utf-8'))
old={s['date']:s for s in m.get('sessions',[]) if s.get('date')}
status={}

# 1) KIOXIA: rebuild the rolling history from Yahoo Finance chart data.
# Prices use Adj Close ratio for split-consistent OHLC; volume remains reported daily volume.
try:
    kioxia=yahoo_chart('285A.T', days=520)
    status['kioxia']=f'ok:{len(kioxia)}'
except Exception as e:
    kioxia={d:s['kioxia'] for d,s in old.items() if s.get('kioxia')}
    status['kioxia']=f'fallback-existing:{type(e).__name__}:{len(kioxia)}'
kret=returns(kioxia,'close')

# 2) SOX / rates / FX from FRED.
feeds={}
for name,series in [('sox','NASDAQSOX'),('us10y','DGS10'),('usdjpy','DEXJPUS')]:
    try:
        feeds[name]=fred(series); status[name]=f'fred-ok:{len(feeds[name])}'
    except Exception as e:
        feeds[name]={}; status[name]=f'fred-error:{type(e).__name__}'

# Independent market-data fallbacks. FRED remains the preferred source.
if not feeds['sox']:
    try:
        q=yahoo_chart('^SOX', days=520); feeds['sox']={d:x['close'] for d,x in q.items()}; status['sox']=f'yahoo-fallback-ok:{len(q)}'
    except Exception as e: status['sox']+=f'/yahoo-error:{type(e).__name__}'
# FX freshness overlay: FRED H.10 can lag several days. Prefer Yahoo JPY=X when it has a newer observation,
# while retaining FRED as the authoritative historical backbone.
try:
    q=yahoo_chart('JPY=X', days=520); yfx={d:x['close'] for d,x in q.items()}
    if yfx and (not feeds['usdjpy'] or max(yfx) > max(feeds['usdjpy'])):
        feeds['usdjpy'].update(yfx)
        status['usdjpy']=f'fred+yahoo-fresh:{len(feeds["usdjpy"])}'
    elif not feeds['usdjpy']:
        feeds['usdjpy']=yfx; status['usdjpy']=f'yahoo-fallback-ok:{len(yfx)}'
except Exception as e:
    status['usdjpy']+=f'/yahoo-error:{type(e).__name__}'
# ^TNX is a market proxy. Use it only to extend DGS10 when it is newer; historical DGS10 remains preferred.
try:
    q=yahoo_chart('^TNX', days=520); y10={d:x['close'] for d,x in q.items()}
    if y10 and (not feeds['us10y'] or max(y10) > max(feeds['us10y'])):
        feeds['us10y'].update({d:v for d,v in y10.items() if d not in feeds['us10y'] or d>max(feeds['us10y'])})
        status['us10y']=f'fred+tnx-fresh:{len(feeds["us10y"])}'
    elif not feeds['us10y']:
        feeds['us10y']=y10; status['us10y']=f'yahoo-tnx-fallback-ok:{len(y10)}'
except Exception as e:
    status['us10y']+=f'/yahoo-error:{type(e).__name__}'
feedret={k:returns(v) for k,v in feeds.items()}

# 3) US peers: Yahoo first, Stooq fallback.
stocks={}
for name,ysym,ssym in [('sndk','SNDK','sndk.us'),('mu','MU','mu.us'),('nvda','NVDA','nvda.us'),('wdc','WDC','wdc.us')]:
    try:
        stocks[name]=yahoo_chart(ysym, days=520); status[name]=f'yahoo-ok:{len(stocks[name])}'
    except Exception as e1:
        try:
            stocks[name]=stooq(ssym); status[name]=f'stooq-ok:{len(stocks[name])}'
        except Exception as e2:
            stocks[name]={}; status[name]=f'error:{type(e1).__name__}/{type(e2).__name__}'
stockret={k:returns(v,'close') for k,v in stocks.items()}

# Keep roughly the latest year of Kioxia sessions (up to 370 calendar days) while preserving all fetched trading days.
if kioxia:
    maxd=max(kioxia)
    cutoff=(datetime.fromisoformat(maxd)-timedelta(days=370)).date().isoformat()
    kdates=[d for d in sorted(kioxia) if d>=cutoff]
else:
    kdates=sorted(old)

sessions=[]
for jd in kdates:
    k=kioxia[jd]
    s={
      'date':jd,
      'kioxia':{'open':k.get('open'),'high':k.get('high'),'low':k.get('low'),'close':k.get('close'),
                'change_pct':kret.get(jd),'volume':k.get('volume')},
      'verified':True,
      'price_basis':'yahoo_adjclose_split_consistent',
      'volume_basis':'reported_daily_volume' if k.get('volume') is not None else 'unavailable',
      'us_session_date':None,'sox':None,'sndk':None,'mu':None,'nvda':None,'wdc':None,'us10y':None,'usdjpy':None
    }
    for name,rows in feeds.items():
        d=latest_before(rows,jd)
        if not d: continue
        if name=='sox':
            s[name]={'close':rows[d],'change_pct':feedret[name].get(d),'date':d,'source':'FRED NASDAQSOX / Nasdaq'}
            s['us_session_date']=d
        else:
            src='FRED DGS10 / Federal Reserve H.15' if name=='us10y' else 'FRED DEXJPUS / Federal Reserve H.10'
            s[name]={'value':rows[d],'change_pct':feedret[name].get(d),'date':d,'source':src}
    for name,rows in stocks.items():
        d=latest_before(rows,jd)
        if d:
            s[name]={'close':rows[d]['close'],'change_pct':stockret[name].get(d),'date':d,'source':'Yahoo Finance chart / Stooq fallback'}
    sessions.append(s)

m['sessions']=sessions
meta=m.setdefault('meta',{})
meta['version']='9.0-nearest-analog'
meta['as_of']=sessions[-1]['date'] if sessions else meta.get('as_of')
meta['source_universe']=len(sessions)
meta['loaded_kioxia_rows']=len(sessions)
meta['loaded_daily_rows']=len(sessions)
meta['target_period']={'from':sessions[0]['date'] if sessions else None,'to':sessions[-1]['date'] if sessions else None,'source_rows':len(sessions)}
meta['last_automation_run_jst']=datetime.now(JST).isoformat(timespec='seconds')
meta['automation_status']=status
# Latest independently available market observations for the NEXT JPX session signal.
# These are deliberately not forced onto a future JPX date.
latest_context={}
for name,rows in feeds.items():
    if rows:
        d=max(rows)
        latest_context[name]={'date':d,'value':rows[d],'change_pct':feedret[name].get(d)}
for name,rows in stocks.items():
    if rows:
        d=max(rows)
        latest_context[name]={'date':d,'close':rows[d].get('close'),'change_pct':stockret[name].get(d)}
meta['latest_context']=latest_context
meta['latest_context_generated_jst']=datetime.now(JST).isoformat(timespec='seconds')
meta['no_imputation']=True
meta['source_policy']={
 'kioxia':'Yahoo Finance chart 285A.T; Adj Close ratio used for split-consistent OHLC; reported daily volume',
 'sox':'FRED NASDAQSOX / Nasdaq, Inc.',
 'sndk':'Yahoo Finance SNDK; Stooq fallback', 'mu':'Yahoo Finance MU; Stooq fallback',
 'nvda':'Yahoo Finance NVDA; Stooq fallback', 'wdc':'Yahoo Finance WDC; Stooq fallback',
 'us10y':'FRED DGS10 / Federal Reserve H.15; Yahoo ^TNX freshness extension', 'usdjpy':'FRED DEXJPUS / Federal Reserve H.10; Yahoo JPY=X freshness extension'}
DATA.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'sessions':len(sessions),'latest':sessions[-1]['date'] if sessions else None,'status':status},ensure_ascii=False,indent=2))
