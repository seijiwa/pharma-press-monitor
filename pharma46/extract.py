"""Conservative parsing: only dated links in official listing content are candidates."""
import re
import json
from datetime import datetime, date
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from dateutil import parser as dateparser

DATE_RE = re.compile(
    r'\b(?:20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[-/.]\d{1,2}[-/.]20\d{2}|'
    r'(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)[.]?\s+\d{1,2},?\s+20\d{2}|'
    r'\d{1,2}\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+20\d{2})\b',
    re.I)
MONTH_DATE_RE = re.compile(r'^20\d{2}-\d{2}-\d{2}$')
EXCLUDE_RE = re.compile(r'/privacy|/terms|/careers?|/contact|/search|/login|/about-us|/governance|/investor-faq', re.I)
ARTICLE_RE = re.compile(r'/(?:news(?:room)?|press[-_]?releases?|media[-_]?releases?|news-release-details|press-release-details|news-details|akeso-news|article|stories|releases?|node)/[^/?#]+|/(?:pressReleasesDetail|newsDetail|newsCenterDetail)\.(?:do|aspx)',re.I)
NEXT_WORDS = {'next', 'older', 'next page', 'load more', 'more news', 'older posts', '>'}

def parse_date(text):
    if not text: return None
    if isinstance(text,str) and re.match(r'^20\d{2}-\d{2}-\d{2}T',text):
        try:return date.fromisoformat(text[:10]).isoformat()
        except ValueError:pass
    text=str(text)
    # CJK official listings: 2026年11月25日, 2026. 11. 25
    text=re.sub(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',r'\1-\2-\3',text)
    text=re.sub(r'(20\d{2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})',r'\1-\2-\3',text)
    m=DATE_RE.search(text)
    if not m:return None
    sample=m.group(0)
    try:
        d=dateparser.parse(sample,dayfirst=bool(re.match(r'^\d{1,2}\s+[A-Za-z]',sample)),fuzzy=False)
        if d and 2018<=d.year<=datetime.now().year+1:return d.date().isoformat()
    except (ValueError,OverflowError,TypeError):pass
    return None

def host_matches(index_url, article_url):
    """Keep links at same registered domain or subdomains, not third-party ads."""
    a=urlparse(index_url).hostname or ''; b=urlparse(article_url).hostname or ''
    a=a.lower().removeprefix('www.');b=b.lower().removeprefix('www.')
    if a==b:return True
    # permit host subdomains only when registrable tail has >= 2 tokens
    return len(a.split('.'))>=2 and (b.endswith('.'+a) or a.endswith('.'+b))

def canonical(url):
    """Avoid an accidental query collapse for valid pagination, strip only fragments."""
    return url.split('#',1)[0]

def _closest_date(anchor):
    # If the anchor itself has a date, accept; else only bounded nearby text
    for node in [anchor, anchor.parent, anchor.parent.parent if anchor.parent else None,
                 anchor.parent.parent.parent if anchor.parent and anchor.parent.parent else None]:
        if node is None:continue
        # A whole list container can contain multiple dates: refuse that as evidence
        node_text=node.get_text(' ',strip=True)
        if len(node_text)>700:continue
        node_text=re.sub(r'(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日',r'\1-\2-\3',node_text)
        node_text=re.sub(r'(20\d{2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})',r'\1-\2-\3',node_text)
        for time_node in node.select('time[datetime],time'):
            parsed=parse_date(time_node.get('datetime') or time_node.get_text(' ',strip=True))
            if parsed:return parsed
        dates=DATE_RE.findall(node_text)
        if len(dates)==1:
            return parse_date(dates[0])
    return None


# Site-scoped row selectors derived from captured official HTML in run 45913588099.
# Never use dates mentioned in headlines or unrelated tabs as publication dates.
def _row_listing(page_url,soup):
    host=(urlparse(page_url).hostname or '').lower()
    path=urlparse(page_url).path
    spec=None
    if host=='news.abbvie.com':
        spec=('.wd_item_wrapper','.wd_title a[href]','.wd_date',None,'mdy')
    elif host=='ir.vikingtherapeutics.com':
        spec=('li.wd_item','.wd_title a[href]','.wd_date',None,'mdy')
    elif host=='www.novartis.com' and path.rstrip('/')=='/news':
        spec=('#tab-all li.each-item','a[href]','time','h3','mdy')
    elif host in ('www.galderma.com','galderma.com') and path.rstrip('/') in ('/news','/newsroom'):
        spec=('a.news-teaser',None,'.header p','h2.title','mdy')
    elif host in ('news.bms.com','investors.hims.com','smmttx.com','ir.tevapharm.com'):
        spec=('.module_item:has(.module_headline-link)','.module_headline-link[href]','.module_date-time',None,'mdy')
    elif host=='www.biomarin.com' and '/news/press-releases' in path:
        spec=('article.press-release','h3 a[href]','p.date',None,'mdy')
    elif host=='c2n.com' and '/news-releases' in path:
        spec=('article.blog-item','.blog-title a[href]','time.blog-date',None,'short_mdy')
    elif host=='www.sumitomo-pharma.com' and path.rstrip('/')=='/news':
        spec=('li:has(.date-container)','.text a[href], .pdf-link a[href]','.date-container .date','.text','mdy')
    elif host=='www.daiichisankyo.com' and '/media/press_release' in path:
        spec=('li.active:has(.newsDate)','.newsTitle a[href]','.newsDate','.newsTitle','mdy')
    elif host=='investors.immunome.com' and path.startswith('/news-releases'):
        spec=('.content-wrapper','h3 a[href]','div.dynamic','h3','mdy')
    elif host=='www.grifols.com' and path.rstrip('/')=='/en/newsroom':
        spec=('.card-content:has(a[href*="/en/view-news/-/news/"])','.button-row a[href]','.card-metadata','p.text-lg.text-bold','mdy')
    elif host=='www.alkermes.com' and path.rstrip('/')=='/news':
        spec=('div','p a[href*="investor.alkermes.com/news-releases/news-release-details/"]','p strong span','p','mdy')
    elif host=='www.zealandpharma.com' and path.rstrip('/')=='/news-media':
        spec=('.card.card-list.card-article','.card-list__cta a[href]','.card__meta time','.card-list__main h2','mdy')
    elif host=='investors.biogen.com' and path.rstrip('/')=='/news/news-releases':
        spec=('.card.cmp-card-tile','.card-body a[href*="/news-releases/news-release-details/"]','.news-date','.card-title','mdy')
    elif host=='ir.ionis.com' and path.rstrip('/') in ('/news-releases','/investor-news/press-releases'):
        spec=('.llf-row:has(.nir-widget--news--date-time)','.nir-widget--news--headline a[href]','.nir-widget--news--date-time','.nir-widget--news--headline','mdy')
    if spec is None:return None
    rows,anchor_sel,date_sel,title_sel,date_kind=spec
    # Avoid nested :has() selectors: SoupSieve strict-mode rejects them.
    if host=='investors.immunome.com' and path.startswith('/news-releases'):
        nodes=[row for row in soup.select('.content-wrapper')
               if row.select_one('h3 a[href]')]
    elif host=='www.alkermes.com' and path.rstrip('/')=='/news':
        nodes=[]
        for link in soup.select(anchor_sel):
            p=link.parent
            row=p.parent if p and p.name=='p' else None
            if row is None or row.name!='div':return []
            if not any(row is candidate for candidate in nodes):nodes.append(row)
    else:
        nodes=soup.select(rows)
    if not nodes:
        return None if soup.select('main article time[datetime]') else []
    result={}
    for row in nodes:
        a=row.select_one(anchor_sel) if anchor_sel else row
        dn=row.select_one(date_sel)
        tn=row.select_one(title_sel) if title_sel else a
        if host=='www.alkermes.com':
            dated=[p for p in row.find_all('p',recursive=False) if p.select_one('strong span')]
            if len(dated)!=1:return []
            tn=dated[0]
            dn=tn.select_one('strong span')
        if a is None or dn is None or tn is None or not a.get('href'):return []
        url=canonical(urljoin(page_url,a['href']))
        # Zealand's own archive directly links its published releases on
        # GlobeNewswire. Allow those links as listing evidence only; the
        # independent original-body verifier still enforces its host check.
        external_zealand=(host=='www.zealandpharma.com' and
            urlparse(url).hostname=='www.globenewswire.com' and
            re.match(r'^/news-release/20\d{2}/\d{2}/\d{2}/\d+/0/en/zealand-pharma[-.].+',urlparse(url).path,re.I))
        if (not host_matches(page_url,url) and not external_zealand) or url==canonical(page_url):return []
        date_text=dn.get('datetime') or dn.get_text(' ',strip=True)
        # Only this dedicated date field can supply the two-digit or spaced year.
        compact=re.sub(r'\s*([./-])\s*',r'\1',date_text)
        if date_kind=='short_mdy' and re.fullmatch(r'\d{1,2}/\d{1,2}/\d{2}',compact):
            m,d,y=map(int,compact.split('/'))
            try:published=date(2000+y,m,d).isoformat()
            except ValueError:return []
        elif re.fullmatch(r'\d{1,2}[./-]\d{1,2}[./-]20\d{2}',compact):
            m,d,y=map(int,re.split(r'[./-]',compact))
            try:published=date(y,m,d).isoformat()
            except ValueError:return []
        else:published=parse_date(date_text)
        title=' '.join(tn.get_text(' ',strip=True).split())
        if host=='www.alkermes.com':
            title=title.removeprefix(' '.join(dn.get_text(' ',strip=True).split())).strip()
        if not published or not title:return []
        if url in result and result[url]['listing_date']!=published:
            return []  # inconsistent duplicated row is not coverage evidence
        result.setdefault(url,{'url':url,'title':title[:500],'listing_date':published})
    return list(result.values())

def listing_entries(page_url, html, preserve_order=False):
    soup=BeautifulSoup(html,'html.parser')
    for el in soup.select('header,footer,nav,[role="navigation"]'):
        el.decompose()
    scoped=_row_listing(page_url,soup)
    if scoped is not None:
        return scoped if preserve_order else sorted(scoped,key=lambda x:(x['listing_date'],x['url']),reverse=True)
    entries={}
    for a in soup.find_all('a',href=True):
        href=a['href'].strip()
        if href.startswith(('javascript:','mailto:','#','data:')):continue
        url=canonical(urljoin(page_url,href))
        if not url.startswith(('https://','http://')) or not host_matches(page_url,url):continue
        if EXCLUDE_RE.search(url):continue
        if not ARTICLE_RE.search(urlparse(url).path):
            # Permit deep-segment date paths, even if the route is different.
            if not re.search(r'/20\d{2}[/\-]\d{2}[/\-]\d{2}',url):continue
        if urlparse(url).path.rstrip('/') == urlparse(page_url).path.rstrip('/') and urlparse(url).query == urlparse(page_url).query:continue
        title=' '.join(a.get_text(' ',strip=True).split())
        if len(title)<16:
            h=a.find(['h2','h3','h4'])
            if h:title=h.get_text(' ',strip=True)
        if len(title)<16 or title.lower().startswith(('read more','read the release','view more')):
            parent=a.parent
            for _ in range(3):
                if parent is None:break
                heading=parent.find(['h2','h3','h4'])
                if heading and 16<=len(heading.get_text(' ',strip=True))<=450:
                    title=heading.get_text(' ',strip=True);break
                parent=parent.parent
        if not (16<=len(title)<=600):continue
        published=_closest_date(a)
        if not published:continue
        if url not in entries or len(title)>len(entries[url]['title']):
            entries[url]={'url':url,'title':title[:500],'listing_date':published}
    if preserve_order:
        return list(entries.values())
    return sorted(entries.values(),key=lambda x:(x['listing_date'],x['url']),reverse=True)

def next_page_urls(page_url,html):
    soup=BeautifulSoup(html,'html.parser');links=[]
    for a in soup.find_all('a',href=True):
        label=' '.join(a.get_text(' ',strip=True).lower().split())
        rel=' '.join(a.get('rel',[])).lower()
        aria=str(a.get('aria-label','')).lower()
        href=a['href']; url=canonical(urljoin(page_url,href))
        if not host_matches(page_url,url) or url==canonical(page_url):continue
        if 'next' in rel or label in NEXT_WORDS or 'next page' in aria:
            links.append(url)
    if urlparse(page_url).hostname=='www.jnj.com' and urlparse(page_url).path=='/media-center/press-releases':
        for n in soup.select('bsp-load-more[data-url]'):
            url=canonical(urljoin(page_url,n['data-url']))
            if (host_matches(page_url,url) and urlparse(url).path==urlparse(page_url).path and
                re.fullmatch(r'p=\d+',urlparse(url).query) and url!=canonical(page_url)):
                links.append(url)
    return list(dict.fromkeys(links))

def page_has_unresolved_load_more(html,page_url=None,found_boundary=False):
    soup=BeautifulSoup(html,'html.parser')
    text=soup.get_text(' ',strip=True).lower()
    present=any(x in text for x in ('load more', 'show more releases', 'load additional', 'view more news'))
    if not present or not page_url:return present
    host=urlparse(page_url).hostname
    # The next page is explicit, not an unresolved JS-only continuation.
    if host=='www.jnj.com' and next_page_urls(page_url,html):
        controls=soup.select('bsp-load-more[data-url]')
        if len(controls)==1:
            controls[0].decompose()
            remaining=soup.get_text(' ',strip=True).lower()
            return any(x in remaining for x in ('load more','show more releases','load additional','view more news'))
    # Viking has a declared offset/count on the exact chronological list.
    # Only resolve the continuation after the audited date boundary is reached,
    # with a complete visible page and no other unresolved load-more control.
    if host=='ir.vikingtherapeutics.com' and found_boundary:
        controls=soup.select('button.wd_load_more-trigger[data-limit][data-offset][data-total][data-content]')
        if len(controls)==1:
            control=controls[0]
            try:
                limit,offset,total=(int(control['data-'+k]) for k in ('limit','offset','total'))
                rows=soup.select('.wd_item_list li.wd_item')
                scoped=_row_listing(page_url,soup)
                if control['data-content']=='.wd_item_list' and 0<limit==offset==len(rows)==len(scoped or [])<total:
                    control.decompose()
                    remaining=soup.get_text(' ',strip=True).lower()
                    return any(x in remaining for x in ('load more','show more releases','load additional','view more news'))
            except (ValueError,TypeError):pass
    return present

def article_details(url,html):
    soup=BeautifulSoup(html,'html.parser')
    title=(soup.find('meta',attrs={'property':'og:title'}) or {}).get('content')
    if not title:
        h=soup.find('h1')
        title=h.get_text(' ',strip=True) if h else (soup.title.get_text(' ',strip=True) if soup.title else '')
    datev=None
    for attrs in ({'property':'article:published_time'},{'name':'date'},{'name':'pubdate'},
                  {'name':'datePublished'},{'itemprop':'datePublished'}):
        node=soup.find('meta',attrs=attrs)
        if node:datev=parse_date(node.get('content') or node.get('datetime'))
        if datev:break
    if not datev:
        time_node=soup.find('time')
        if time_node:datev=parse_date(time_node.get('datetime') or time_node.get_text(' ',strip=True))
    if not datev:
        for script in soup.find_all('script',type='application/ld+json'):
            try:
                data=json.loads(script.string or script.get_text())
                if isinstance(data,list):nodes=data
                elif isinstance(data,dict) and '@graph' in data:nodes=data['@graph']
                else:nodes=[data]
                for node in nodes:
                    if isinstance(node,dict):
                        datev=parse_date(node.get('datePublished'))
                        if datev:break
                if datev:break
            except (ValueError,TypeError):pass
    for el in soup.select('nav,header,footer,script,style,aside'):
        el.decompose()
    main=soup.select_one('article') or soup.select_one('main') or soup.select_one('[class*=body]') or soup.body
    body=' '.join(main.get_text(' ',strip=True).split()) if main else ''
    # This date fallback is deliberately article-only, not listing; require close to heading
    if not datev:datev=parse_date(body[:750])
    return {'url':url,'title':str(title)[:500],'published_date':datev,'body':body[:15000],
            'body_confirmed':bool(datev and len(body)>180 and len(title)>12)}
