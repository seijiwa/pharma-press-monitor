"""Primary collection, conservative page coverage, audit and rendering.

A company is NEVER 'なし' just because one URL has no new articles.
"""
from __future__ import annotations
import hashlib,json,logging,os,re
from difflib import SequenceMatcher
from datetime import datetime,timedelta,timezone,date
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from .fetch import LiveFetcher,FetchError,store_snapshot,JST
from .extract import listing_entries,next_page_urls,page_has_unresolved_load_more,article_details,host_matches
LOG=logging.getLogger(__name__)
BATCHES={'A':['LLY','ABBV','AMGN','BIIB','BMY','GILD','JNJ','MRK','PFE','REGN','AZN','GSK','NOVN','NOVOB','ROP','SAN'],
         'B':['GALD','LONN','VRTX','JAZZ','ALKS','SRPT','VKTX','VERA','CAPR','KURA','SMMT','ZEAL','SUPN','ALMS','HRMY'],
         'C':['HIMS','RVMD','SRRK','ORKA','ERAS','CGEM','IMNM','GPCR','ALVO','DNLI','6990 HK','9926 HK','1801 HK','2269 HK','207940 KS']}
ORDER=sum(BATCHES.values(),[])


def iso_dt(value):
    try:
        d=datetime.fromisoformat(value.replace('Z','+00:00'))
        return d if d.tzinfo else d.replace(tzinfo=JST)
    except (ValueError,TypeError,AttributeError):return None


def fetch_receipt(res,snapshot_path=None):
    return {'requested_url':res.requested_url,'final_url':res.final_url,'http_status':res.http_status,
            'method':res.method,'fetched_jst':res.fetched_jst,'sha256':res.snapshot_sha256,
            'response_date':res.response_date,'age_seconds':res.age_seconds,
            'last_modified':res.last_modified,'snapshot_path':snapshot_path}


def suspect_cache(res,run_dt):
    """An old release date is NOT stale-cache evidence; old HTTP cache headers are."""
    if res.age_seconds is not None and res.age_seconds > 172800:return 'AGE_GT_48H'
    stamp=iso_dt(res.response_date)
    if stamp and run_dt.astimezone(timezone.utc)-stamp.astimezone(timezone.utc)>timedelta(days=2):
        return 'HTTP_DATE_GT_48H'
    return None


def title_matches(listing_title,article_title):
    """Require a recognizable official original, not an unrelated redirect or landing page."""
    clean=lambda x:re.sub(r'[^\w\u3400-\u9fff]+','',str(x).lower())
    left,right=clean(listing_title),clean(article_title)
    if not left or not right:return False
    return left in right or right in left or SequenceMatcher(None,left,right).ratio()>=0.50


def scan_index(fetcher,company,index_url,baseline,run_dt,evidence_dir,max_pages=12,max_primary=15):
    """Try one official listing. Complete only on a chain of dated pages reaching baseline."""
    queue=[index_url];seen=set();receipts=[];all_entries={};earliest=None
    found_older=False;unknown_pagination=False;failures=[];stale=[];new_originals=[]
    primary_receipts=[];fetched_any=False;newest=None;order_errors=[];page_date_bounds=[];last_page_oldest=None
    while queue and len(seen)<max_pages and not found_older:
        url=queue.pop(0)
        if url in seen:continue
        seen.add(url)
        try:
            res=fetcher.get(url);fetched_any=True
            if not host_matches(url,res.final_url):
                failures.append({'url':url,'failure':'REDIRECT_OUTSIDE_REGISTERED_COMPANY_DOMAIN','redirect_to':res.final_url})
                break
            snapshot=store_snapshot(evidence_dir,company['ticker'],res)
            rec=fetch_receipt(res,snapshot)
            receipts.append(rec)
            stale_reason=suspect_cache(res,run_dt)
            ordered_items=listing_entries(res.final_url,res.html,preserve_order=True)
            items=listing_entries(res.final_url,res.html)
            on_first_page=(len(seen)==1)
            floor=company.get('known_official_release_floor')
            known_floor_missing=bool(on_first_page and floor and (not items or max(i['listing_date'] for i in items)<floor['date']))
            # A readable shell is not proof that a JS-driven news list was loaded.
            # Force a fresh Chromium fetch if dates are absent or HTTP cache is stale.
            if (not items or stale_reason or known_floor_missing) and res.method=='requests' and hasattr(fetcher,'browser_get'):
                try:
                    br=fetcher.browser_get(url)
                    br_items=listing_entries(br.final_url,br.html)
                    br_stale=suspect_cache(br,run_dt)
                    receipts.append(fetch_receipt(br,store_snapshot(evidence_dir,company['ticker'],br)))
                    browser_has_floor=bool(floor and br_items and max(i['listing_date'] for i in br_items)>=floor['date'])
                    if ((br_items and not known_floor_missing) or browser_has_floor or
                        (stale_reason and not br_stale)):
                        res=br; items=br_items; stale_reason=br_stale
                        ordered_items=listing_entries(br.final_url,br.html,preserve_order=True)
                except Exception as e:
                    failures.append({'url':url,'failure':'CHROMIUM_RETRY_FAILED','detail':str(e)[:120]})
            if stale_reason:stale.append({'url':url,'reason':stale_reason})
            # A fresh HTTP Date does not prove fresh content. Missing a previously
            # verified, newer primary release is a hard stale-index warning.
            if on_first_page and floor and (not items or max(i['listing_date'] for i in items)<floor['date']):
                stale.append({'url':url,'reason':'KNOWN_VERIFIED_ORIGINAL_NOT_IN_LISTING',
                              'floor_date':floor['date'],'floor_url':floor.get('url')})
            # Pinned/out-of-order posts can make a single old item look like a
            # page-boundary. Never stop at an old item on an unordered page.
            dates=[i['listing_date'] for i in ordered_items]
            is_sorted=all(a>=b for a,b in zip(dates,dates[1:]))
            if not is_sorted:
                order_errors.append({'url':url,'failure':'UNSORTED_DATED_LISTING'})
            if dates and last_page_oldest and max(dates)>last_page_oldest:
                order_errors.append({'url':url,'failure':'CROSS_PAGE_DATE_ORDER_INVERSION'})
            if dates:
                page_date_bounds.append({'url':res.final_url,'latest':max(dates),'oldest':min(dates),
                                         'count':len(dates),'descending_order':is_sorted})
                last_page_oldest=min(dates)
            for item in items:all_entries[item['url']]=item
            if items:
                latest_on_page=max(x['listing_date'] for x in items)
                oldest_on_page=min(x['listing_date'] for x in items)
                if newest is None or latest_on_page>newest:newest=latest_on_page
                if earliest is None or oldest_on_page<earliest:earliest=oldest_on_page
                if oldest_on_page<baseline.date().isoformat() and not order_errors:found_older=True
            nexts=next_page_urls(res.final_url,res.html)
            for nxt in nexts:
                if nxt not in seen and nxt not in queue:queue.append(nxt)
            if page_has_unresolved_load_more(res.html,res.final_url,found_older):unknown_pagination=True
            if not items:failures.append({'url':url,'failure':'NO_DATED_ARTICLE_LISTING'})
        except FetchError as err:
            failures.append({'url':url,'failure':str(err),'error_class':'FETCH_ERROR'})
            # If pagination failed, previous pages cannot prove coverage.
            break
    # Exhaustion is never proof of coverage unless we passed the requested baseline date.
    coverage=(found_older and bool(receipts) and not stale and not failures and not order_errors and not unknown_pagination)
    # Full candidate original checking is deliberately independent of coverage QA.
    since=baseline.date().isoformat()
    # Never treat future-dated content as already-published news.
    tomorrow=(run_dt+timedelta(days=1)).date().isoformat()
    if any(v['listing_date']>tomorrow for v in all_entries.values()):
        failures.append({'failure':'FUTURE_DATED_LISTING_ENTRY'})
        coverage=False
    recent=[v for v in all_entries.values() if since<=v['listing_date']<=tomorrow]
    recent=sorted(recent,key=lambda x:(x['listing_date'],x['url']),reverse=True)
    if len(recent)>max_primary:
        failures.append({'failure':'RECENT_ARTICLE_CAP_EXCEEDED','count':len(recent)})
        coverage=False
    for item in recent[:max_primary]:
        try:
            article=fetcher.get(item['url'])
            sr=store_snapshot(evidence_dir,company['ticker'],article)
            pr=fetch_receipt(article,sr)
            primary_receipts.append(pr)
            details=article_details(article.final_url,article.html)
            # Exact official URL origin is part of evidence. Date must be present in original.
            verified=bool(details['body_confirmed'] and host_matches(index_url,article.final_url) and
                          title_matches(item['title'],details['title']) and
                          abs((date.fromisoformat(item['listing_date'])-date.fromisoformat(details['published_date'])).days)<=2)
            new_originals.append({'ticker':company['ticker'],'name':company['name'],
                        'url':item['url'],'listing_title':item['title'],
                        'listing_date':item['listing_date'],'original_title':details['title'],
                        'published_date':details['published_date'],'body_excerpt':details['body'][:600] if verified else None,
                        'original_confirmed':verified,'receipt':pr})
        except (FetchError,ValueError,TypeError) as e:
            new_originals.append({'ticker':company['ticker'],'name':company['name'],
                                  'url':item['url'],'listing_title':item['title'],'listing_date':item['listing_date'],
                                  'original_confirmed':False,'error':str(e)[:240]})
    if any(not x['original_confirmed'] for x in new_originals):coverage=False
    if failures or order_errors:coverage=False
    if len(seen)>=max_pages and not found_older:
        failures.append({'failure':'PAGE_LIMIT_REACHED','pages_checked':len(seen)})
    return {'official_listing_url':index_url,'fetched_any':fetched_any,'page_receipts':receipts,
            'listing_page_urls_checked':[r['final_url'] for r in receipts],
            'latest_publication_date':newest,'oldest_publication_date':earliest,
            'dated_entries_count':len(all_entries),'pagination_complete':bool(coverage),
            'found_baseline_boundary':found_older,'stale_cache':stale,
            'errors':failures+order_errors,'page_date_bounds':page_date_bounds,'candidate_releases':new_originals,'article_receipts':primary_receipts,
            'newer_listing_count':len(recent),'incomplete_load_more':unknown_pagination,'date_order_valid':not order_errors}


def process_company(company,fetcher,now_dt,state,evidence_dir,max_pages=12):
    ticker=company['ticker'];start=datetime.now(JST)
    previous=(state.get('companies') or {}).get(ticker,{})
    prev_success=previous.get('last_verified_success_jst')
    pending=previous.get('pending_baseline_jst')
    baseline=iso_dt(prev_success) or iso_dt(pending) or (now_dt-timedelta(hours=24))
    override=iso_dt(company.get('coverage_recovery_start_jst'))
    recovery=bool(override and override<baseline)
    if recovery:baseline=override
    result={'ticker':ticker,'company_name':company['name'],'batch_id':company['batch_id'],
            'audit_date_jst':now_dt.date().isoformat(),'official_listing_url':None,
            'official_urls_configured':company['official_indexes'],
            'homepage_visit_status':'未訪問','attempt_start_jst':start.isoformat(),
            'attempt_end_jst':None,'tool_evidence_ref':None,
            'previous_success_jst':prev_success,
            'comparison_period':{'start_jst':baseline.isoformat(), 'end_jst':now_dt.isoformat(),
                                 'type':'coverage_gap_recovery' if recovery else ('last_success' if prev_success else ('unresolved_baseline' if pending else 'provisional_24h'))},
            'status':'未確認','reason':'未実査','latest_publication_date':None,
            'oldest_publication_date':None,'listing_page_urls_checked':[],
            'pagination_complete':False,'alternative_attempts':[],
            'primary_releases':[],'new_success_jst':None,'stale_cache_status':None,
            'source_classification':'UNVERIFIED','index_attempts':[]}
    try:
        candidates=[]
        for index_num,url in enumerate(company['official_indexes'][:3]):
            company_with_floor=dict(company)
            current_floor=company.get('known_official_release_floor')
            old_floor=previous.get('latest_verified_original')
            if old_floor and (not current_floor or old_floor.get('date','')>current_floor.get('date','')):
                company_with_floor['known_official_release_floor']=old_floor
            scan=scan_index(fetcher,company_with_floor,url,baseline,now_dt,evidence_dir,max_pages=max_pages)
            candidates.append(scan)
            result['index_attempts'].append(scan)
            if scan['fetched_any']:result['homepage_visit_status']='成功'
            elif result['homepage_visit_status']!='成功':result['homepage_visit_status']='失敗'
            if index_num>0:
                result['alternative_attempts'].append({'url':url,'method':'direct_http_or_playwright',
                                      'fetched_any':scan['fetched_any'],
                                      'pagination_complete':scan['pagination_complete'],
                                      'errors':scan['errors']})
            if scan['pagination_complete']:break
        # Prefer full coverage over most recent but incomplete, never treat '0 articles' as no release.
        chosen=next((s for s in candidates if s['pagination_complete']),None)
        if not chosen:
            chosen=max(candidates,key=lambda s:(int(s['fetched_any']),len(s['page_receipts']),s['dated_entries_count'])) if candidates else None
        if chosen:
            result['official_listing_url']=chosen['official_listing_url']
            for k in ('latest_publication_date','oldest_publication_date','listing_page_urls_checked','pagination_complete'):
                result[k]=chosen[k]
            if chosen['page_receipts']:
                result['tool_evidence_ref']=chosen['page_receipts'][0]['sha256']
            # Independently retain all confirmed originals, including from non-selected listing sources.
            all_releases={}
            for scan in candidates:
                for r in scan['candidate_releases']:
                    if r['url'] not in all_releases or (r['original_confirmed'] and not all_releases[r['url']]['original_confirmed']):
                        all_releases[r['url']]=r
            result['primary_releases']=list(all_releases.values())
            newest_alt=max((s['latest_publication_date'] for s in candidates if s['latest_publication_date']),default=None)
            # If one official index has much newer releases, mark older candidates suspect rather than asserting site outage.
            selected_stale=bool(chosen['stale_cache'])
            divergent=bool(chosen['latest_publication_date'] and newest_alt and
                (date.fromisoformat(newest_alt)-date.fromisoformat(chosen['latest_publication_date'])).days>=5)
            floor=company.get('known_official_release_floor')
            state_floor=previous.get('latest_verified_original')
            if state_floor and (not floor or state_floor.get('date','')>floor.get('date','')):
                floor=state_floor
            floor_missed=bool(floor and chosen['latest_publication_date'] and
                chosen['latest_publication_date']<floor['date'])
            if selected_stale:result['stale_cache_status']='STALE_CACHE'
            elif floor_missed:
                result['stale_cache_status']='STALE_CACHE_SUSPECTED_KNOWN_RELEASE_MISSING'
                result['known_release_floor_evidence']=floor
            elif divergent:result['stale_cache_status']='STALE_CACHE_SUSPECTED_SOURCE_DIVERGENCE'
            if chosen['pagination_complete'] and not result['stale_cache_status']:
                result['status']='あり' if chosen['newer_listing_count']>0 else 'なし'
                result['source_classification']='PERIOD_VERIFIED'
                result['new_success_jst']=now_dt.isoformat()
                result['reason']='COMPLETE_DATED_LISTING_AND_ORIGINALS' if result['status']=='あり' else 'COMPLETE_DATED_LISTING_NO_NEW_RELEASES'
            else:
                result['reason']=('STALE_CACHE_OR_SOURCE_DIVERGENCE' if result['stale_cache_status'] else
                                  'INCOMPLETE_PAGINATION_OR_LISTING_OR_ORIGINAL')
                result['source_classification']='UNVERIFIED'
        else:
            result['reason']='NO_OFFICIAL_URL_CONFIGURED'
    except Exception as e:
        LOG.exception('Internal exception for %s',ticker)
        result['reason']='INTERNAL_ERROR:'+type(e).__name__+':'+str(e)[:160]
    finally:
        result['attempt_end_jst']=datetime.now(JST).isoformat()
    return result


def validate_report(registry,results,expected_order=None):
    errors=[]
    expected=[c['ticker'] for c in registry['companies']]
    order=ORDER if expected_order is None else list(expected_order)
    if expected!=order:errors.append('REGISTRY_ORDER_MISMATCH')
    if [e['ticker'] for e in results]!=order:errors.append('RESULT_ORDER_MISMATCH')
    if len(set(x['ticker'] for x in results))!=len(order):errors.append('DUPLICATE_OR_MISSING_TICKER')
    for e in results:
        if e['status'] not in ('あり','なし','未確認'):errors.append(e['ticker']+':INVALID_STATUS')
        if e['status'] in ('あり','なし'):
            if not (e['pagination_complete'] and e['listing_page_urls_checked'] and e['latest_publication_date'] and
                    e['oldest_publication_date'] and e['new_success_jst'] and not e['stale_cache_status']):
                errors.append(e['ticker']+':SUCCESS_WITHOUT_COVERAGE_EVIDENCE')
        if e['status']=='あり' and not any(x['original_confirmed'] for x in e['primary_releases']):
            errors.append(e['ticker']+':SUCCESS_WITHOUT_PRIMARY_ORIGINAL')
        if e['homepage_visit_status']=='未訪問' and e['tool_evidence_ref']:
            errors.append(e['ticker']+':UNVISITED_WITH_RECEIPT')
    return errors


def render_report(now_dt,results,errors,engine):
    direct=sum(x['homepage_visit_status']!='未訪問' for x in results)
    passed=sum(x['status']!='未確認' for x in results)
    total=len(results)
    unconfirmed=total-passed
    originals=[p for x in results for p in x['primary_releases'] if p['original_confirmed']]
    originals=list({p['url']:p for p in originals}.values())
    subject=f'製薬公式監視 {now_dt.date().isoformat()}【暫定・未確認{unconfirmed}社】' if (unconfirmed or errors) else f'製薬公式監視 {now_dt.date().isoformat()}【{total}社監査】'
    lines=[f'# {subject}','',f'- レポート日付(JST): {now_dt.isoformat()}',
        f'- 対象{total}社 / 直接取得試行記録 {direct}社 / 期間網羅確認 {passed}社 / 未確認 {unconfirmed}社',
        f'- 一次原文で確認した発表: {len(originals)}件 / 新規、既報、初回観測を別々に表示',
        f'- 収集エンジン: {engine} / 構造QAコード: 実行済み（エラー{len(errors)}件） / 期間網羅QA: {"合格" if passed==total and not errors else "未達"}',
        f'- キャッシュ疑い: {sum(bool(x["stale_cache_status"]) for x in results)}社',
        '- 注意: 未確認は「新規発表なし」を意味しない。GitHub上の直接HTTP収集はweb.openのクロールキャッシュとは別。',
        '', '## 一次原文が確認できた発表（一覧QA不合格でも保持）']
    if originals:
        for p in sorted(originals,key=lambda v:(v['published_date'] or '',v['ticker']),reverse=True):
            lines.append(f'- {p["ticker"]} | {p.get("new_status","初回")} | {p["published_date"]} | {p["original_title"]} | {p["url"]}')
            if p.get('body_excerpt'):lines.append('  原文要旨: '+p['body_excerpt'][:280])
    else:lines.append('- なし（未確認企業の不在証明ではない）')
    lines+=['',f'## {total}社対応表（固定順）','', '|Ticker|判定|一覧取得|最新記事|ページ網羅|原因|','|---|---|---|---|---|---|']
    for e in results:
        reason=e['reason'].replace('|','/')[:90]
        lines.append(f'|{e["ticker"]}|{e["status"]}|{e["homepage_visit_status"]}|{e["latest_publication_date"] or "null"}|{e["pagination_complete"]}|{reason}|')
    lines+=['','## QAエラー']
    lines+=['- '+s for s in errors] if errors else ['- 構造上のエラーなし。期間網羅の達成とは別。']
    return subject,'\n'.join(lines)+'\n', {'total':total,'direct_attempts':direct,'period_verified':passed,'unconfirmed':unconfirmed,
        'primary_originals':len(originals),'qa_errors':len(errors)}


def transient_failure(e):
    if e.get('status')!='未確認' or e.get('stale_cache_status'):return False
    failures=' '.join(str(x.get('failure','')) for a in e.get('index_attempts',[]) for x in a.get('errors',[]))
    # No repeated request against explicit denial, throttling or missing pages.
    if re.search(r'HTTP_(?:401|403|404|429)\b',failures):return False
    return bool(re.search(r'HTTP_5\d\d|Timeout|ConnectionError|ERR_CONNECTION_RESET|ERR_TIMED_OUT',failures,re.I))

def merge_retry(first,second):
    if first['ticker']!=second['ticker'] or first['comparison_period']!=second['comparison_period']:
        raise ValueError('retry scope mismatch')
    chosen=second if second['status']!='未確認' else first
    result=dict(chosen)
    result['retry_observation']={'first_reason':first['reason'],'second_reason':second['reason'],'second_status':second['status'],'attempted':True}
    result['index_attempts']=first['index_attempts']+second['index_attempts']
    result['alternative_attempts']=first['alternative_attempts']+second['alternative_attempts']
    releases={}
    for p in first['primary_releases']+second['primary_releases']:
        if p['url'] not in releases or (p.get('original_confirmed') and not releases[p['url']].get('original_confirmed')):
            releases[p['url']]=p
    result['primary_releases']=list(releases.values())
    return result

def collect(registry,state,asof=None,fetcher=None,evidence_dir='data/evidence',workers=5,max_pages=12,expected_order=None,retry_transient=False):
    """Execute all 46 direct collections, always preserve the fixed batch order."""
    now_dt=asof or datetime.now(JST)
    f=fetcher or LiveFetcher()
    companies=registry['companies']
    order=ORDER if expected_order is None else list(expected_order)
    if len(set(order))!=len(order) or [x['ticker'] for x in companies]!=order:raise ValueError('Wrong company registry')
    # Checkpoint each completed company before waiting for the rest. These files
    # are included in the evidence artifact even if the later audit step fails.
    checkpoint=Path(evidence_dir)/('checkpoints_'+now_dt.strftime('%Y%m%dT%H%M%S%f'))
    checkpoint.mkdir(parents=True,exist_ok=True)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        tasks={pool.submit(process_company,c,f,now_dt,state,evidence_dir,max_pages):c for c in companies}
        completed={}
        for fut in as_completed(tasks):
            c=tasks[fut];ticker=c['ticker']
            try:
                completed[ticker]=fut.result()
            except Exception as exc:
                LOG.exception('Unexpected worker failure: %s',ticker)
                previous=(state.get('companies') or {}).get(ticker,{})
                prev=previous.get('last_verified_success_jst')
                pending=previous.get('pending_baseline_jst')
                baseline=iso_dt(prev) or iso_dt(pending) or (now_dt-timedelta(hours=24))
                completed[ticker]={'ticker':ticker,'company_name':c['name'],'batch_id':c['batch_id'],
                    'audit_date_jst':now_dt.date().isoformat(),'official_listing_url':None,
                    'official_urls_configured':c['official_indexes'],'homepage_visit_status':'未訪問',
                    'attempt_start_jst':None,'attempt_end_jst':None,'tool_evidence_ref':None,
                    'comparison_period':{'start_jst':baseline.isoformat(),'end_jst':now_dt.isoformat(),
                        'type':'last_success' if prev else ('unresolved_baseline' if pending else 'provisional_24h')},'previous_success_jst':prev,
                    'status':'未確認','reason':'WORKER_EXCEPTION_NO_VERIFIABLE_RECEIPT:'+type(exc).__name__,
                    'latest_publication_date':None,'oldest_publication_date':None,'listing_page_urls_checked':[],
                    'pagination_complete':False,'alternative_attempts':[],'primary_releases':[],
                    'new_success_jst':None,'stale_cache_status':None,'source_classification':'UNVERIFIED',
                    'index_attempts':[]}
            try:
                path=checkpoint/(ticker.replace(' ','_')+'.json')
                tmp=path.with_suffix('.tmp')
                tmp.write_text(json.dumps(completed[ticker],ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
                tmp.replace(path)
            except OSError:
                LOG.exception('Checkpoint write failed for %s; retaining in memory',ticker)
            LOG.info('%s: %s / %s',ticker,completed[ticker]['status'],completed[ticker]['reason'])
    if retry_transient:
        # Bound retries to 4 companies; never change the comparison interval.
        targets=[c for c in companies if transient_failure(completed[c['ticker']])][:4]
        for c in targets:
            ticker=c['ticker']
            try:
                retry=process_company(c,f,now_dt,state,Path(evidence_dir)/'retry',max_pages)
                completed[ticker]=merge_retry(completed[ticker],retry)
                (checkpoint/(ticker.replace(' ','_')+'.json')).write_text(json.dumps(completed[ticker],ensure_ascii=False,indent=2),encoding='utf-8')
            except Exception as exc:
                LOG.warning('Bounded retry failed for %s: %s',ticker,type(exc).__name__)
    results=[completed[t] for t in order]
    # Persist verified original URLs even when a company's index-coverage QA fails.
    # On the first-ever baseline, 'first observed' is not equivalent to newly published.
    for e in results:
        st=state.setdefault('companies',{}).setdefault(e['ticker'],{})
        seen=set(st.get('seen_verified_urls',[]))
        for item in e['primary_releases']:
            if not item.get('original_confirmed'):continue
            if item['url'] in seen:item['new_status']='KNOWN_PREVIOUSLY_CONFIRMED'
            elif e['previous_success_jst']:item['new_status']='UNSEEN_IN_DATE_WINDOW_TIME_UNCERTAIN'
            else:item['new_status']='FIRST_OBSERVED_NOT_PROVEN_NEW'
            seen.add(item['url'])
            prev_floor=st.get('latest_verified_original')
            if not prev_floor or (item.get('published_date') or '')>(prev_floor.get('date') or ''):
                st['latest_verified_original']={'date':item['published_date'],'url':item['url'],
                                               'purpose':'verified original retained for stale-index detection'}
        if e['status']=='あり' and not any(p.get('new_status') in
            ('UNSEEN_IN_DATE_WINDOW_TIME_UNCERTAIN','FIRST_OBSERVED_NOT_PROVEN_NEW')
            for p in e['primary_releases'] if p.get('original_confirmed')):
            e['status']='なし'
            e['reason']='COMPLETE_LISTING_ALL_RELEASES_ALREADY_REPORTED'
        st['seen_verified_urls']=sorted(seen)[-500:]
        if e['new_success_jst'] and e['status'] in ('あり','なし'):
            st['last_verified_success_jst']=e['new_success_jst']
    errors=validate_report(registry,results,expected_order=order)
    return results,errors,state
