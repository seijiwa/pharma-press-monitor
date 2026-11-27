"""Preserve independently verified SEC exhibits across unsuccessful later polls.
History is supplemental evidence, never a new filing-window or newsroom credit.
"""
from datetime import datetime,timedelta
from urllib.parse import urlparse
import re

def valid_record(r,now):
    try:
        u=urlparse(r['url'])
        stamp=datetime.fromisoformat(r['receipt']['fetched_jst'])
        filed=datetime.strptime(r['filing_date'],'%Y-%m-%d').date()
        return (r['original_confirmed'] is True and r['issuer_identity_verified'] is True
            and str(r['run_id']).isdigit() and u.scheme=='https' and u.netloc=='www.sec.gov'
            and u.path.startswith('/Archives/edgar/data/') and stamp.tzinfo is not None
            and now-timedelta(days=7)<=stamp<=now and filed<=now.date()
            and r['receipt']['http_status']==200
            and re.fullmatch(r'[a-f0-9]{64}',r['receipt']['sha256'],re.I) is not None)
    except (KeyError,TypeError,ValueError,AttributeError):return False

def records(reg):
    for e in reg.get('entries',[]):
        if e.get('issuer_identity_verified') is not True:continue
        for d in e.get('exhibit_results',[]):
            for x in d.get('exhibits',[]):
                if x.get('original_confirmed') is not True:continue
                yield {'ticker':e['ticker'],'issuer_identity_verified':True,'original_confirmed':True,
                       'run_id':reg.get('run_id'),'filing_date':d['filing_date'],
                       'url':x['url'],'description':x.get('description') or x.get('exhibit_type') or 'EX-99',
                       'receipt':x.get('receipt',{})}

def merge_history(prior,current,now):
    merged={}
    prior_records=prior.get('sec_exhibit_history',[])
    for r in [*prior_records,*records(prior.get('regulatory_observations',{})),*records(current)]:
        if not valid_record(r,now):continue
        key=(r['ticker'],r['url'])
        old=merged.get(key)
        if old is None or datetime.fromisoformat(r['receipt']['fetched_jst'])>datetime.fromisoformat(old['receipt']['fetched_jst']):
            merged[key]=r
    return sorted(merged.values(),key=lambda r:(r['filing_date'],r['ticker'],r['url']),reverse=True)[:500]

def report(reg,history):
    seen={(r['ticker'],r['url']) for r in records(reg)}
    lines=['','## SEC添付資料の先行取得履歴（今回未再確認・補完のみ）']
    for r in history:
        if (r['ticker'],r['url']) in seen:continue
        lines.append(f'- {r["ticker"]} | 提出日 {r["filing_date"]} | 確認時刻 {r["receipt"]["fetched_jst"]} | run {r["run_id"]} | {r["description"]} | {r["url"]}')
    if len(lines)==2:lines.append('- 該当する保存済み添付資料なし（過去7日の保存範囲内）')
    return '\n'.join(lines)+'\n'
