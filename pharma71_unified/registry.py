"""71-name registry: merge audited 46 entries with the existing 71-company watchlist."""
import csv,json
from pathlib import Path
from pharma46.engine import ORDER

# Explicit stable identifiers for companies without stock tickers in companies.csv.
UNTICKERED={'C2N Diagnostics':'C2N','Catalent':'CATALENT','Daiichi Sankyo':'4568 JP',
 'FUJIFILM Diosynth Biotechnologies':'FUJIFILM-CDMO','Genentech':'GENENTECH',
 'Jnana Therapeutics':'JNANA','Kyowa Kirin':'4151 JP','Lupin':'LUPIN',
 'Reata Pharmaceuticals':'REATA','Santen Pharmaceutical':'4536 JP','Sumitomo Pharma':'4506 JP'}
HISTORICAL={'RNA','REATA','JNANA'}

# Alternative public corporate newsroom URLs, not access-control bypasses.
# Candidate addresses inherited from the running 71 monitor plus the actual
# recorded FUJIFILM official relocation; audit success requires live receipts.
ALTERNATES={
 'BAYN':['https://www.bayer.com/media/en-us/','https://www.bayer.com/en/investors/investor-news'],
 'DNLI':['https://investors.denalitherapeutics.com/investors'],
 'LONN':['https://www.lonza.com/news-and-media/news-archive','https://www.lonza.com/media','https://www.lonza.com/investors'],
 'REGN':['https://investor.regeneron.com/news/press-releases'],
 'SRRK':['https://scholarrock.com/investors-media/press-releases/'],
 'BIIB':['https://www.biogen.com/home.html'],
 'HRMY':['https://www.harmonybiosciences.com/newsroom/'],
 'ALKS':['https://investor.alkermes.com/press-releases'],
 'EXEL':['https://ir.exelixis.com/press-releases','https://ir.exelixis.com/news-releases'],
 'KURA':['https://ir.kuraoncology.com/press-releases','https://ir.kuraoncology.com/news-releases'],
 'NBIX':['https://neurocrine.gcs-web.com/investors/news-releases'],
 'ERAS':['https://investors.erasca.com/news-events/news-releases'],
 'GENENTECH':['https://www.gene.com/media/press-releases'],
 'FUJIFILM-CDMO':['https://fujifilmbiotechnologies.fujifilm.com/about/news/'],
}


def load_registry(csv_path='companies.csv', base_path='pharma46/sources.json'):
    base=json.loads(Path(base_path).read_text(encoding='utf-8'))['companies']
    if [c['ticker'] for c in base]!=ORDER:
        raise ValueError('unexpected core 46 registry')
    core={c['ticker']:c for c in base}
    with open(csv_path,encoding='utf-8-sig',newline='') as f:
        rows=list(csv.DictReader(f))
    if len(rows)!=71 or len({r['Company'] for r in rows})!=71:
        raise ValueError('expected exactly 71 unique company names')
    merged={}
    for row in rows:
        ticker=row['Ticker'].strip() or UNTICKERED[row['Company']]
        ticker='ROP' if ticker=='ROG' else ticker
        if ticker in merged:
            raise ValueError('duplicate ticker '+ticker)
        company=dict(core.get(ticker,{}))
        urls=list(company.get('official_indexes',[]))
        source=row['Official/Source page'].strip()
        # Prefer independently configured official source from the 71 monitor;
        # keep user-designated Lilly/Jazz/Kelun source first.
        if source and source not in urls:
            urls=([source]+urls) if ticker not in {'LLY','JAZZ','6990 HK'} else ([urls[0],source]+urls[1:])
        if ticker in ALTERNATES:
            urls=list(dict.fromkeys(ALTERNATES[ticker]+urls))
        if not urls or not all(x.startswith('https://') for x in urls):
            raise ValueError('missing or invalid official source '+ticker)
        company.update(ticker=ticker,name=row['Company'],official_indexes=urls[:3],
                       batch_id=company.get('batch_id','D'),source_status='CANDIDATES_NOT_VERIFIED',
                       legacy_feed_url=row['Feed URL'],legacy_fallback=row['Fallback'])
        if ticker=='JNANA':
            company['official_indexes']=['https://www.otsuka.co.jp/en/company/newsreleases/','https://www.otsuka.co.jp/company/newsreleases/']
        if ticker in HISTORICAL:
            company['scope_note']='Historical bookmark: parent disclosure only, not independent company coverage'
        merged[ticker]=company
    if not set(ORDER)<=set(merged):
        raise ValueError('core company missing')
    order=list(ORDER)+[t for t in merged if t not in core]
    return {'version':'71-staging-1','companies':[merged[t] for t in order]}

def ticker_order(registry):
    order=[c['ticker'] for c in registry['companies']]
    if len(order)!=71 or len(set(order))!=71 or order[:46]!=ORDER:
        raise ValueError('unexpected 71-company registry')
    return order
