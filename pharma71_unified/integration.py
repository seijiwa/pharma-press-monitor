"""Transparent multi-route monitoring matrix; no substitution for newsroom coverage."""
from datetime import datetime
import re

PARENT={'RNA':('NOVN','Novartis',r'\bavidity\b|\bdel-desiran\b|\bdel-brax\b|\bdel-zota\b'),
        'REATA':('BIIB','Biogen',r'\breata\b|\bskyclarys\b|\bomaveloxolone\b'),
        'JNANA':(None,'Otsuka',r'\bjnana\b|\bjnt[- ]517\b|\brepinatrabit\b')}
def iso(s):
    try:return datetime.fromisoformat(s)
    except (ValueError,TypeError):return None
def parent_scope(entries,prior_state,now,parent_attempts=None):
    by={e['ticker']:e for e in entries}
    out=[]
    for ticker,(parent,name,pattern) in PARENT.items():
        child=by[ticker];p=by.get(parent)
        # A historical row was collected directly against a configured parent
        # archive at the historical baseline before its independent status was reset.
        alt=(parent_attempts or {}).get(ticker)
        if alt and alt.get('status')!='未確認':p=alt
        r={'ticker':ticker,'parent_ticker':parent,'parent_name':name,'status':'PARENT_SCOPE_UNCONFIRMED',
           'scope':'Named parent newsroom disclosures mentioning the historical company or registered assets; not independent-company news',
           'period':child['comparison_period'],'matched_originals':[]}
        # The parent period must reach the historical row's requested start,
        # never silently import a narrower prior-success window.
        if p:
            for x in p.get('primary_releases',[]):
                if x.get('original_confirmed') and re.search(pattern,(x.get('original_title') or '')+' '+(x.get('body_excerpt') or ''),re.I):
                    r['matched_originals'].append({'url':x['url'],'title':x.get('original_title'),'published_date':x.get('published_date'),'receipt':x.get('receipt')})
            ps=iso(p['comparison_period']['start_jst']);cs=iso(child['comparison_period']['start_jst'])
            pe=iso(p['comparison_period']['end_jst']);ce=iso(child['comparison_period']['end_jst'])
            # Even a complete parent index only proves title/excerpt scope.
            # Full article bodies are not retained in parsed release objects.
            r['parent_listing_period_verified']=bool(p['status']!='未確認' and ps and cs and pe and ce and ps<=cs and pe>=ce)
            r['status']='PARENT_LISTING_VERIFIED_KEYWORD_SCOPE_LIMITED' if r['parent_listing_period_verified'] else 'PARENT_SCOPE_UNCONFIRMED'
        else:r['reason']='PARENT_ARCHIVE_UNCONFIRMED' if alt else 'PARENT_OUTSIDE_CURRENT_UNIVERSE'
        out.append(r)
    return out

def matrix(entries,reg,parents):
    sec={e['ticker']:e for e in reg.get('entries',[])}
    parent={e['ticker']:e for e in parents}
    td=reg.get('tdnet',{})
    td_candidates={}
    for x in td.get('entries',[]):td_candidates[x['ticker']]=td_candidates.get(x['ticker'],0)+1
    hk_candidates={}
    for x in reg.get('hkex',{}).get('entries',[]):hk_candidates[x['ticker']]=hk_candidates.get(x['ticker'],0)+1
    rows=[]
    for e in entries:
        t=e['ticker'];s=sec.get(t,{})
        direct=e['status']!='未確認'
        regulatory=(s.get('status')=='FILING_METADATA_RETRIEVED' and s.get('issuer_identity_verified') is True)
        scope='HISTORICAL_PARENT' if t in parent else 'INDEPENDENT'
        # No broad regulatory coverage claim: it is recent 8-K/6-K metadata only.
        status=('PARENT_SCOPE_LIMITED' if t in parent and parent[t].get('parent_listing_period_verified') else
                'PARENT_SCOPE_UNCONFIRMED' if t in parent else
                'NEWSROOM_PERIOD_VERIFIED' if direct else
                'SEC_WINDOW_ONLY_NEWSROOM_UNCONFIRMED' if regulatory else 'NO_VERIFIED_PERIOD')
        rows.append({'ticker':t,'scope':scope,'status':status,'newsroom_period_verified':direct,
                     'sec_filing_window_verified':regulatory,'sec_status':s.get('status','NOT_RUN'),
                     'sec_filing_count':len(s.get('filings',[])),
                     'tdnet_candidates':td_candidates.get(t,0),
                     'hkex_candidates':hk_candidates.get(t,0),
                     'parent_status':parent.get(t,{}).get('status'),
                     'original_count':sum(bool(x.get('original_confirmed')) for x in e.get('primary_releases',[]))})
    active=[x for x in rows if x['scope']=='INDEPENDENT']
    summary={'tracked':len(rows),'independent':len(active),'historical':len(rows)-len(active),
             'independent_newsroom_verified':sum(x['newsroom_period_verified'] for x in active),
             'independent_sec_only':sum(x['status']=='SEC_WINDOW_ONLY_NEWSROOM_UNCONFIRMED' for x in active),
             'independent_no_verified_period':sum(x['status']=='NO_VERIFIED_PERIOD' for x in active),
             'parent_limited':sum(x['status']=='PARENT_SCOPE_LIMITED' for x in rows),
             'parent_unconfirmed':sum(x['status']=='PARENT_SCOPE_UNCONFIRMED' for x in rows)}
    # Keep strict original gate: supplemental scope does not equal all-news coverage.
    return {'summary':summary,'rows':rows,'parent_scopes':parents,'production_ready':False}
def report(m):
    s=m['summary']
    lines=['','## 複数取得経路の統合監査（71対象、範囲別）',
           f'- 独立企業 {s["independent"]} / 公式一覧確認 {s["independent_newsroom_verified"]} / SECのみ確認 {s["independent_sec_only"]} / いずれも未確認 {s["independent_no_verified_period"]}',
           f'- 買収済み監視対象 {s["historical"]} / 親会社一覧の限定確認 {s["parent_limited"]} / 未確認 {s["parent_unconfirmed"]}',
           '- SECのみの確認は公式ニュースの不存在証明ではありません。',
           '|Ticker|監視範囲|判定|SEC|TDnet候補|HKEX候補|','|---|---|---|---|---:|---:|']
    for x in m['rows']:
        lines.append(f'|{x["ticker"]}|{x["scope"]}|{x["status"]}|{x["sec_status"]}|{x["tdnet_candidates"]}|{x["hkex_candidates"]}|')
    for p in m['parent_scopes']:
        lines.append(f'- {p["ticker"]}: 親会社 {p["parent_name"]} / {p["status"]} / 原文候補 {len(p["matched_originals"])}件')
    return '\n'.join(lines)+'\n'
