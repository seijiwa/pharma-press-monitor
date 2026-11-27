"""Official newsroom API observations with strict first-page coverage checks.

The endpoints are those already used by the existing 71-company collector.
Persist response bytes/HTTP status even for schema or date failures. The API
results are independent candidate evidence; direct original checks remain required.
"""
import hashlib,json
from pathlib import Path
from datetime import timedelta,datetime,timezone
from urllib.parse import urlparse,urljoin
from html import unescape
import requests
from pharma46.fetch import JST,LiveFetcher,store_snapshot,FetchError,UA
from pharma46.extract import parse_date,article_details,host_matches
from pharma46.engine import fetch_receipt,title_matches,suspect_cache

def fetch_api(ticker,now):
    if ticker=='NOVOB':
        url='https://www.novonordisk.com/bin/nncorp/news-search'
        r=requests.get(url,params={'searchtext':'null','start':str(now.date()-timedelta(days=366)),
            'end':str(now.date()),'newspath':'/content/dam/nncorp/global/en/investors/content-fragments/ir-materials',
            'limit':50,'currentresults':0,'function':'search','language':'all','type':'all',
            'disablesearchfromdb':'false'},headers={'User-Agent':UA},timeout=40)
    elif ticker=='207940 KS':
        url='https://samsungbiologics.com/front/en/mediaCenter/listDataAjax.do'
        r=requests.post(url,data={'boardTyp':'PRESS','ccdGrp':'BOARD_CTGRY_CCD_PRESS','lang':'en',
            'schBoardCtgryCcd':'1','schBoardYear':'','schString':'','maxnum':30,'page':1,
            'pagination':'pagination'},headers={'User-Agent':UA},timeout=40)
    else:raise ValueError('unsupported API')
    return r

def parse_api(ticker,data):
    if ticker=='NOVOB':
        if data.get('status')!=200:raise ValueError('API status not 200')
        records=data['data']['resultBeanList']
        date_fields=('publicationDate','publishDate','publishedDate','releaseDate','date')
    elif ticker=='207940 KS':
        records=data['dataMainList']
        date_fields=('boarddtm','regDate','regDt','publishDate','publishedDate','boardRegDate')
    else:raise ValueError('unsupported API')
    if not isinstance(records,list):raise ValueError('unexpected records type')
    candidates=[]
    for x in records:
        if ticker=='NOVOB':
            if x.get('language') not in ('en','English'):continue
            title=x.get('title')
            url=('https://www.novonordisk.com/news-and-media/news-and-ir-materials/news-details.html?id='+str(x['id'])
                 if x.get('fromIntegration') and x.get('id') else x.get('newsArticleLink') or x.get('pdfLink'))
            origin='https://www.novonordisk.com/'
        else:
            title=x.get('engSbjt')
            slug=x.get('engSortcutLink')
            url=('https://samsungbiologics.com/media/company-news/'+str(slug) if slug else
                 'https://samsungbiologics.com/media/company-news-view?boardseq='+str(x['boardseq']) if x.get('boardseq') else None)
            origin='https://samsungbiologics.com/'
        rawdate=next((x[k] for k in date_fields if x.get(k)),None)
        date=(datetime.fromtimestamp(rawdate/1000,tz=JST).date().isoformat() if ticker=='207940 KS' and isinstance(rawdate,(int,float)) and 946684800000<rawdate<4102444800000 else parse_date(rawdate))
        if title and url and str(url).startswith('https://') and host_matches(origin,url):
            candidates.append({'url':url,'title':unescape(str(title)),'listing_date':date})
    return candidates, sorted({k for x in records for k in x}),len(records)


def coverage_check(ticker,data,rows,start,end,now,response_date,age,known_floor=None):
    """Credit only a complete, bounded first page from the company's actual API.
    A truncated page is sufficient only if its ordered dates cross the baseline.
    Reject missing rows, inconsistent total counts, future dates and stale headers.
    """
    from email.utils import parsedate_to_datetime
    try:
        if not response_date:return 'API_MISSING_HTTP_DATE'
        stamp=parsedate_to_datetime(response_date)
        if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=timezone.utc)
        delta=now.astimezone(timezone.utc)-stamp
        if delta>timedelta(hours=48) or delta< -timedelta(minutes=10) or (age is not None and int(age)>172800):
            return 'API_STALE_HTTP'
        if ticker=='NOVOB':
            raw=data['data']['resultBeanList'];total=int(data['data']['numberOfResults']);limit=50
            if start<(now.date()-timedelta(days=366)).isoformat():return 'API_QUERY_WINDOW_TOO_SHORT'
            if any(x.get('language') not in ('en','English') for x in raw):return 'API_MIXED_SCOPE'
        elif ticker=='207940 KS':
            raw=data['dataMainList'];total=int(data['totalCnt']['cnt']);limit=30
            if any(str(x.get('boardCtgryCcd'))!='1' for x in raw):return 'API_MIXED_SCOPE'
        else:return 'API_UNSUPPORTED'
        if not raw or total<len(raw) or len(raw)!=min(limit,total) or len(rows)!=len(raw):
            return 'API_TRUNCATED_OR_UNPARSED'
        dates=[x['listing_date'] for x in rows]
        if any(not x or x>end for x in dates):return 'API_INVALID_DATES'
        if dates!=sorted(dates,reverse=True):return 'API_UNSORTED'
        if len({x['url'] for x in rows})!=len(rows):return 'API_DUPLICATE_URL'
        if known_floor and dates[0]<known_floor:return 'API_KNOWN_RELEASE_MISSING'
        if dates[-1]>=start:return 'API_BASELINE_NOT_REACHED'
        return None
    except (KeyError,ValueError,TypeError,OverflowError,AttributeError):
        return 'API_INVALID_SCHEMA_OR_METADATA'

def supplement(entry,now,evidence_dir,state=None):
    if entry['ticker'] not in ('NOVOB','207940 KS') or entry['status']!='未確認':return
    ticker=entry['ticker']
    folder=Path(evidence_dir)/ticker.replace(' ','_')
    folder.mkdir(parents=True,exist_ok=True)
    attempt={'method':'official_newsroom_api','coverage_credit':False}
    entry['alternative_attempts'].append(attempt)
    try:
        r=fetch_api(ticker,now)
        path=folder/'official_api.json.raw'
        path.write_bytes(r.content)
        attempt.update(url=r.url,http_status=r.status_code,sha256=hashlib.sha256(r.content).hexdigest(),
                       snapshot_path=str(path),fetched_jst=datetime.now(JST).isoformat(),
                       response_date=r.headers.get('Date'),age=r.headers.get('Age'))
        r.raise_for_status()
        expected_host='www.novonordisk.com' if ticker=='NOVOB' else 'samsungbiologics.com'
        if urlparse(r.url).scheme!='https' or urlparse(r.url).hostname!=expected_host:raise ValueError('API_REDIRECT_OUTSIDE_ISSUER')
        data=r.json()
        rows,keys,count=parse_api(ticker,data)
        attempt.update(record_count=count,record_keys=keys,dated_candidate_count=sum(bool(x['listing_date']) for x in rows))
        attempt['candidate_releases']=rows[:50]
        start=entry['comparison_period']['start_jst'][:10]
        end=(now+timedelta(days=1)).date().isoformat()
        fetcher=LiveFetcher()
        existing={x['url'] for x in entry['primary_releases'] if x.get('original_confirmed')}
        recent=[x for x in rows if x['listing_date'] and start<=x['listing_date']<=end]
        for item in recent[:15]:
            if item['url'] in existing:continue
            try:
                article=fetcher.get(item['url'])
                receipt=fetch_receipt(article,store_snapshot(evidence_dir,ticker,article))
                details=article_details(article.final_url,article.html)
                ok=(details['body_confirmed'] and host_matches(item['url'],article.final_url) and
                    title_matches(item['title'],details['title']) and details['published_date']==item['listing_date']
                    and not suspect_cache(article,now))
                if ok:
                    entry['primary_releases'].append({'ticker':ticker,'name':entry['company_name'],
                        'url':item['url'],'listing_title':item['title'],'listing_date':item['listing_date'],
                        'original_title':details['title'],'published_date':details['published_date'],
                        'body_excerpt':details['body'][:600],'original_confirmed':True,
                        'receipt':receipt,'new_status':'API_ORIGINAL_VERIFIED_NEWNESS_UNDETERMINED'})
                    existing.add(item['url'])
            except (FetchError,ValueError,TypeError) as exc:
                attempt.setdefault('article_errors',[]).append({'url':item['url'],'error':str(exc)[:200]})
        prior=(state or {}).get('companies',{}).get(ticker,{})
        floor=(prior.get('latest_verified_original') or {}).get('date')
        if entry.get('latest_publication_date'):
            floor=max(floor or '',entry['latest_publication_date'])
        problem=coverage_check(ticker,data,rows,start,end,now,r.headers.get('Date'),r.headers.get('Age'),floor)
        if entry.get('stale_cache_status'):problem='CONFLICTING_LISTING_STALE_EVIDENCE'
        if len(recent)>15 or any(x['url'] not in existing for x in recent):problem='API_PRIMARY_ORIGINALS_INCOMPLETE'
        attempt['coverage_reason']=problem or 'API_ORDERED_PAGE_REACHES_BASELINE'
        if problem is None:
            attempt['coverage_credit']=True
            dates=[x['listing_date'] for x in rows]
            entry.update(status='あり' if recent else 'なし',reason='OFFICIAL_API_PERIOD_VERIFIED',
                official_listing_url=r.url,homepage_visit_status='成功',tool_evidence_ref=attempt['sha256'],
                latest_publication_date=dates[0],oldest_publication_date=dates[-1],
                listing_page_urls_checked=[r.url],pagination_complete=True,
                new_success_jst=now.isoformat(),stale_cache_status=None,
                source_classification='PERIOD_VERIFIED_OFFICIAL_API')
    except Exception as exc:
        attempt['error']=type(exc).__name__+':'+str(exc)[:220]
