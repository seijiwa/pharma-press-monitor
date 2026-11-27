"""Independent official-source observations, not automatic period-coverage credit."""
from datetime import datetime,timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urlparse,urljoin
import hashlib,logging,json
import xml.etree.ElementTree as ET
import requests
from bs4 import BeautifulSoup
from pharma46.fetch import UA,JST,LiveFetcher,store_snapshot,FetchError
from pharma46.extract import host_matches,parse_date,article_details
from pharma46.engine import fetch_receipt,suspect_cache,title_matches

LOG=logging.getLogger(__name__)

def parse_rss(raw):
    root=ET.fromstring(raw)
    rows=[]
    for node in root.findall('./channel/item'):
        title=(node.findtext('title') or '').strip()
        link=(node.findtext('link') or '').strip()
        stamp=(node.findtext('pubDate') or '').strip()
        try:published=parsedate_to_datetime(stamp).date().isoformat()
        except (ValueError,TypeError,OverflowError):published=None
        if title and link.startswith('https://'):
            rows.append({'url':link,'title':title,'listing_date':published})
    return rows

def parse_lundbeck(raw):
    data=json.loads(raw)
    rows=[]
    for item in data['items']:
        if item.get('language')!='en':continue
        url=item.get('url','')
        if url.startswith('https://') and item.get('title'):
            rows.append({'url':url,'title':item['title'],'listing_date':parse_date(item.get('publishDate'))})
    return rows

def save_response(r,folder,label):
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(label+'.raw')
    path.write_bytes(r.content)
    return {'url':r.url,'http_status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),
            'snapshot_path':str(path),'fetched_jst':datetime.now(JST).isoformat(),
            'response_date':r.headers.get('Date'),'age':r.headers.get('Age')}

def collect_fallback(entry,company,now,evidence_dir,session=None,fetcher=None):
    if entry['status']!='未確認':return
    ticker=entry['ticker']
    feed=(company.get('legacy_feed_url') or '').strip()
    folder=Path(evidence_dir)/ticker.replace(' ','_')
    sess=session or requests.Session()
    own=session is None
    try:
        # Registered company feed only; never use third-party aggregate feeds.
        routes=[]
        if feed.startswith('https://') and any(host_matches(feed,x) for x in company['official_indexes']):
            routes.append(('official_rss',feed,parse_rss))
        if ticker=='HLUN':
            # This exact JSON endpoint was exposed in the official archive HTML.
            routes.append(('lundbeck_official_archive_api',
                'https://www.lundbeck.com/content/lundbeck-com/global/global-site/en/press/news-archive/jcr:content/root/responsivegrid/newsarchive.model.json',
                parse_lundbeck))
        for label,url,parser in routes:
            attempt={'method':label,'coverage_credit':False}
            entry['alternative_attempts'].append(attempt)
            try:
                resp=sess.get(url,headers={'User-Agent':UA,'Cache-Control':'no-cache'},timeout=25)
                attempt.update(save_response(resp,folder,label))
                resp.raise_for_status()
                if not host_matches(url,resp.url):raise ValueError('redirect outside configured source')
                rows=parser(resp.content)
                attempt['record_count']=len(rows)
                attempt['dated_count']=sum(bool(x['listing_date']) for x in rows)
                attempt['candidate_releases']=rows[:100]
                start=entry['comparison_period']['start_jst'][:10]
                end=(now+timedelta(days=1)).date().isoformat()
                recent=[x for x in rows if x['listing_date'] and start<=x['listing_date']<=end]
                attempt['recent_count']=len(recent)
                seen={x['url'] for x in entry['primary_releases'] if x.get('original_confirmed')}
                # Feed item alone is never enough. Verify original body, title,
                # date, company host and freshness. External distribution URLs
                # remain candidates pending explicit publisher validation.
                for item in recent[:15]:
                    if item['url'] in seen or not any(host_matches(x,item['url']) for x in company['official_indexes']):
                        continue
                    try:
                        f=(fetcher or LiveFetcher()).get(item['url'])
                        receipt=fetch_receipt(f,store_snapshot(evidence_dir,ticker,f))
                        d=article_details(f.final_url,f.html)
                        if (d['body_confirmed'] and host_matches(item['url'],f.final_url) and
                            title_matches(item['title'],d['title']) and
                            d['published_date']==item['listing_date'] and not suspect_cache(f,now)):
                            entry['primary_releases'].append({'ticker':ticker,'name':entry['company_name'],
                                'url':item['url'],'listing_title':item['title'],'listing_date':item['listing_date'],
                                'original_title':d['title'],'published_date':d['published_date'],
                                'body_excerpt':d['body'][:600],'original_confirmed':True,'receipt':receipt,
                                'new_status':'FALLBACK_ORIGINAL_VERIFIED_NEWNESS_UNDETERMINED'})
                            seen.add(item['url'])
                    except (FetchError,ValueError,TypeError) as exc:
                        attempt.setdefault('article_errors',[]).append({'url':item['url'],'error':str(exc)[:160]})
                attempt['reason']='SUPPLEMENTAL_ONLY_NO_PERIOD_COVERAGE_CREDIT'
            except Exception as exc:
                attempt['error']=type(exc).__name__+':'+str(exc)[:200]
    finally:
        if own:sess.close()

def update_original_state(entries,state,prior_state):
    """Record fallback originals too, while never advancing an unverified period."""
    for e in entries:
        ticker=e['ticker']
        if e.get('source_classification')=='PARENT_ONLY_UNVERIFIED':continue
        st=state.setdefault('companies',{}).setdefault(ticker,{})
        prior=prior_state.get('companies',{}).get(ticker,{})
        seen=set(st.get('seen_verified_urls',[]))
        known=set(prior.get('seen_verified_urls',[]))
        for p in e['primary_releases']:
            if not p.get('original_confirmed'):continue
            if p['url'] in known:p['new_status']='KNOWN_PREVIOUSLY_CONFIRMED'
            seen.add(p['url'])
            floor=st.get('latest_verified_original') or {}
            if (p.get('published_date') or '')>(floor.get('date') or ''):
                st['latest_verified_original']={'date':p['published_date'],'url':p['url'],'purpose':'verified original freshness floor'}
        st['seen_verified_urls']=sorted(seen)[-500:]
        if e['status']=='未確認':
            if 'last_verified_success_jst' in prior:
                st['last_verified_success_jst']=prior['last_verified_success_jst']
            else:st.pop('last_verified_success_jst',None)
