import csv, json, os, re, hashlib, html, time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor
import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

ROOT=Path(__file__).resolve().parent; DATA=ROOT/'data'; DOCS=ROOT/'docs'
STATE=DATA/'state.json'; EVENTS=DATA/'events.json'; STATUS=DATA/'status.json'
UA='PharmaPressMonitor/1.0 (+GitHub Actions; official newsroom monitor)'
KEYWORDS=re.compile(r'(press|news|release|media|announcement|investor|article|story|202[0-9]|20[0-9]{2})',re.I)
EXCLUDE=re.compile(r'(privacy|cookie|terms|contact|career|job|facebook|linkedin|twitter|instagram|youtube|login|search|subscribe|mailto:|javascript:)',re.I)

def now(): return datetime.now(timezone.utc).isoformat()
def norm(u):
    if not u: return ''
    u=u.split('#')[0]
    return u[:-1] if u.endswith('/') else u

def fetch_requests(url):
    r=requests.get(url,headers={'User-Agent':UA},timeout=35,allow_redirects=True)
    r.raise_for_status()
    if 'charset=' not in r.headers.get('content-type','').lower(): r.encoding='utf-8'
    return r.text, r.url, 'requests'

def fetch_browser(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True)
        page=b.new_page(viewport={'width':1440,'height':1200})
        response=page.goto(url,wait_until='domcontentloaded',timeout=45000)
        if response and response.status >= 400:
            b.close(); raise RuntimeError(f'Official page HTTP {response.status}')
        try: page.wait_for_load_state('networkidle',timeout=15000)
        except Exception: pass
        page.evaluate('window.scrollTo(0, document.body.scrollHeight)'); page.wait_for_timeout(1200)
        out=(page.content(),page.url,'playwright'); b.close(); return out

def fetch(url):
    try:
        text,final,method=fetch_requests(url)
        soup=BeautifulSoup(text,'html.parser')
        if len(soup.find_all('a')) >= 8 and len(soup.get_text(' ',strip=True)) >= 500:
            return text,final,method
    except Exception: pass
    return fetch_browser(url)

def candidates(page_url, raw):
    soup=BeautifulSoup(raw,'html.parser')
    host=urlparse(page_url).netloc.lower().removeprefix('www.')
    items={}
    # Kelun displays article cards in dialogs and supplies no permanent article URL.
    # The date/title key detects changes; RSS opens the official listing.
    if host == 'en.kelun-biotech.com':
        for card in soup.select('.item.href'):
            heading=card.select_one('h3'); date=card.select_one('.time')
            if heading and date:
                title=heading.get_text(' ',strip=True)
                key=hashlib.sha256((date.get_text(strip=True)+'|'+title).encode()).hexdigest()
                items[key]={'url':page_url,'key':page_url+'#release-'+key,'title':title,'score':5}
        return list(items.values())
    for el in soup.select('nav, header, footer, [role="navigation"]'): el.decompose()
    for a in soup.find_all('a',href=True):
        href=a['href'].strip()
        if not href or href.startswith(('#','javascript:','mailto:')): continue
        n=norm(urljoin(page_url,href)); parsed=urlparse(n)
        if parsed.scheme not in ('http','https'): continue
        h=parsed.netloc.lower().removeprefix('www.')
        if h!=host and not h.endswith('.'+host) and not host.endswith('.'+h): continue
        path=parsed.path.lower()
        if re.search(r'/(privacy|cookie|terms|contact|careers?|jobs?|search|subscribe|governance|sustainability|capabilities|production-systems)(/|$)',path): continue
        # Match article routes, never the mere presence of "news" in a host/menu.
        article=bool(re.search(r'/20[0-9]{2}[-/]\d{2}[-/]\d{2}|news-release-details/|press-release-detail/|news-details/|press-releases/detail/|pressreleasedetail\?|newsdetail|newsdetails|/node/\d+|/media/releases/med-|/news_releases/\d{4}/|/news/\d{4}/|/release/\d+',n,re.I))
        if not article:
            article=bool(re.search(r'/(?:news(?:room|-releases)?|press[-_]releases?|media-releases|company-announcements)/[^/?]+',path) and len(path.rstrip('/').split('/')[-1].split('-'))>=4)
        routes={
            'akesobio.com':r'/en/media/akeso-news/[0-9][^/]*',
            'daiichisankyo.com':r'/files/news/pressrelease/pdf/.*\.pdf$',
            'sumitomo-pharma.com':r'/news/(?:20[0-9]{6}[^/]*\.html|assets/pdf/[^/]+\.pdf)$',
            'investors.immunome.com':r'^/immunome-[a-z0-9-]+$',
        }
        if host in routes and re.search(routes[host],path): article=True
        if not article: continue
        texts=[a.get_text(' ',strip=True),a.get('aria-label',''),a.get('title','')]
        heading=a.find(re.compile('^h[1-6]$'))
        if heading: texts.insert(0,heading.get_text(' ',strip=True))
        txt=' '.join((heading.get_text(' ',strip=True) if heading else max(texts,key=len)).split())
        txt=re.sub(r'^Read more(?: about|:| -)?\s*', '', txt, flags=re.I)
        if host == 'alkermes.com':
            if '/news-releases/news-release-details/' not in path: continue
            card=a.parent.parent
            for paragraph in card.find_all('p'):
                value=paragraph.get_text(' ',strip=True)
                if len(value)>40:
                    txt=re.sub(r'^[A-Z][a-z]+ \d{1,2}, \d{4}\s*','',value); break
        if host == 'en.innoventbio.com':
            card=a.find_parent(class_='data_row')
            if card and card.select_one('.div_content'): txt=card.select_one('.div_content').get_text(' ',strip=True)
        if host == 'sumitomo-pharma.com' and path.endswith('.pdf'):
            # PDF-only releases have their headline beside the PDF button.
            card=a.find_parent('li') or a.find_parent('dd')
            if card:
                primary=card.select_one('a[href*=".html"]')
                if primary: continue
                txt=re.sub(r'（PDF/[^）]+）','',card.get_text(' ',strip=True)).strip()
        if len(txt)<12 or re.fullmatch(r'(Read (the )?(Press Release|Release|Media Update|more)|Discover More|More|Download PDF)',txt,re.I):
            parent=a.parent
            for _ in range(5):
                if parent is None: break
                title=parent.find(re.compile('^h[1-6]$')) or parent.select_one('[class*="title"], [class*="Title"], .text-bold')
                if title and len(title.get_text(' ',strip=True))>=12 and title.get_text(' ',strip=True) not in ('Featured News','Press Releases','News Releases'):
                    txt=' '.join(title.get_text(' ',strip=True).split()); break
                parent=parent.parent
        if len(txt)<12 or n==norm(page_url): continue
        if re.fullmatch(r'(Read (the )?(Press Release|Release|Media Update|more)|Discover More|More|Download PDF)',txt,re.I): continue
        if n not in items or len(txt)>len(items[n]['title']):
            items[n]={'url':n,'title':txt[:500],'score':3}
    return list(items.values())

def load(p,default):
    try:return json.load(open(p,encoding='utf-8'))
    except:return default

def save(p,x): p.parent.mkdir(parents=True,exist_ok=True); json.dump(x,open(p,'w',encoding='utf-8'),ensure_ascii=False,indent=2)

def make_feeds(events,companies):
    DOCS.mkdir(exist_ok=True); base=os.getenv('PAGES_URL','').rstrip('/')
    def build(path,title,evs):
        fg=FeedGenerator(); fg.id(base or 'urn:pharma-press-monitor'); fg.title(title); fg.description('New releases detected directly from official company newsroom/press-release pages.'); fg.link(href=(base+'/' if base else 'https://github.com/'),rel='alternate'); fg.language('en')
        for e in reversed(evs[-300:]):
            fe=fg.add_entry(); fe.id(e['id']); fe.title(f"{e['company']}: {e['title']}"); fe.link(href=e['url']); fe.description(f"Official company source. Detected {e['detected_at']}"); fe.pubDate(datetime.fromisoformat(e['detected_at']))
        fg.rss_file(str(path),pretty=True)
    build(DOCS/'feed.xml','Pharma Official Press Releases',events)
    d=DOCS/'feeds'; d.mkdir(exist_ok=True)
    for c in companies:
        slug=re.sub(r'[^a-z0-9]+','-',c['Company'].lower()).strip('-')
        build(d/f'{slug}.xml',f"{c['Company']} Official Press Releases",[e for e in events if e['company']==c['Company']])

def make_site(events,status,companies):
    failures=[s for s in status.values() if s.get('status')!='OK']
    rows=''.join(f"<tr><td>{html.escape(e['detected_at'][:16].replace('T',' '))} UTC</td><td>{html.escape(e['company'])}</td><td><a target='_blank' href='{html.escape(e['url'])}'>{html.escape(e['title'])}</a></td></tr>" for e in reversed(events[-500:])) or '<tr><td colspan=3>基準値の保存後、新着記事はまだ検出されていません。</td></tr>'
    cards=''
    for c in companies:
        record=status.get(c['Company'],{})
        label={'OK':'取得できています','RSS_ONLY':'公式RSSで補完中','FAIL':'取得できません'}.get(record.get('status'),'未実行')
        source=html.escape(record.get('source_url') or c['Official/Source page'],quote=True)
        samples=''.join(f"<li><a href='{html.escape(x['url'],quote=True)}' target='_blank' rel='noopener'>{html.escape(x['title'])}</a></li>" for x in record.get('samples',[]))
        slug=re.sub(r'[^a-z0-9]+','-',c['Company'].lower()).strip('-')
        cards+=f"<div class='card {'bad' if record.get('status')!='OK' else ''}'><b>{html.escape(c['Company'])}</b><br><span>{label}</span><br><small>{html.escape(record.get('checked_at',''))}</small><p><a href='{source}' target='_blank' rel='noopener'>公式の取得先</a> · <a href='feeds/{slug}.xml'>この会社のRSS</a></p><details><summary>取得した記事と確認情報</summary><ul>{samples}</ul><small>{html.escape(record.get('detail',''))}</small></details></div>"
    page=f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>製薬会社 公式ニュース監視</title><style>body{{font:14px system-ui;margin:24px;max-width:1400px}}h1{{margin-bottom:4px}}.summary{{padding:12px;background:#f3f3f3;border-radius:8px}}.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin:16px 0}}.card{{border:1px solid #ddd;padding:9px;border-radius:7px}}.bad{{border:2px solid #b00020;background:#fff1f2}}table{{border-collapse:collapse;width:100%}}td,th{{padding:8px;border-bottom:1px solid #ddd;text-align:left}}a{{color:inherit}}</style></head><body><h1>製薬会社 公式ニュース監視</h1><div class="summary"><b>登録:</b> {len(companies)}社 &nbsp; <b>公式ページ取得:</b> {sum(v.get("status")=="OK" for v in status.values())}社 &nbsp; <b>公式RSSのみ:</b> {sum(v.get("status")=="RSS_ONLY" for v in status.values())}社 &nbsp; <b>取得失敗:</b> {sum(v.get("status")=="FAIL" for v in status.values())}社 &nbsp; <a href="feed.xml">全社統合RSS</a></div><p>約20分間隔で確認。初回は基準値を保存し、その後の新規URLを配信します。「取得できています」は公式サイトの記事候補を取得できた状態です。全記事の網羅は未検証です。公式RSSによる補完と取得失敗は区別して表示します。Kelunは記事の固定URLがないため、見出しと日付で新着を判定し、ニュース一覧にリンクします。</p><h2>会社別の取得状況</h2><div class="grid">{cards}</div><h2>検出した新着記事</h2><table><tr><th>Detected</th><th>Company</th><th>Official release</th></tr>{rows}</table></body></html>'''
    (DOCS/'index.html').write_text(page,encoding='utf-8')

def collect_page(url):
    raw,final,method=fetch(url); cand=candidates(final,raw)
    if not cand and method != 'playwright':
        raw,final,method=fetch_browser(url); cand=candidates(final,raw)
    if not cand: raise RuntimeError('No release links found; source/parser needs review')
    return final,method,cand

def collect_official_data(company):
    """Read public data endpoints used by the official newsroom itself."""
    name=company['Company']; page=company['Official/Source page'].strip()
    if name == 'Amgen':
        raw,_,_=fetch_requests(page)
        node=BeautifulSoup(raw,'html.parser').select_one('#rootId')
        if not node: raise RuntimeError('Amgen official news configuration missing')
        response=requests.get('https://www.amgen.com/MyApi/Custom/NewsListing/GetRecentNewsReleasesV2',
            params={'count':30,'isNasdaq':'false','rootId':node['value']},headers={'User-Agent':UA},timeout=40)
        response.raise_for_status()
        items=[{'url':urljoin(page,x['Url']),'title':x['Title'],'score':5}
            for month in response.json() for x in month['NewsReleases']]
    elif name == 'BioMarin':
        response=requests.post('https://www.biomarin.com/wp-admin/admin-ajax.php',
            data={'press-release-year':'','search':'','paged':1,'action':'filter_press_releases'},
            headers={'User-Agent':UA},timeout=40)
        response.raise_for_status(); response.encoding='utf-8'; items=candidates(page,response.text)
    elif name == 'Neurocrine Biosciences':
        raw,_,_=fetch_requests('https://www.neurocrine.com/api/gcs/news')
        items=[{'url':x['url'],'title':x['title'],'score':5} for x in json.loads(raw)
            if x.get('type')=='news' and x.get('url','').startswith('https://neurocrine.gcs-web.com/news-releases/')]
    elif name == 'Novo Nordisk':
        today=datetime.now(timezone.utc).date()
        response=requests.get('https://www.novonordisk.com/bin/nncorp/news-search',params={
            'searchtext':'null','start':str(today-timedelta(days=366)),'end':str(today),
            'newspath':'/content/dam/nncorp/global/en/investors/content-fragments/ir-materials',
            'limit':50,'currentresults':0,'function':'search','language':'all','type':'all','disablesearchfromdb':'false'
        },headers={'User-Agent':UA},timeout=40)
        response.raise_for_status(); data=response.json()
        if data.get('status')!=200: raise RuntimeError('Official news index returned an error')
        items=[]
        for x in data['data']['resultBeanList']:
            if x.get('language') not in ('en','English'): continue
            if x.get('fromIntegration') and x.get('id'):
                link='https://www.novonordisk.com/news-and-media/news-and-ir-materials/news-details.html?id='+str(x['id'])
            else: link=x.get('newsArticleLink') or x.get('pdfLink')
            if link and link.startswith('https://'): items.append({'url':link,'title':x['title'],'score':5})
    elif name == 'Samsung Biologics':
        response=requests.post('https://samsungbiologics.com/front/en/mediaCenter/listDataAjax.do',data={
            'boardTyp':'PRESS','ccdGrp':'BOARD_CTGRY_CCD_PRESS','lang':'en','schBoardCtgryCcd':'1',
            'schBoardYear':'','schString':'','maxnum':30,'page':1,'pagination':'pagination'
        },headers={'User-Agent':UA},timeout=40)
        response.raise_for_status(); items=[]
        for x in response.json()['dataMainList']:
            slug=x.get('engSortcutLink')
            link='https://samsungbiologics.com/media/company-news/'+slug if slug else 'https://samsungbiologics.com/media/company-news-view?boardseq='+str(x['boardseq'])
            items.append({'url':link,'title':x['engSbjt'],'score':5})
    else: return None
    if not items: raise RuntimeError('Official newsroom data contains no releases')
    return page,'official-newsroom-data',items

SUCCESSORS={
    'Avidity Biosciences':('Novartis',r'avidity|del[- ]?desiran|del[- ]?brax|del[- ]?pacibart|aoc.?1001|aoc.?1020|aoc.?1044'),
    'Reata Pharmaceuticals':('Biogen',r'reata|skyclarys|omaveloxolone'),
}
ALTERNATE_OFFICIAL_PAGES={
    'Biogen':'https://www.biogen.com/home.html',
    'Reata Pharmaceuticals':'https://www.biogen.com/home.html',
    'Harmony Biosciences':'https://www.harmonybiosciences.com/newsroom/',
}

def collect(company):
    url=company['Official/Source page'].strip()
    try:
        result=collect_official_data(company) or collect_page(url)
    except Exception as source_error:
        result=None
        alternate=ALTERNATE_OFFICIAL_PAGES.get(company['Company'])
        if alternate:
            try:
                final,method,items=collect_page(alternate)
                result=final,method+' (official corporate latest-news index)',items
            except Exception: pass
        if result is None:
            feed=company.get('Feed URL','').strip()
            if not feed: raise source_error
            try:
                import xml.etree.ElementTree as ET
                raw,final,_=fetch_requests(feed)
                root=ET.fromstring(raw)
                items=[]
                for item in root.findall('.//item'):
                    title=(item.findtext('title') or '').strip()
                    link=(item.findtext('link') or '').strip()
                    if title and link.startswith('https://'):
                        items.append({'url':norm(link),'title':title[:500],'score':3})
                if not items: raise RuntimeError('Official RSS contains no items')
                result=final,'official-rss-fallback (newsroom unavailable)',items
            except Exception as feed_error:
                raise RuntimeError(str(source_error)+'; official RSS also unavailable: '+str(feed_error)[:100])
    successor=SUCCESSORS.get(company['Company'])
    if successor:
        final,method,items=result
        parent,pattern=successor
        matches=[x for x in items if re.search(pattern,x['title'],re.I)]
        return final,method+f'; successor {parent}: {len(items)} parent releases checked, keyword matches only',matches
    return result

def main():
    companies=list(csv.DictReader(open(ROOT/'companies.csv',encoding='utf-8-sig')))
    state=load(STATE,{}); events=load(EVENTS,[]); status={}; first_global=not bool(state)
    pool=ThreadPoolExecutor(max_workers=6)
    pending={c['Company']:pool.submit(collect,c) for c in companies}
    for i,c in enumerate(companies):
        name=c['Company']; url=c['Official/Source page'].strip(); t=now()
        try:
            final,method,cand=pending[name].result()
            current={x.get('key',x['url']):x for x in cand}
            baseline=state.get(name,{}).get('final_url')==final and state.get(name,{}).get('parser_version')==3
            previous=set(state.get(name,{}).get('urls',[])) if baseline else set()
            new=set(current)-previous if baseline else set()
            # Safety: a drastic collapse is an error signal, not "no news".
            prevn=len(previous)
            if prevn>=8 and len(current)<max(2,int(prevn*0.25)):
                raise RuntimeError(f'candidate count collapsed {prevn}->{len(current)}; possible page/parser failure')
            for u in sorted(new):
                x=current[u]; eid=hashlib.sha256((name+'|'+u).encode()).hexdigest()
                if not any(e['id']==eid for e in events): events.append({'id':eid,'company':name,'ticker':c['Ticker'],'title':x['title'],'url':x['url'],'detected_at':t,'source_page':url})
            state[name]={'parser_version':3,'urls':sorted(current),'checked_at':t,'final_url':final,'method':method,'count':len(current),'samples':list(current.values())[:5]}
            status[name]={'status':('RSS_ONLY' if method.startswith('official-rss') else 'OK'),'checked_at':now(),'detail':f'{method}; {len(current)} release/article links; {len(new)} new','source_url':final,'samples':list(current.values())[:3]}
        except Exception as e:
            status[name]={'status':'FAIL','checked_at':t,'detail':str(e)[:300],'source_url':url}
        print(f'{i+1}/71 {name}: {status[name]}', flush=True)
    pool.shutdown()
    save(STATE,state); save(EVENTS,events); save(STATUS,status); make_feeds(events,companies); make_site(events,status,companies); save(DOCS/'status.json',status)
    ok=sum(v['status']=='OK' for v in status.values()); fail=len(companies)-ok
    print(f'Configured {len(companies)} | OK {ok} | FAIL {fail} | events {len(events)}')
    # Do not silently accept missing checks. GitHub Actions will show red if any source failed.
    if fail: raise SystemExit(2)
if __name__=='__main__': main()
