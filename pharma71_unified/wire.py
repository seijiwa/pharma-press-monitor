"""Issuer-scoped distribution archives. Supplementary coverage, never newsroom QA."""
import re,json,unicodedata
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse,urljoin
from bs4 import BeautifulSoup
import requests
from pharma46.fetch import UA,JST,LiveFetcher,store_snapshot,FetchError
from pharma46.extract import article_details,parse_date
from pharma46.engine import fetch_receipt,suspect_cache,title_matches
from .official_fallback import save_response

# Actual organization archive URLs found on GlobeNewswire (not keyword search).
SOURCES={
 'BIIB':('Biogen Inc.','https://www.globenewswire.com/en/search/organization/Biogen%2520Inc%C2%A7?page=1'),
 'DNLI':('Denali Therapeutics Inc.','https://www.globenewswire.com/search/organization/Denali%2520Therapeutics%2520Inc%C2%A7'),
 'ERAS':('Erasca, Inc.','https://www.globenewswire.com/search/organization/Erasca%CE%B4%2520Inc%C2%A7'),
 'KURA':('Kura Oncology, Inc.','https://www.globenewswire.com/search/organization/Kura%2520Oncology%CE%B4%2520Inc%C2%A7'),
 'CGEM':('Cullinan Therapeutics, Inc.','https://www.globenewswire.com/search/organization/cullinan%2520therapeutics%CE%B4%2520inc%C2%A7'),
 'GPCR':('Structure Therapeutics Inc.','https://www.globenewswire.com/search/organization/structure%2520therapeutics%2520inc%C2%A7'),
}
HOSTS={'www.globenewswire.com','rss.globenewswire.com','globenewswire.com'}
def norm(s):
    return ' '.join(re.findall(r'[a-z0-9]+',unicodedata.normalize('NFKC',str(s)).lower()))
def exact_source(actual,expected):return norm(actual)==norm(expected)
def valid_release(url):
    u=urlparse(url)
    return u.scheme=='https' and u.hostname in HOSTS and bool(re.fullmatch(r'/(?:en/)?news-release/\d{4}/\d{2}/\d{2}/\d+/\d+/en/[^/]+',u.path,re.I))
def sources_in(node):
    # Use only explicitly labeled source fields, not names mentioned in body text.
    out=[]
    for tag in node.select('[itemprop="sourceOrganization"], [itemprop="publisher"], .source, .source-name, .company-name, .article-source'):
        val=tag.get('content') or tag.get_text(' ',strip=True)
        val=re.sub(r'^\s*Source\s*:\s*','',val,flags=re.I)
        if val:out.append(val)
    for tag in node.find_all(['p','span','div','a','time']):
        v=tag.get_text(' ',strip=True)
        if len(v)>180:continue
        m=re.search(r'(?:^|\|\s*)Source\s*:\s*(.+)$',v,re.I)
        if m:out.append(m.group(1).strip())
    return out
def archive_rows(url,html,issuer):
    soup=BeautifulSoup(html,'html.parser')
    rows={}
    for a in soup.find_all('a',href=True):
        link=urljoin(url,a['href'])
        if not valid_release(link):continue
        title=a.get_text(' ',strip=True)
        if len(title)<15:continue
        # Closest small ancestor containing this release and its source/date.
        for node in list(a.parents)[:6]:
            if node.name in ('body','html'):break
            links={urljoin(url,x['href']) for x in node.find_all('a',href=True) if valid_release(urljoin(url,x['href']))}
            if len(links)>1:break
            if not any(exact_source(x,issuer) for x in sources_in(node)):continue
            path_date='/'.join(urlparse(link).path.split('news-release/')[1].split('/')[:3])
            dt=parse_date(path_date)
            # Explicit date near source must agree with the release URL.
            dates=[]
            for tag in node.find_all(['time','p','span','div']):
                v=tag.get('datetime') or tag.get_text(' ',strip=True)
                if len(v)>180:continue
                if tag.name=='time' or re.search(r'\bSource\s*:|\b(?:ET|EST|EDT)\b',v,re.I):
                    dates.append(parse_date(v))
            if dt and dt in dates:
                rows.setdefault(link,{'url':link,'title':title,'listing_date':dt,'issuer':issuer})
                break
    return list(rows.values())
def verify_article(url,html,item,issuer):
    if not valid_release(url):return None
    soup=BeautifulSoup(html,'html.parser')
    # Company attribution must occur in publication metadata/header, not a
    # third-party press release that mentions the issuer later in its body.
    scopes=soup.select('header, .article-header, .article-info, .main-article-header, [class*="article-header"], [class*="articleHeader"]')
    header_sources=[]
    for node in scopes:header_sources.extend(sources_in(node))
    for tag in soup.select('meta[name="author"], meta[property="article:author"], meta[name="source"]'):
        if tag.get('content'):header_sources.append(tag['content'])
    for node in soup.select('[itemprop="sourceOrganization"], .article-source, .source-name'):
        header_sources.extend(sources_in(node.parent))
    if not any(exact_source(x,issuer) for x in header_sources):return None
    d=article_details(url,html)
    if not(d['body_confirmed'] and d['published_date']==item['listing_date'] and title_matches(item['title'],d['title'])):return None
    return d
def collect_wire(entry,now,evidence_dir,session=None,fetcher=None):
    if entry['status']!='未確認' or entry['ticker'] not in SOURCES:return
    issuer,url=SOURCES[entry['ticker']]
    attempt={'method':'globenewswire_issuer_archive','coverage_credit':False,'issuer':issuer,'url':url}
    entry['alternative_attempts'].append(attempt)
    own=session is None;session=session or requests.Session()
    folder=Path(evidence_dir)/entry['ticker'].replace(' ','_')
    try:
        r=session.get(url,headers={'User-Agent':UA,'Cache-Control':'no-cache'},timeout=25)
        attempt.update(save_response(r,folder,'globenewswire_archive'))
        r.raise_for_status()
        if urlparse(r.url).hostname not in HOSTS or '/search/organization/' not in urlparse(r.url).path:
            raise ValueError('unexpected archive redirect')
        rows=archive_rows(r.url,r.text,issuer)
        attempt['record_count']=len(rows)
        attempt['candidate_releases']=rows[:100]
        start=entry['comparison_period']['start_jst'][:10];end=(now+timedelta(days=1)).date().isoformat()
        recent=[x for x in rows if start<=x['listing_date']<=end]
        attempt['recent_count']=len(recent)
        attempt['reason']='ISSUER_DISTRIBUTION_SCOPE_ONLY' if rows else 'NO_ATTRIBUTED_DATED_ROWS'
        seen={x['url'] for x in entry['primary_releases'] if x.get('original_confirmed')}
        for item in recent[:15]:
            if item['url'] in seen:continue
            try:
                f=(fetcher or LiveFetcher()).get(item['url'])
                rec=fetch_receipt(f,store_snapshot(evidence_dir,entry['ticker'],f))
                d=verify_article(f.final_url,f.html,item,issuer)
                if d and not suspect_cache(f,now):
                    entry['primary_releases'].append({'ticker':entry['ticker'],'name':entry['company_name'],
                        'url':item['url'],'listing_title':item['title'],'listing_date':item['listing_date'],
                        'original_title':d['title'],'published_date':d['published_date'],
                        'body_excerpt':d['body'][:600],'original_confirmed':True,'receipt':rec,
                        'new_status':'DISTRIBUTION_ORIGINAL_VERIFIED_NEWNESS_UNDETERMINED',
                        'source_type':'ISSUER_AUTHORED_WIRE'})
                    seen.add(item['url'])
                else:attempt.setdefault('article_errors',[]).append({'url':item['url'],'error':'ATTRIBUTION_DATE_BODY_OR_FRESHNESS_FAILED'})
            except (FetchError,ValueError,TypeError) as exc:
                attempt.setdefault('article_errors',[]).append({'url':item['url'],'error':str(exc)[:180]})
    except Exception as exc:
        attempt['error']=type(exc).__name__+':'+str(exc)[:200]
    finally:
        if own:session.close()
