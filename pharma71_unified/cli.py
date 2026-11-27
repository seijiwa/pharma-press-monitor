"""Staging unified audit; the same original receipts feed JSON, Markdown and RSS.
No email or public Pages changes in this first test."""
import argparse,json,os,sys
from copy import deepcopy
from pathlib import Path
from datetime import datetime
from xml.etree.ElementTree import Element,SubElement,ElementTree
from pharma46.engine import JST,collect,render_report,validate_report
from pharma46.cli import save_json
from .registry import load_registry,ticker_order,HISTORICAL
from .api_observations import supplement
from .official_fallback import collect_fallback,update_original_state

def verified_feeds(entries,folder):
    folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
    def write(path,title,rows):
        root=Element('rss',version='2.0')
        ch=SubElement(root,'channel')
        SubElement(ch,'title').text=title
        SubElement(ch,'link').text='https://github.com/seijiwa/pharma-press-monitor'
        SubElement(ch,'description').text='Directly verified original releases only; incomplete coverage is not proof of absence.'
        unique={}
        for p in rows:
            if p.get('original_confirmed') and p.get('url'):unique[p['url']]=p
        for p in sorted(unique.values(),key=lambda x:x.get('published_date') or '',reverse=True):
            item=SubElement(ch,'item')
            SubElement(item,'title').text=p['original_title']
            SubElement(item,'link').text=p['url']
            SubElement(item,'guid',isPermaLink='true').text=p['url']
            SubElement(item,'description').text=(p.get('published_date') or '')+' | '+(p.get('new_status') or '')+' | '+(p.get('body_excerpt') or '')[:280]
        ElementTree(root).write(path,encoding='utf-8',xml_declaration=True)
    originals=[]
    for e in entries:
        rows=e['primary_releases'];originals.extend(rows)
        write(folder/(e['ticker'].replace(' ','_')+'.xml'),e['company_name'],rows)
    write(folder/'all.xml','Pharma71 verified originals',originals)

def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument('--workers',type=int,default=3)
    p.add_argument('--max-pages',type=int,default=12)
    args=p.parse_args(argv)
    registry=load_registry()
    order=ticker_order(registry)
    now=datetime.now(JST)
    root=Path('data/pharma71_unified')
    root.mkdir(parents=True,exist_ok=True)
    state_path=root/'state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {'companies':{}}
    prior_state=deepcopy(state)
    by_ticker={x['ticker']:x for x in registry['companies']}
    # Separate parent-only historical rows are explicitly unconfirmed; never
    # report a parent's release as a publication by a former independent entity.
    entries,errors,new_state=collect(registry,state,asof=now,
        evidence_dir=root/'evidence'/now.strftime('%Y-%m-%dT%H%M%S'),
        workers=args.workers,max_pages=args.max_pages,expected_order=order)
    for e in entries:
        supplement(e,now,root/'evidence'/now.strftime('%Y-%m-%dT%H%M%S'),state=new_state)
        if e['ticker'] not in HISTORICAL:
            collect_fallback(e,by_ticker[e['ticker']],now,root/'evidence'/now.strftime('%Y-%m-%dT%H%M%S'),state=prior_state)
        if e.get('source_classification')=='PERIOD_VERIFIED_OFFICIAL_API':
            new_state['companies'].setdefault(e['ticker'],{})['last_verified_success_jst']=e['new_success_jst']
        if e['ticker'] in HISTORICAL:
            e.update(status='未確認',reason='HISTORICAL_PARENT_SCOPE_NOT_INDEPENDENT',new_success_jst=None,
                     primary_releases=[],source_classification='PARENT_ONLY_UNVERIFIED')
            new_state['companies'].pop(e['ticker'],None)
    update_original_state(entries,new_state,prior_state)
    errors=validate_report(registry,entries,expected_order=order)
    subject,body,summary=render_report(now,entries,errors,'GitHub Pharma71 unified staging')
    audit={'audit_date_jst':now.date().isoformat(),'start_jst':now.isoformat(),
           'run_id':os.getenv('GITHUB_RUN_ID'),'expected_tickers':order,'entries':entries,
           'summary':summary,'qa_errors':errors,'qa_pass':summary['period_verified']==71 and not errors,
           'delivery':{'status':'NOT_REQUESTED_STAGING'},'subject':subject}
    # Separate strict 71-row coverage from successor-only monitoring scope.
    # These diagnostics never change the existing final QA gate.
    unresolved=[{'ticker':e['ticker'],'company':e['company_name'],'reason':e['reason'],
                 'source_errors':[{'url':a['official_listing_url'],'errors':a['errors'],
                                   'unresolved_load_more':a['incomplete_load_more']}
                                  for a in e['index_attempts']]} for e in entries if e['status']=='未確認']
    audit['migration_readiness']={'strict_period_qa':audit['qa_pass'],
        'independent_scope_total':len(order)-len(HISTORICAL),
        'independent_scope_verified':sum(e['status']!='未確認' and e['ticker'] not in HISTORICAL for e in entries),
        'historical_scope_pending_review':sorted(HISTORICAL),
        'unresolved':unresolved,'production_delivery_verified':False}
    save_json(root/'audit.json',audit)
    save_json(root/(now.strftime('%Y-%m-%dT%H%M%S')+'_audit.json'),audit)
    save_json(state_path,new_state)
    (root/'report.md').write_text(body,encoding='utf-8')
    # Persist a bounded rolling original ledger. Failed or empty runs cannot
    # erase verified entries from prior runs; keep latest 500 per company.
    history_path=root/'verified_original_history.json'
    history=json.loads(history_path.read_text()) if history_path.exists() else {}
    for e in entries:
        ledger={x['url']:x for x in history.get(e['ticker'],[]) if x.get('original_confirmed') and x.get('url')}
        for p in e['primary_releases']:
            if p.get('original_confirmed') and p.get('url'):ledger.setdefault(p['url'],p)
        history[e['ticker']]=sorted(ledger.values(),key=lambda x:x.get('published_date') or '',reverse=True)[:500]
    save_json(history_path,history)
    verified_feeds([dict(e,primary_releases=history[e['ticker']]) for e in entries],root/'feeds')
    print(json.dumps(summary,ensure_ascii=False))
    return 0 if not errors else 2

if __name__=='__main__':sys.exit(main())
