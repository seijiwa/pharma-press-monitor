"""TDnet public listing observations; do not infer whole-company news coverage."""
import hashlib,re,time
from datetime import datetime,timedelta
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
from pharma46.fetch import JST,UA

BASE='https://www.release.tdnet.info/inbs/'
TARGETS={'4568':'4568 JP','4151':'4151 JP','4536':'4536 JP','4506':'4506 JP'}
def allowed_pdf(url):
    u=urlparse(url)
    return u.scheme=='https' and u.netloc=='www.release.tdnet.info' and bool(re.fullmatch(r'/inbs/\d+\.pdf',u.path)) and not u.query and not u.fragment
def parse_listing(html,url,day):
    soup=BeautifulSoup(html,'html.parser')
    table=soup.select_one('table#main-list-table')
    if table is None:raise ValueError('TDnet table missing')
    rows=[]
    for tr in table.select('tr'):
        code=tr.select_one('.kjCode');name=tr.select_one('.kjName');stamp=tr.select_one('.kjTime');title=tr.select_one('.kjTitle')
        if not any((code,name,stamp,title)):continue
        if not all((code,name,stamp,title)):raise ValueError('incomplete TDnet row')
        security=code.get_text(strip=True)
        if not re.fullmatch(r'[0-9A-Z]{4,5}',security):raise ValueError('invalid security code')
        t=TARGETS.get(security[:4])
        if not t:continue
        clock=stamp.get_text(strip=True)
        if not re.fullmatch(r'\d{2}:\d{2}',clock):raise ValueError('invalid publication time')
        a=title.find('a',href=True)
        link=urljoin(url,a['href']) if a else None
        rows.append({'ticker':t,'code':security,'issuer':name.get_text(' ',strip=True),'title':title.get_text(' ',strip=True),
                     'published_jst':day+'T'+clock+':00+09:00','url':link if link and allowed_pdf(link) else None,
                     'original_confirmed':False,'status':'LISTED_PDF_NOT_VERIFIED' if link and allowed_pdf(link) else 'PDF_LINK_UNAVAILABLE'})
    # Parse visible numbered links only; JS-only pagination is not verified.
    pages=set()
    for a in soup.find_all('a',href=True):
        link=urljoin(url,a['href']);u=urlparse(link)
        if u.scheme=='https' and u.netloc=='www.release.tdnet.info' and re.fullmatch(r'/inbs/I_list_\d{3}_'+day.replace('-','')+r'\.html',u.path):pages.add(link)
    return rows,sorted(pages)
def run(root,now,session=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    result={'scope':'TDNET_PUBLIC_LISTING_METADATA_ONLY','status':'COLLECTION_FINISHED','newsroom_coverage_credit':False,'days':[],'entries':[]}
    own=session is None;session=session or requests.Session()
    try:
        for offset in range(4):
            day=(now-timedelta(days=offset)).date().isoformat()
            first=BASE+'I_list_001_'+day.replace('-','')+'.html'
            queue=[first];seen=set();record={'date':day,'status':'LISTING_OBSERVATIONS_ONLY','receipts':[],'errors':[]}
            result['days'].append(record)
            while queue and len(seen)<10:
                url=queue.pop(0)
                if url in seen:continue
                seen.add(url)
                try:
                    time.sleep(.6)
                    r=session.get(url,headers={'User-Agent':UA},timeout=25)
                    path=root/(day+'-'+str(len(seen))+'.raw')
                    path.write_bytes(r.content)
                    record['receipts'].append({'url':r.url,'http_status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),'snapshot_path':str(path),'fetched_jst':datetime.now(JST).isoformat()})
                    r.raise_for_status()
                    if r.url!=url:raise ValueError('unexpected redirect')
                    rows,pages=parse_listing(r.text,r.url,day)
                    result['entries'].extend(rows)
                    queue.extend(p for p in pages if p not in seen and p not in queue)
                except Exception as exc:record['errors'].append({'url':url,'error':type(exc).__name__+':'+str(exc)[:150]})
            if queue:record['errors'].append({'error':'PAGE_LIMIT'})
            if record['errors']:record['status']='PARTIAL_OR_UNCONFIRMED'
    finally:
        if own:session.close()
    unique={(x['ticker'],x['published_jst'],x['title'],x['url']):x for x in result['entries']}
    result['entries']=list(unique.values())
    result['summary']={'target_issuers':len(TARGETS),'days_attempted':len(result['days']),
                       'pages_retrieved':sum(sum(x['http_status']==200 for x in d['receipts']) for d in result['days']),
                       'days_with_errors':sum(bool(d['errors']) for d in result['days']),'disclosure_candidates':len(result['entries']),
                       'verified_originals':0}
    return result
def report_lines(reg):
    t=reg.get('tdnet',{});s=t.get('summary',{})
    lines=['','## TDnet補完監視（一覧候補のみ・PDF原文未確認）',f'- 状態: {t.get("status","NOT_RUN")} / 取得ページ {s.get("pages_retrieved",0)} / 開示候補 {s.get("disclosure_candidates",0)}件']
    for x in t.get('entries',[]):
        lines.append(f'- {x["ticker"]} | {x["published_jst"]} | {x["title"]} | {x["url"] or "PDF URL未確認"}')
    return '\n'.join(lines)+'\n'
