"""Live direct-fetch adapter. Never treats a search snippet or tool-cache as a visit."""
import gzip,hashlib,logging,re,requests,time
from datetime import datetime,timezone,timedelta
from pathlib import Path
from urllib.parse import urlparse
from email.utils import parsedate_to_datetime
from dataclasses import dataclass
JST=timezone(timedelta(hours=9))
LOG=logging.getLogger(__name__)
UA='Pharma46Monitor/2.0 (+https://github.com/seijiwa/pharma-press-monitor; official-source monitor)'

@dataclass
class FetchResult:
    requested_url:str
    final_url:str
    html:str
    http_status:int
    method:str
    fetched_jst:str
    snapshot_sha256:str
    response_date:str|None=None
    age_seconds:int|None=None
    last_modified:str|None=None
    error:str|None=None

class FetchError(RuntimeError):
    def __init__(self,reason,attempts):
        super().__init__(reason);self.attempts=attempts

def _age(headers):
    try:return int(headers.get('Age','0'))
    except (ValueError,TypeError):return None

def _to_iso(v):
    if not v:return None
    try:return parsedate_to_datetime(v).isoformat()
    except (TypeError,ValueError):return str(v)

def _safename(url):
    h=hashlib.sha256(url.encode()).hexdigest()[:18]
    name=re.sub(r'[^a-zA-Z0-9_-]+','_',urlparse(url).path)[-50:]
    return f'{name}_{h}.html.gz'

def store_snapshot(evidence_dir,ticker,result):
    if not result.html:return None
    path=Path(evidence_dir)/ticker.replace(' ','_')/(result.method+'-'+result.snapshot_sha256[:16]+'-'+_safename(result.final_url))
    path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,'wb') as f:f.write(result.html.encode('utf-8',errors='replace'))
    return str(path)

class LiveFetcher:
    def __init__(self,timeout=22,allow_browser=True):
        self.timeout=timeout;self.allow_browser=allow_browser

    def get(self,url):
        start=datetime.now(JST);errors=[]
        try:
            r=requests.get(url,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store','Pragma':'no-cache'},timeout=self.timeout,allow_redirects=True)
            if r.status_code in (429,502,503):
                time.sleep(1.0)
                r=requests.get(url,headers={'User-Agent':UA,'Cache-Control':'no-cache, no-store'},timeout=self.timeout,allow_redirects=True)
            if r.status_code>=400:
                errors.append('HTTP_'+str(r.status_code))
            else:
                if r.encoding is None:r.encoding=r.apparent_encoding
                raw=r.text
                if len(raw)<1200 or '<html' not in raw.lower():
                    errors.append('NON_HTML_OR_SHORT')
                else:
                    return self._result(url,r.url,raw,r.status_code,'requests',r.headers)
        except requests.RequestException as e:
            errors.append('REQUEST_'+type(e).__name__)
        if self.allow_browser:
            try:return self.browser_get(url)
            except Exception as e:errors.append('BROWSER_'+type(e).__name__+':'+str(e)[:120])
        raise FetchError(' | '.join(errors) if errors else 'NO_RESPONSE',errors)

    def browser_get(self,url):
        """Fresh isolated Chromium context, including server response age headers."""
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True)
            context=browser.new_context(service_workers='block',user_agent=UA,
                extra_http_headers={'Cache-Control':'no-cache','Pragma':'no-cache'})
            page=context.new_page()
            resp=page.goto(url,timeout=self.timeout*1000,wait_until='domcontentloaded')
            if resp and resp.status>=400:
                context.close();browser.close()
                raise RuntimeError('HTTP_'+str(resp.status))
            try:page.wait_for_load_state('networkidle',timeout=3500)
            except Exception:pass
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            page.wait_for_timeout(350)
            html=page.content();final=page.url
            headers=resp.headers if resp else {}
            code=resp.status if resp else 200
            context.close();browser.close()
        if len(html)<1200:raise RuntimeError('BROWSER_SHORT_RESPONSE')
        return self._result(url,final,html,code,'playwright',headers)

    def _result(self,url,final,html,http_status,method,headers):
        return FetchResult(requested_url=url,final_url=final,html=html,http_status=http_status,
                           method=method,fetched_jst=datetime.now(JST).isoformat(),
                           snapshot_sha256=hashlib.sha256(html.encode('utf-8',errors='replace')).hexdigest(),
                           response_date=_to_iso(headers.get('Date')),
                           age_seconds=_age(headers) if headers else None,
                           last_modified=_to_iso(headers.get('Last-Modified')))
