"""Issuer-attributed EQS disclosures, not exhaustive newsroom coverage."""
import re,time,hashlib
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urlparse,urljoin
from bs4 import BeautifulSoup
import requests
from pharma46.fetch import UA,JST
SOURCES={
 'BAYN':('https://www.eqs-news.com/company/bayer-aktiengesellschaft/news/5b70bb23-ea7c-11e8-902f-2c44fd856d8c','DE000BAY0017',('Bayer AG','Bayer Aktiengesellschaft')),
 'LONN':('https://www.eqs-news.com/company/lonza-ag/news/5b71ace0-ea7c-11e8-902f-2c44fd856d8c','CH0013841017',('Lonza Group AG','Lonza Group Ltd')),
}
def norm(s):return ' '.join(str(s).lower().split())
def release_url(url):
    u=urlparse(url)
    return u.scheme=='https' and u.netloc=='www.eqs-news.com' and bool(re.fullmatch(r'/(?:en/|de/)?news/[^/]+/[^/]+/[a-f0-9-]{36}(?:_en|_de)?',u.path,re.I)) and not u.query and not u.fragment
def archive_links(html,url,isin,names):
    soup=BeautifulSoup(html,'html.parser')
    text=soup.get_text(' ',strip=True)
    if isin not in text:raise ValueError('archive ISIN missing')
    if not any(norm(h.get_text(' ',strip=True)) in {norm(n) for n in names} for h in soup.select('h1,h2')):raise ValueError('archive issuer heading mismatch')
    out={}
    for a in soup.select('a[href]'):
        u=urljoin(url,a['href']);title=a.get_text(' ',strip=True)
        if release_url(u) and any(norm(n) in norm(title) for n in names):
            out.setdefault(u,title)
    return out
def verify(html,url,isin,names):
    if not release_url(url):return None
    soup=BeautifulSoup(html,'html.parser');text=soup.get_text(' ',strip=True)
    if not re.search(r'\bISIN\s*:\s*'+re.escape(isin)+r'\b',text):return None
    if not any(re.search(r'\bCompany\s*:\s*'+re.escape(n)+r'\b',text,re.I) for n in names):return None
    if not any(norm(h.get_text(' ',strip=True)) in {norm(n) for n in names} for h in soup.select('h1')):return None
    if not re.search(r'(EQS Distribution Services|EQS News Service|issuer is solely responsible)',text,re.I):return None
    # Require dated original release stamp. Never use archive date or HTTP date.
    m=re.search(r'(\d{1,2}-[A-Za-z]{3}-\d{4})\s*(?:/|CET|CEST)',text)
    if not m:return None
    try:day=datetime.strptime(m.group(1),'%d-%b-%Y').date().isoformat()
    except ValueError:return None
    # Meta title is taken from the original; body is retained as evidence.
    meta=soup.find('meta',attrs={'property':'og:title'})
    title=meta.get('content','') if meta else (soup.title.get_text(' ',strip=True) if soup.title else '')
    if len(title)<15 or len(text)<500:return None
    return {'title':title,'published_date':day,'body_excerpt':text[:600]}
def fetch(session,url,folder,label):
    time.sleep(.6)
    r=session.get(url,headers={'User-Agent':UA,'Cache-Control':'no-cache'},timeout=25)
    folder.mkdir(parents=True,exist_ok=True);p=folder/(label+'.raw');p.write_bytes(r.content)
    receipt={'url':r.url,'http_status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),'snapshot_path':str(p),'fetched_jst':datetime.now(JST).isoformat()}
    if urlparse(r.url).netloc!='www.eqs-news.com':raise ValueError('unexpected EQS redirect')
    r.raise_for_status()
    return r,receipt
def run(root,now,session=None):
    root=Path(root);result={'scope':'EQS_ISSUER_ATTRIBUTED_DISCLOSURES_ONLY','status':'COLLECTION_FINISHED','newsroom_coverage_credit':False,'issuers':[],'entries':[]}
    own=session is None;session=session or requests.Session()
    start=(now-timedelta(days=3)).date().isoformat();end=(now+timedelta(days=1)).date().isoformat()
    try:
        for t,(url,isin,names) in SOURCES.items():
            e={'ticker':t,'status':'UNCONFIRMED','archive_candidates':0,'originals_verified':0,'errors':[]};result['issuers'].append(e)
            try:
                r,rec=fetch(session,url,root/t,'archive');e['receipt']=rec
                if '/company/' not in urlparse(r.url).path or urlparse(r.url).path.split('/')[-1]!=urlparse(url).path.split('/')[-1]:raise ValueError('wrong EQS company archive')
                links=archive_links(r.text,r.url,isin,names);e['archive_candidates']=len(links)
                e['status']='ARCHIVE_CANDIDATES_ONLY' if links else 'EMPTY_ARCHIVE_UNCONFIRMED'
                for i,(link,listing_title) in enumerate(list(links.items())[:8]):
                    try:
                        ar,receipt=fetch(session,link,root/t,'article-'+str(i))
                        d=verify(ar.text,ar.url,isin,names)
                        if not d:raise ValueError('original issuer or publication date not verified')
                        if start<=d['published_date']<=end:
                            result['entries'].append(dict(d,ticker=t,url=ar.url,listing_title=listing_title,source_type='EQS_ISSUER_DISCLOSURE',original_confirmed=True,receipt=receipt))
                            e['originals_verified']+=1
                    except Exception as exc:e['errors'].append({'url':link,'error':type(exc).__name__+':'+str(exc)[:150]})
                e['article_limit_reached']=len(links)>8
            except Exception as exc:e['errors'].append({'url':url,'error':type(exc).__name__+':'+str(exc)[:150]})
    finally:
        if own:session.close()
    result['summary']={'target_issuers':2,'archives_parsed':sum(e['status']=='ARCHIVE_CANDIDATES_ONLY' for e in result['issuers']),'verified_originals':len(result['entries'])}
    return result
def report(reg):
    q=reg.get('eqs',{});s=q.get('summary',{})
    lines=['','## EQS補完監視（発行企業配信・全発表網羅未検証）',f'- 状態: {q.get("status","NOT_RUN")} / 企業別一覧解析 {s.get("archives_parsed",0)}/2 / 原文 {s.get("verified_originals",0)}件']
    for e in q.get('issuers',[]):lines.append(f'- {e["ticker"]}: {e["status"]}, 原文 {e["originals_verified"]}件')
    for x in q.get('entries',[]):lines.append(f'- {x["ticker"]} | {x["published_date"]} | {x["title"]} | {x["url"]}')
    return '\n'.join(lines)+'\n'
