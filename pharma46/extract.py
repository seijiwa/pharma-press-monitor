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

def listing_entries(page_url, html, preserve_order=False):
    soup=BeautifulSoup(html,'html.parser')
    for el in soup.select('header,footer,nav,[role="navigation"]'):
        el.decompose()
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
    return list(dict.fromkeys(links))

def page_has_unresolved_load_more(html):
    text=BeautifulSoup(html,'html.parser').get_text(' ',strip=True).lower()
    return any(x in text for x in ('load more', 'show more releases', 'load additional', 'view more news'))

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
