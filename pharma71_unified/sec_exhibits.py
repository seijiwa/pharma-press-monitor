"""SEC accession-scoped exhibits. Filing evidence is not newsroom coverage."""
import hashlib,re,time
from datetime import datetime
from urllib.parse import urlparse,urljoin
from pathlib import Path
from bs4 import BeautifulSoup
from pharma46.fetch import JST

def directory(filing):
    cik=int(filing['issuer_cik']);acc=filing['accession']
    if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',acc):raise ValueError('invalid accession')
    return f'https://www.sec.gov/Archives/edgar/data/{cik}/{acc.replace("-","")}/'

def allowed(url,base):
    u=urlparse(url);b=urlparse(base)
    return (u.scheme=='https' and u.netloc=='www.sec.gov' and u.path.startswith(b.path)
            and bool(re.fullmatch(r'[A-Za-z0-9_.-]+',u.path[len(b.path):])) and not u.query and not u.fragment)

def exhibit_links(html,filing):
    base=directory(filing);soup=BeautifulSoup(html,'html.parser')
    rows={}
    # SEC document index table: Sequence, Description, Document, Type, Size.
    for tr in soup.select('table.tableFile tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)<5:continue
        kind=cells[3].get_text(' ',strip=True).upper()
        if not re.fullmatch(r'EX-99(?:\.\d+)?',kind):continue
        desc=cells[1].get_text(' ',strip=True)
        a=cells[2].find('a',href=True)
        if not a:continue
        url=urljoin(base,a['href'])
        if not allowed(url,base):continue
        if not url.lower().endswith(('.htm','.html','.txt')):continue
        rows[url]={'url':url,'exhibit_type':kind,'description':desc,
                   'press_release_label':bool(re.search(r'press release|news release|earnings release',desc,re.I))}
    return list(rows.values())

def extract_body(html):
    soup=BeautifulSoup(html,'html.parser')
    for tag in soup.select('script,style,nav,footer,ix\\:header,[style*="display:none"],[style*="display: none"]'):
        tag.decompose()
    body=' '.join((soup.body or soup).get_text(' ',strip=True).split())
    return body

def fetch_doc(session,url,base,folder,label,ua):
    if not allowed(url,base):raise ValueError('outside filing accession')
    time.sleep(.55)
    r=session.get(url,headers={'User-Agent':ua,'Accept':'text/html,text/plain'},timeout=25)
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(label+'.raw');path.write_bytes(r.content)
    rec={'url':r.url,'http_status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),
         'fetched_jst':datetime.now(JST).isoformat(),'snapshot_path':str(path)}
    if not allowed(r.url,base):raise ValueError('redirect outside accession')
    r.raise_for_status()
    return r.text,rec

def collect_exhibits(session,filing,folder,ua,limit=8):
    base=directory(filing);acc=filing['accession']
    result={'accession':acc,'filing_date':filing['filing_date'],'status':'UNCONFIRMED','exhibits':[]}
    try:
        html,rec=fetch_doc(session,base+acc+'-index.htm',base,folder,'index',ua)
        result['index_receipt']=rec
        soup=BeautifulSoup(html,'html.parser')
        # Reject a readable SEC error page / incomplete document listing.
        if not soup.select_one('table.tableFile'):raise ValueError('missing filing document index')
        rows=exhibit_links(html,filing)
        result['eligible_exhibit_count']=len(rows)
        for i,item in enumerate(rows[:limit]):
            row=dict(item,original_confirmed=False)
            result['exhibits'].append(row)
            try:
                html,rec=fetch_doc(session,item['url'],base,folder,f'exhibit-{i}',ua)
                row['receipt']=rec
                body=extract_body(html)
                # SEC-hosted exhibit provenance is established by CIK/accession
                # and document index. It does not establish a news release date.
                if len(body)<200 or re.search(r'undeclared automated tool|request rate threshold exceeded|access denied',body[:500],re.I):
                    raise ValueError('short or blocked exhibit body')
                row.update(original_confirmed=True,source_type='SEC_FILED_EXHIBIT',
                           body_excerpt=body[:600],body_sha256=hashlib.sha256(body.encode()).hexdigest())
            except Exception as exc:row['error']=type(exc).__name__+':'+str(exc)[:180]
        result['status']='EXHIBIT_LIMIT_EXCEEDED' if len(rows)>limit else ('EXHIBITS_VERIFIED' if rows and all(x['original_confirmed'] for x in result['exhibits']) else 'EXHIBITS_PARTIAL' if rows else 'NO_ELIGIBLE_HTML_EXHIBIT')
    except Exception as exc:result['error']=type(exc).__name__+':'+str(exc)[:180]
    return result

def summarize(reg):
    entries=reg.get('entries',[])
    docs=[d for e in entries for d in e.get('exhibit_results',[])]
    originals=[x for d in docs for x in d.get('exhibits',[]) if x.get('original_confirmed')]
    return {'registry_rows':len(entries),
            'mapped':sum(e.get('status')!='NO_CURRENT_SEC_TICKER_MAPPING' for e in entries),
            'filing_windows_verified':sum(e.get('status')=='FILING_METADATA_RETRIEVED' for e in entries),
            'filing_windows_unconfirmed':sum(e.get('status') in ('UNCONFIRMED','FILING_WINDOW_NOT_PROVEN') for e in entries),
            'filings':sum(len(e.get('filings',[])) for e in entries),
            'filing_indexes_attempted':len(docs),
            'verified_exhibits':len(originals),
            'verified_press_release_labeled_exhibits':sum(bool(x.get('press_release_label')) for x in originals)}
def report_lines(reg):
    s=summarize(reg)
    lines=['','## SEC規制開示（独立補完経路・公式ニュース一覧の網羅判定とは別）',
           f'- 状態: {reg.get("status","NOT_RUN")} / SEC対象マッピング {s["mapped"]} / 開示期間確認 {s["filing_windows_verified"]} / 未確認 {s["filing_windows_unconfirmed"]} / 開示 {s["filings"]}件 / 原文添付資料 {s["verified_exhibits"]}件',
           '|Ticker|SEC判定|開示件数|確認済み添付資料|','|---|---|---:|---:|']
    for e in reg.get('entries',[]):
        n=sum(bool(x.get('original_confirmed')) for d in e.get('exhibit_results',[]) for x in d.get('exhibits',[]))
        lines.append(f'|{e["ticker"]}|{e["status"]}|{len(e.get("filings",[]))}|{n}|')
    lines+=['','### SECで確認した添付資料（公開日は提出日と区別）']
    seen=set()
    for e in reg.get('entries',[]):
        for d in e.get('exhibit_results',[]):
            for x in d.get('exhibits',[]):
                if not x.get('original_confirmed') or x['url'] in seen:continue
                seen.add(x['url'])
                desc=x['description'].replace('|','/') or x['exhibit_type']
                lines.append(f'- {e["ticker"]} | 提出日 {d["filing_date"]} | {desc} | {x["url"]}')
    if not seen:lines.append('- 確認済み添付資料なし（発表不存在の証明ではない）')
    return '\n'.join(lines)+'\n'
