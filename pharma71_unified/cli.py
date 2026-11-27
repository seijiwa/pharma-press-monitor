"""Staging unified audit; the same original receipts feed JSON, Markdown and RSS.
No email or public Pages changes in this first test."""
import argparse,json,os,sys
from pathlib import Path
from datetime import datetime
from xml.etree.ElementTree import Element,SubElement,ElementTree
from pharma46.engine import JST,collect,render_report,validate_report
from pharma46.cli import save_json
from .registry import load_registry,ticker_order,HISTORICAL
from .api_observations import supplement

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
    p.add_argument('--workers',type=int,default=8)
    p.add_argument('--max-pages',type=int,default=12)
    args=p.parse_args(argv)
    registry=load_registry()
    order=ticker_order(registry)
    now=datetime.now(JST)
    root=Path('data/pharma71_unified')
    root.mkdir(parents=True,exist_ok=True)
    state_path=root/'state.json'
    state=json.loads(state_path.read_text()) if state_path.exists() else {'companies':{}}
    # Separate parent-only historical rows are explicitly unconfirmed; never
    # report a parent's release as a publication by a former independent entity.
    entries,errors,new_state=collect(registry,state,asof=now,
        evidence_dir=root/'evidence'/now.strftime('%Y-%m-%dT%H%M%S'),
        workers=args.workers,max_pages=args.max_pages,expected_order=order)
    for e in entries:
        supplement(e,now,root/'evidence'/now.strftime('%Y-%m-%dT%H%M%S'))
        if e['ticker'] in HISTORICAL:
            e.update(status='未確認',reason='HISTORICAL_PARENT_SCOPE_NOT_INDEPENDENT',new_success_jst=None,
                     primary_releases=[],source_classification='PARENT_ONLY_UNVERIFIED')
            new_state['companies'].pop(e['ticker'],None)
    errors=validate_report(registry,entries,expected_order=order)
    subject,body,summary=render_report(now,entries,errors,'GitHub Pharma71 unified staging')
    audit={'audit_date_jst':now.date().isoformat(),'start_jst':now.isoformat(),
           'run_id':os.getenv('GITHUB_RUN_ID'),'expected_tickers':order,'entries':entries,
           'summary':summary,'qa_errors':errors,'qa_pass':summary['period_verified']==71 and not errors,
           'delivery':{'status':'NOT_REQUESTED_STAGING'},'subject':subject}
    save_json(root/'audit.json',audit)
    save_json(root/(now.strftime('%Y-%m-%dT%H%M%S')+'_audit.json'),audit)
    save_json(state_path,new_state)
    (root/'report.md').write_text(body,encoding='utf-8')
    verified_feeds(entries,root/'feeds')
    print(json.dumps(summary,ensure_ascii=False))
    return 0 if not errors else 2

if __name__=='__main__':sys.exit(main())
