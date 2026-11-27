"""HKEX public title search observations; no claim of exhaustive disclosure coverage."""
import hashlib,json,re,time
from datetime import datetime,timedelta,timezone
from pathlib import Path
from urllib.parse import urlparse,urljoin
import requests
from pharma46.fetch import UA,JST
HOSTS={'www.hkexnews.hk','www1.hkexnews.hk'}
BASE='https://www1.hkexnews.hk'
TARGETS={'06990':('6990 HK','kelun'),'09926':('9926 HK','akeso'),'01801':('1801 HK','innovent'),'02269':('2269 HK','wuxi bio')}
HKT=timezone(timedelta(hours=8))
def code(v):
    s=str(v)
    return s.zfill(5) if re.fullmatch(r'\d{1,5}',s) else None
def resolve_ids(data):
    if not isinstance(data,list):raise ValueError('unexpected stock map schema')
    out={}
    for x in data:
        c=code(x.get('c',''))
        if c not in TARGETS:continue
        i=str(x.get('i',''))
        if not i.isdigit() or c in out:raise ValueError('ambiguous HKEX issuer ID')
        out[c]=i
    if len(set(out.values()))!=len(out):raise ValueError('duplicate internal issuer ID')
    return out
def pdf_url(link):
    u=urlparse(urljoin(BASE+'/',str(link)))
    if u.scheme!='https' or u.netloc not in HOSTS or not u.path.lower().startswith('/listedco/listconews/') or not u.path.lower().endswith('.pdf') or u.query or u.fragment:return None
    if '..' in u.path or '%' in u.path:return None
    return u.geturl()
def parse_rows(data,c,start,end):
    v=data['result']
    rows=json.loads(v) if isinstance(v,str) else v
    if not isinstance(rows,list):raise ValueError('unexpected title search schema')
    out=[]
    for x in rows:
        if code(x.get('STOCK_CODE'))!=c:raise ValueError('stock code mismatch')
        name=str(x.get('STOCK_NAME',''))
        if TARGETS[c][1] not in name.lower():raise ValueError('issuer name mismatch')
        raw=str(x['DATE_TIME']).strip()
        dt=None
        for fmt in ('%d/%m/%Y %H:%M','%Y/%m/%d %H:%M','%Y-%m-%d %H:%M','%d/%m/%Y','%Y/%m/%d','%Y-%m-%d'):
            try:dt=datetime.strptime(raw,fmt);break
            except ValueError:pass
        if dt is None or not start<=dt.date().isoformat()<=end:raise ValueError('invalid or out-of-window disclosure date')
        title=str(x['TITLE']).strip()
        if not title:raise ValueError('empty title')
        out.append({'ticker':TARGETS[c][0],'stock_code':c,'issuer':name,'title':title,
                    'published_hkt_raw':raw,'published_date':dt.date().isoformat(),
                    'url':pdf_url(x.get('FILE_LINK','')),'original_confirmed':False})
    return out
def get(session,url,folder,label,params=None):
    time.sleep(.6)
    r=session.get(url,params=params,headers={'User-Agent':UA,'Accept':'application/json','Referer':BASE+'/search/titlesearch.xhtml'},timeout=25)
    folder.mkdir(parents=True,exist_ok=True);p=folder/(label+'.raw');p.write_bytes(r.content)
    rec={'url':r.url,'http_status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),'snapshot_path':str(p),'fetched_jst':datetime.now(JST).isoformat()}
    if urlparse(r.url).hostname not in HOSTS:raise ValueError('unexpected HKEX redirect')
    r.raise_for_status()
    return r.json(),rec
def run(root,now,session=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    end=now.astimezone(HKT).date();start=end-timedelta(days=3)
    out={'scope':'HKEX_ENGLISH_ANNOUNCEMENT_TITLE_CANDIDATES_ONLY','status':'COLLECTION_FINISHED','newsroom_coverage_credit':False,'entries':[],'issuers':[]}
    own=session is None;session=session or requests.Session()
    try:
        data,rec=get(session,BASE+'/ncms/script/eds/activestock_sehk_e.json',root,'stock-map')
        out['stock_map_receipt']=rec;ids=resolve_ids(data)
        for c,(ticker,_) in TARGETS.items():
            e={'ticker':ticker,'stock_code':c,'status':'UNCONFIRMED','candidate_count':0};out['issuers'].append(e)
            if c not in ids:e['reason']='INTERNAL_ID_UNRESOLVED';continue
            try:
                params={'sortDir':'1','sortByOptions':'DateTime','category':'0','market':'SEHK','stockId':ids[c],
                    'documentType':'-1','fromDate':start.strftime('%Y%m%d'),'toDate':end.strftime('%Y%m%d'),
                    'title':'','searchType':'1','t1code':'40000','t2Gcode':'-2','t2code':'40100','rowRange':'100','lang':'EN'}
                data,rec=get(session,BASE+'/search/titleSearchServlet.do',root,c,params)
                e['receipt']=rec;rows=parse_rows(data,c,start.isoformat(),end.isoformat())
                e.update(status='CANDIDATES_RETRIEVED_SCOPE_UNVERIFIED' if rows else 'EMPTY_RESPONSE_SCOPE_UNVERIFIED',candidate_count=len(rows))
                if len(rows)>=100:e['status']='POSSIBLY_TRUNCATED'
                out['entries'].extend(rows)
            except Exception as exc:e['reason']=type(exc).__name__+':'+str(exc)[:180]
    except Exception as exc:out.update(status='SOURCE_UNAVAILABLE',reason=type(exc).__name__+':'+str(exc)[:180])
    finally:
        if own:session.close()
    out['summary']={'target_issuers':4,'issuer_queries':len(out['issuers']),'issuer_responses_parsed':sum(x['status']!='UNCONFIRMED' for x in out['issuers']),'disclosure_candidates':len(out['entries']),'verified_originals':0}
    return out
def report_lines(reg):
    h=reg.get('hkex',{});s=h.get('summary',{})
    lines=['','## HKEX補完監視（英語開示候補・範囲未検証）',f'- 状態: {h.get("status","NOT_RUN")} / 解析済み企業 {s.get("issuer_responses_parsed",0)}/4 / 開示候補 {s.get("disclosure_candidates",0)}件']
    for e in h.get('issuers',[]):lines.append(f'- {e["ticker"]}: {e["status"]} / {e["candidate_count"]}件')
    for x in h.get('entries',[]):lines.append(f'- {x["ticker"]} | {x["published_hkt_raw"]} HKT | {x["title"]} | {x["url"] or "PDF URL未確認"}')
    return '\n'.join(lines)+'\n'
