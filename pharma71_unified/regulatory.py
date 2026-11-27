"""SEC filing metadata only: never counts as official newsroom coverage."""
import argparse,hashlib,json,os,re,time
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlparse
import requests
from pharma46.fetch import JST
from pharma46.cli import save_json
from .registry import load_registry
from .sec_exhibits import collect_exhibits,summarize
from .sec_identity import resolve,verify_identity
from .tdnet import run as tdnet_run
from .hkex import run as hkex_run

FORMS={'8-K','8-K/A','6-K','6-K/A'}
def parse_tickers(data):
    out={}
    for x in data.values():
        t=x['ticker'].upper();cik=int(x['cik_str'])
        if t in out and out[t]!=cik:raise ValueError('ambiguous SEC ticker')
        out[t]=cik
    return out

def parse_submissions(data,ticker,cik,start,end):
    if int(data['cik'])!=cik or ticker not in [x.upper() for x in data['tickers']]:
        raise ValueError('issuer identity mismatch')
    recent=data['filings']['recent']
    keys=('accessionNumber','filingDate','form','primaryDocument')
    if len({len(recent[k]) for k in keys})!=1:raise ValueError('inconsistent SEC columns')
    rows=[]
    for acc,dt,form,doc in zip(*(recent[k] for k in keys)):
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',dt):raise ValueError('invalid filing date')
        if form not in FORMS or not start<=dt<=end:continue
        if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',acc) or not re.fullmatch(r'[A-Za-z0-9_.-]+',doc):
            raise ValueError('invalid filing identifier')
        rows.append({'accession':acc,'filing_date':dt,'form':form,
            'url':f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-","")}/{doc}',
            'issuer_cik':cik,'original_confirmed':False})
    dates=recent['filingDate']
    return rows,bool(dates and min(dates)<start),len(dates)

def fetch_json(session,url,folder,label,ua):
    time.sleep(.55)
    r=session.get(url,headers={'User-Agent':ua,'Accept':'application/json'},timeout=25)
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(label+'.json.raw');path.write_bytes(r.content)
    rec={'url':r.url,'http_status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),
        'fetched_jst':datetime.now(JST).isoformat(),'snapshot_path':str(path),'http_date':r.headers.get('Date')}
    if urlparse(r.url).hostname not in ('www.sec.gov','data.sec.gov'):raise ValueError('non SEC redirect')
    r.raise_for_status()
    return r.json(),rec

def run(root,now=None,ua=None,session=None):
    now=now or datetime.now(JST);root=Path(root);root.mkdir(parents=True,exist_ok=True)
    start=(now-timedelta(days=3)).date().isoformat();end=now.date().isoformat()
    result={'scope':'SEC_8K_6K_FILING_AND_HTML_EXHIBITS','run_id':os.getenv('GITHUB_RUN_ID'),
        'collected_jst':now.isoformat(),'start_date':start,'end_date':end,'newsroom_coverage_credit':False,'entries':[]}
    result['tdnet']=tdnet_run(root/'tdnet'/now.strftime('%Y%m%dT%H%M%S'),now)
    result['hkex']=hkex_run(root/'hkex'/now.strftime('%Y%m%dT%H%M%S'),now)
    ua=ua or os.getenv('SEC_USER_AGENT','')
    if not re.search(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}',ua):
        result.update(status='NOT_CONFIGURED',reason='SEC_USER_AGENT_WITH_CONTACT_REQUIRED')
        result['summary']=summarize(result)
        save_json(root/'regulatory.json',result);return result
    own=session is None;session=session or requests.Session()
    evidence=root/'evidence'/now.strftime('%Y%m%dT%H%M%S')
    try:
        data,receipt=fetch_json(session,'https://www.sec.gov/files/company_tickers.json',evidence,'issuer_map',ua)
        result['issuer_map_receipt']=receipt;tickers=parse_tickers(data)
        for c in load_registry()['companies']:
            t=c['ticker'];mapping=resolve(c,tickers)
            e={'ticker':t,'company_name':c['name'],'newsroom_coverage_credit':False}
            result['entries'].append(e)
            if not mapping:
                e.update(status='NO_CURRENT_SEC_TICKER_MAPPING');continue
            try:
                cik=mapping['cik'];e['sec_ticker']=mapping['sec_ticker'];e['issuer_cik']=cik
                data,receipt=fetch_json(session,f'https://data.sec.gov/submissions/CIK{cik:010d}.json',evidence,t,ua)
                e['receipt']=receipt;e['sec_issuer_name']=data.get('name')
                if not verify_identity(data,mapping):raise ValueError('SEC legal issuer name mismatch')
                e['issuer_identity_verified']=True
                rows,boundary,count=parse_submissions(data,mapping['sec_ticker'],cik,start,end)
                e.update(status='FILING_METADATA_RETRIEVED' if boundary else 'FILING_WINDOW_NOT_PROVEN',
                    filings=rows,record_count=count,filing_date_boundary_reached=boundary)
                e['exhibit_results']=[collect_exhibits(session,row,evidence/t/row['accession'],ua) for row in rows[:10]]
                e['exhibit_filing_cap_exceeded']=len(rows)>10
            except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
                e.update(status='UNCONFIRMED',error=type(exc).__name__+':'+str(exc)[:150])
        result['status']='COLLECTION_FINISHED'
    except (requests.RequestException,ValueError,KeyError,TypeError) as exc:
        result.update(status='SOURCE_UNAVAILABLE',reason=type(exc).__name__+':'+str(exc)[:150])
    finally:
        if own:session.close()
    result['summary']=summarize(result)
    save_json(root/'regulatory.json',result);return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='data/pharma71_regulatory')
    r=run(p.parse_args().root);print(json.dumps({'status':r['status'],'summary':r['summary']}))
