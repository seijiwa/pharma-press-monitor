"""Compact comparison receipt. This is diagnostics, not transferable raw evidence."""
import hashlib,json,sqlite3
from pathlib import Path
from .sec_exhibits import summarize

def receipt(root,expected_run_id):
    root=Path(root)
    raw=(root/'audit.json').read_bytes()
    audit=json.loads(raw)
    if audit['run_id']!=expected_run_id:raise ValueError('Stale audit')
    entries=audit['entries']
    if len(entries)!=71 or len({e['ticker'] for e in entries})!=71:raise ValueError('Invalid universe')
    with sqlite3.connect(root/'audit_ledger.sqlite3') as con:
        row=con.execute('SELECT payload FROM runs WHERE run_key=?',(expected_run_id,)).fetchone()
    if not row or json.loads(row[0])!=audit:raise ValueError('Ledger missing current audit')
    return {'run_id':expected_run_id,'environment':audit['execution_environment'],
            'start_jst':audit['start_jst'],'audit_sha256':hashlib.sha256(raw).hexdigest(),
            'summary':audit['summary'],'strict_qa_pass':audit['qa_pass'],
            'regulatory_status':audit.get('regulatory_observations',{}).get('status'),
            'regulatory_summary':summarize(audit.get('regulatory_observations',{})),
            'integrated_summary':audit.get('integrated_monitoring',{}).get('summary',{}),
            'tdnet_summary':audit.get('regulatory_observations',{}).get('tdnet',{}).get('summary',{}),
            'regulatory_entries':[{'ticker':e['ticker'],'status':e['status'],'sec_ticker':e.get('sec_ticker'),'issuer_identity_verified':e.get('issuer_identity_verified',False),'filings':len(e.get('filings',[])),
                'verified_exhibits':sum(bool(x.get('original_confirmed')) for d in e.get('exhibit_results',[]) for x in d.get('exhibits',[]))} for e in audit.get('regulatory_observations',{}).get('entries',[])],
            'integrated_rows':audit.get('integrated_monitoring',{}).get('rows',[]),
            'entries':[{'ticker':e['ticker'],'status':e['status'],'reason':e['reason'],
                        'period':e['comparison_period'],'receipt_sha256':e.get('tool_evidence_ref'),
                        'originals':sum(bool(p.get('original_confirmed')) for p in e['primary_releases']),
                        'http403':any('HTTP_403' in err.get('failure','') for a in e['index_attempts'] for err in a['errors'])}
                        for e in entries]}
def emit(root,run_id):
    r=receipt(root,run_id)
    entries=r.pop('entries')
    regulatory=r.pop('regulatory_entries')
    integrated=r.pop('integrated_rows')
    print('PHARMA71_RUN '+json.dumps(r,ensure_ascii=False,separators=(',',':')),flush=True)
    for entry in regulatory:
        print('PHARMA71_SEC '+json.dumps(dict(entry,run_id=run_id),ensure_ascii=False,separators=(',',':')),flush=True)
    for entry in integrated:
        print('PHARMA71_SCOPE '+json.dumps(dict(entry,run_id=run_id),ensure_ascii=False,separators=(',',':')),flush=True)
    for entry in entries:
        print('PHARMA71_COMPANY '+json.dumps(dict(entry,run_id=run_id),ensure_ascii=False,separators=(',',':')),flush=True)
