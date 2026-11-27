"""Persist verified newsroom intervals separately from per-run success.
Never infer coverage of a gap from an adjacent successful fetch."""
from datetime import datetime,timedelta
from pathlib import Path
import json

def dt(value):
    d=datetime.fromisoformat(value)
    if d.tzinfo is None:raise ValueError('unzoned interval')
    return d

def merge(intervals):
    out=[]
    for start,end in sorted(intervals):
        if end<start:raise ValueError('inverted interval')
        if out and start<=out[-1][1]:out[-1]=(out[-1][0],max(out[-1][1],end))
        else:out.append((start,end))
    return out

def gaps(intervals,start,end):
    if end<start:raise ValueError('inverted target')
    cursor=start;out=[]
    for s,e in merge(intervals):
        if e<=cursor:continue
        if s>=end:break
        if s>cursor:out.append((cursor,min(s,end)))
        cursor=max(cursor,min(end,e))
        if cursor==end:break
    if cursor<end:out.append((cursor,end))
    return out

def morning_window(now):
    # Target yesterday's nominal delivery cutoff; use collection time as end.
    # The interval after the latest collection is not verified by this audit.
    cutoff=now.replace(hour=5,minute=30,second=0,microsecond=0)-timedelta(days=1)
    return cutoff,now

def record(prior,audit,now):
    start,end=morning_window(now)
    cutoff=now-timedelta(days=14)
    rows={}
    for e in audit['entries']:
        ticker=e['ticker']
        records=[r for r in prior.get(ticker,[]) if dt(r['end_jst'])>=cutoff]
        if e['status']!='未確認' and e.get('pagination_complete') and e.get('tool_evidence_ref') and e.get('new_success_jst') and not e.get('stale_cache_status'):
            p=e['comparison_period'];s,z=dt(p['start_jst']),dt(p['end_jst'])
            if s<=z<=now and dt(e['new_success_jst'])==z:
                r={'start_jst':s.isoformat(),'end_jst':z.isoformat(),'run_id':audit['run_id'],'receipt_sha256':e['tool_evidence_ref']}
                if r not in records:records.append(r)
        rows[ticker]=records
    return rows

def evaluate(records,order,now):
    start,end=morning_window(now)
    rows=[]
    for ticker in order:
        valid=[(dt(r['start_jst']),dt(r['end_jst'])) for r in records.get(ticker,[]) if r.get('receipt_sha256') and r.get('run_id')]
        missing=gaps(valid,start,end)
        rows.append({'ticker':ticker,'status':'VERIFIED_TO_COLLECTION' if not missing else 'GAP_UNVERIFIED',
             'gaps':[{'start_jst':s.isoformat(),'end_jst':e.isoformat()} for s,e in missing]})
    return {'window_start_jst':start.isoformat(),'window_end_jst':end.isoformat(),'scope':'NEWSROOM_ONLY_TO_COLLECTION_START','rows':rows,'verified':sum(r['status']=='VERIFIED_TO_COLLECTION' for r in rows),'unconfirmed':sum(r['status']=='GAP_UNVERIFIED' for r in rows)}

def report(x):
    lines=['','## 前回朝05:30から今回取得基準時刻までの公式一覧期間連結',
           f'- {x["window_start_jst"]} ～ {x["window_end_jst"]} / 連続確認 {x["verified"]} / 未確認区間あり {x["unconfirmed"]}',
           '- SEC・親会社限定確認はこの網羅率に加算しない。取得基準時刻から実配信までの区間は未確認。']
    for r in x['rows']:
        if r['gaps']:lines.append('- '+r['ticker']+': '+'; '.join(y['start_jst']+' ～ '+y['end_jst'] for y in r['gaps']))
    return '\n'.join(lines)+'\n'
