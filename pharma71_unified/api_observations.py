"""Secondary, official newsroom API observations. Never promote to period coverage.

The endpoints are those already used by the existing 71-company collector.
Persist response bytes/HTTP status even for schema or date failures. The API
results are independent candidate evidence; direct original checks remain required.
"""
import hashlib,json
from pathlib import Path
from datetime import timedelta,datetime
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
        date_fields=('regDate','regDt','publishDate','publishedDate','boardRegDate')
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
        date=parse_date(rawdate)
        if title and url and str(url).startswith('https://') and host_matches(origin,url):
            candidates.append({'url':url,'title':unescape(str(title)),'listing_date':date})
    return candidates, sorted({k for x in records for k in x}),len(records)

def supplement(entry,now,evidence_dir):
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
        rows,keys,count=parse_api(ticker,r.json())
        attempt.update(record_count=count,record_keys=keys,dated_candidate_count=sum(bool(x['listing_date']) for x in rows))
        attempt['candidate_releases']=rows[:50]
        start=entry['comparison_period']['start_jst'][:10]
        end=(now+timedelta(days=1)).date().isoformat()
        fetcher=LiveFetcher()
        existing={x['url'] for x in entry['primary_releases'] if x.get('original_confirmed')}
        for item in [x for x in rows if x['listing_date'] and start<=x['listing_date']<=end][:15]:
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
    except Exception as exc:
        attempt['error']=type(exc).__name__+':'+str(exc)[:220]
