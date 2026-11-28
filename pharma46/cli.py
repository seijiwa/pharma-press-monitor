"""One command runs all 46, writes A/B/C, merged audit, MD report and evidence."""
import argparse,json,logging,os,sys
from datetime import datetime
from pathlib import Path
from .engine import JST,collect,render_report,BATCHES,ORDER


def save_json(path,obj):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    pending=path.with_suffix(path.suffix+'.tmp')
    pending.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    pending.replace(path)


def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--date',help='JST date for fixtures/manual replay; uses real clock for capture')
    ap.add_argument('--workers',type=int,default=4)
    ap.add_argument('--max-pages',type=int,default=12)
    ap.add_argument('--assert-quality',action='store_true')
    args=ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    now=datetime.now(JST)
    day=now.date().isoformat()
    if args.date and args.date != day:
        ap.error('live collection only supports the current JST date')
    if args.assert_quality:
        audit=Path('data')/f'pharma_monitor_{day}_audit.json'
        if not audit.exists():print('NO_AUDIT_FILE');return 2
        d=json.loads(audit.read_text(encoding='utf-8'))
        stats=d['summary'];delivery=d.get('delivery',{})
        print(json.dumps({'summary':stats,'delivery_status':delivery.get('status')},ensure_ascii=False))
        return 0 if stats['period_verified']==46 and delivery.get('recipient_inbox_verified') is True else 2
    registry=json.loads(Path('pharma46/sources.json').read_text(encoding='utf-8'))
    if [x['ticker'] for x in registry['companies']]!=ORDER:raise RuntimeError('REGISTRY_FAILED')
    state_file=Path('data/pharma46_state.json')
    state=json.loads(state_file.read_text(encoding='utf-8')) if state_file.exists() else {'companies':{}}
    data_dir=Path('data');data_dir.mkdir(exist_ok=True)
    # Recover unresolved baseline from actual prior 46 audits; no coverage credit.
    from .engine import iso_dt
    for old_audit in sorted(data_dir.glob('pharma_monitor_*_audit.json'))[-30:]:
        try:
            prior=json.loads(old_audit.read_text(encoding='utf-8'))
            if prior.get('expected_tickers')!=ORDER or not str(prior.get('run_id','')).isdigit():continue
            if [e.get('ticker') for e in prior['entries']]!=ORDER:continue
            for e in prior['entries']:
                if e.get('status')!='未確認':continue
                st=state.setdefault('companies',{}).setdefault(e['ticker'],{})
                if st.get('last_verified_success_jst'):continue
                start=iso_dt(e['comparison_period']['start_jst'])
                pending=iso_dt(st.get('pending_baseline_jst'))
                if start and start.tzinfo and start<=now and (not pending or start<pending):
                    st['pending_baseline_jst']=start.isoformat()
        except (OSError,ValueError,TypeError,KeyError):continue
    evidence_dir=data_dir/'evidence'/day
    results,errors,new_state=collect(registry,state,asof=now,evidence_dir=evidence_dir,
                                     workers=args.workers,max_pages=args.max_pages,retry_transient=True)
    subject,body,summary=render_report(now,results,errors,'GitHub Actions direct HTTP/Playwright')
    for batch,tickers in BATCHES.items():
        entries=[e for e in results if e['batch_id']==batch]
        assert [e['ticker'] for e in entries]==tickers
        batch_data={'batch_id':batch,'audit_date_jst':day,'expected_tickers':tickers,
                    'entries':entries,'qa_errors':[x for x in errors if x.startswith(batch+':')]}
        save_json(data_dir/f'pharma_monitor_{day}_batch_{batch}.json',batch_data)
    report_file=data_dir/f'pharma_monitor_{day}_report.md'
    report_file.write_text(body,encoding='utf-8')
    audit_path=data_dir/f'pharma_monitor_{day}_audit.json'
    audit={'audit_date_jst':day,'start_jst':now.isoformat(),'run_id':os.getenv('GITHUB_RUN_ID'),
           'completed_jst':datetime.now(JST).isoformat(),'source_scope':'pharma46-independent',
           'expected_tickers':ORDER,'entries':results,'summary':summary,'qa_errors':errors,
           'engine_status':'EXECUTED','is_live_direct_http':True,'qa_code_executed':True,
           'qa_pass':bool(summary['period_verified']==46 and not errors),
           'email_subject':subject,'delivery':{'status':'NOT_REQUESTED'}}
    if not errors:
        originals=new_state.setdefault('verified_originals',{})
        for entry in results:
            for item in entry['primary_releases']:
                if item['original_confirmed']:
                    originals.setdefault(item['url'], {
                        'ticker':item['ticker'],'date':item['published_date'],
                        'title':item['original_title'],'observed_jst':audit['completed_jst'],
                    })
    save_json(audit_path,audit)
    save_json(state_file,new_state)
    print(json.dumps({'summary':summary,'email':audit['delivery'],'output':str(audit_path)},ensure_ascii=False))
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'],'a',encoding='utf-8') as f:
            f.write(f'## Pharma46 {day}\n\n'+body.split('## 一次原文')[0])
    return 0

if __name__=='__main__':sys.exit(main())
