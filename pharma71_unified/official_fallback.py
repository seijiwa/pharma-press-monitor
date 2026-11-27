"""Independent official-source observations, not automatic period-coverage credit."""
from datetime import datetime,timedelta,timezone
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

def lundbeck_archive_coverage(raw,start,end,now,response_date,age=None,floor=None):
    """Validate the unfiltered English archive and its dated boundary.
    Historical records outside the requested years may lack an article link.
    Any malformed record in the requested years fails closed.
    """
    try:
        stamp=parsedate_to_datetime(response_date)
        if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
        delta=now.astimezone(timezone.utc)-stamp
        if delta>timedelta(hours=48) or delta< -timedelta(minutes=10) or (age is not None and int(age)>172800):
            return [],'LUNDBECK_STALE_RESPONSE'
        data=json.loads(raw)
        filters={x['property']:x['options'] for x in data['filters']}
        if set(filters)!= {'type','year','language'}:return [],'LUNDBECK_FILTER_SCHEMA'
        if any(x.get('selected') for k in ('type','year') for x in filters[k]):
            return [],'LUNDBECK_FILTERED_ARCHIVE'
        if [x['value'] for x in filters['language'] if x.get('selected')]!=['en']:
            return [],'LUNDBECK_WRONG_LANGUAGE_SCOPE'
        years={int(x['value']) for x in filters['year']}
        first_year=int(start[:4])-1
        if not set(range(first_year,int(now.date().isoformat()[:4])+1))<=years:
            return [],'LUNDBECK_YEAR_WINDOW_MISSING'
        rows=[];stamps=[];ids=set();urls=set()
        for item in data['items']:
            if item.get('language') not in ('en','da'):return [],'LUNDBECK_UNKNOWN_LANGUAGE'
            if item['language']!='en':continue
            dt=datetime.fromisoformat(item['publishDate'].replace('Z','+00:00'))
            if dt.tzinfo is None:return [],'LUNDBECK_UNZONED_DATE'
            stamps.append(dt)
            if int(item['year'])<first_year:continue
            published=dt.date().isoformat()
            url=item.get('url') or '';u=urlparse(url)
            if (u.scheme!='https' or u.hostname!='news.cision.com' or not u.path.startswith('/h--lundbeck-a-s/r/')
                or not item.get('title') or not item.get('id') or item['id'] in ids or url in urls
                or published>end):
                return [],'LUNDBECK_INVALID_CURRENT_RECORD'
            ids.add(item['id']);urls.add(url)
            rows.append({'url':url,'title':item['title'],'listing_date':published})
        if stamps!=sorted(stamps,reverse=True):return [],'LUNDBECK_UNSORTED'
        if not rows or rows[-1]['listing_date']>=start:return [],'LUNDBECK_NO_BOUNDARY'
        if floor and rows[0]['listing_date']<floor:return [],'LUNDBECK_KNOWN_RELEASE_MISSING'
        return rows,None
    except (KeyError,ValueError,TypeError,OverflowError,AttributeError):
        return [],'LUNDBECK_INVALID_ARCHIVE'

def save_response(r,folder,label):
    folder.mkdir(parents=True,exist_ok=True)
    path=folder/(label+'.raw')
    path.write_bytes(r.content)
    return {'url':r.url,'http_status':r.status_code,'sha256':hashlib.sha256(r.content).hexdigest(),
            'snapshot_path':str(path),'fetched_jst':datetime.now(JST).isoformat(),
            'response_date':r.headers.get('Date'),'age':r.headers.get('Age')}

def collect_fallback(entry,company,now,evidence_dir,session=None,fetcher=None,state=None):
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
        if ticker=='BAYN':
            # Candidate official-host corporate RSS, separate from full coverage.
            routes.append(('bayer_corporate_rss','https://www.bayer.com/en/rss/corporate-news',parse_rss))
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
                problem=None
                strict_rows=[]
                if label=='lundbeck_official_archive_api':
                    floor=((state or {}).get('companies',{}).get(ticker,{}).get('latest_verified_original') or {}).get('date')
                    strict_rows,problem=lundbeck_archive_coverage(resp.content,start,end,now,resp.headers.get('Date'),resp.headers.get('Age'),floor)
                    if not problem:rows=strict_rows
                recent=[x for x in rows if x['listing_date'] and start<=x['listing_date']<=end]
                attempt['recent_count']=len(recent)
                seen={x['url'] for x in entry['primary_releases'] if x.get('original_confirmed')}
                # Feed item alone is never enough. Verify original body, title,
                # date, company host and freshness. External distribution URLs
                # remain candidates pending explicit publisher validation.
                for item in recent[:15]:
                    # Lundbeck links to its own Cision publisher account.
                    u=urlparse(item['url'])
                    publisher_ok=(label=='lundbeck_official_archive_api' and u.hostname=='news.cision.com' and u.path.startswith('/h--lundbeck-a-s/r/'))
                    if item['url'] in seen or not (publisher_ok or any(host_matches(x,item['url']) for x in company['official_indexes'])):
                        continue
                    try:
                        f=(fetcher or LiveFetcher()).get(item['url'])
                        receipt=fetch_receipt(f,store_snapshot(evidence_dir,ticker,f))
                        d=article_details(f.final_url,f.html)
                        final=urlparse(f.final_url)
                        publisher_final_ok=(not publisher_ok or (final.hostname=='news.cision.com' and final.path.startswith('/h--lundbeck-a-s/r/')))
                        if (publisher_final_ok and d['body_confirmed'] and host_matches(item['url'],f.final_url) and
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
                if label=='lundbeck_official_archive_api':
                    if entry.get('stale_cache_status'):problem='CONFLICTING_LISTING_STALE_EVIDENCE'
                    if len(recent)>15 or any(x['url'] not in seen for x in recent):problem='LUNDBECK_ORIGINALS_INCOMPLETE'
                    attempt['coverage_reason']=problem or 'LUNDBECK_UNFILTERED_ARCHIVE_REACHES_BASELINE'
                    if not problem and strict_rows:
                        attempt['coverage_credit']=True
                        entry.update(status='あり' if recent else 'なし',reason='OFFICIAL_LUNDBECK_API_PERIOD_VERIFIED',
                            official_listing_url=resp.url,homepage_visit_status='成功',tool_evidence_ref=attempt['sha256'],
                            latest_publication_date=strict_rows[0]['listing_date'],oldest_publication_date=strict_rows[-1]['listing_date'],
                            listing_page_urls_checked=[resp.url],pagination_complete=True,new_success_jst=now.isoformat(),
                            stale_cache_status=None,source_classification='PERIOD_VERIFIED_OFFICIAL_API')
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
