"""Lonza has a separate media advisory archive. Both source scopes must pass."""
from datetime import datetime
from pharma46.engine import scan_index
from pharma46.fetch import LiveFetcher

def combine(entry,scan):
    entry['additional_scope']={'name':'Lonza Media Advisories','period':entry['comparison_period'],'scan':scan}
    known={p['url']:p for p in entry['primary_releases']}
    for p in scan.get('candidate_releases',[]):
        if p['url'] not in known or (p.get('original_confirmed') and not known[p['url']].get('original_confirmed')):
            known[p['url']]=p
    entry['primary_releases']=list(known.values())
    if not scan.get('pagination_complete'):
        if entry['status']!='未確認':
            entry.update(status='未確認',new_success_jst=None,pagination_complete=False,reason='LONZA_MEDIA_ADVISORY_SCOPE_UNCONFIRMED',source_classification='UNVERIFIED')
        return entry
    if entry['status']!='未確認':
        entry['listing_page_urls_checked']=list(dict.fromkeys(entry['listing_page_urls_checked']+scan['listing_page_urls_checked']))
        entry['source_classification']='PERIOD_VERIFIED_NEWS_AND_MEDIA_ADVISORIES'
        if any(p.get('original_confirmed') for p in scan['candidate_releases']):
            entry['status']='あり'
    return entry

def collect_lonza_scope(entry,company,now,evidence_dir,fetcher=None):
    if entry['ticker']!='LONN':return entry
    baseline=datetime.fromisoformat(entry['comparison_period']['start_jst'])
    media=dict(company,known_official_release_floor={'date':'2026-11-16','url':'https://www.lonza.com/media-advisories/2026-11-16-16-30','purpose':'independently indexed advisory freshness floor'})
    try:
        scan=scan_index(fetcher or LiveFetcher(),media,'https://www.lonza.com/media-advisories',baseline,now,evidence_dir,max_pages=5,max_primary=15)
    except Exception as exc:
        scan={'pagination_complete':False,'candidate_releases':[],'errors':[{'failure':type(exc).__name__}]}
    return combine(entry,scan)
