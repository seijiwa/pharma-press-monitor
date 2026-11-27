import json,pytest
from pharma71_unified.ledger import persist
from pharma71_unified.comparison_receipt import receipt

def test_current_audit_and_ledger_match(tmp_path):
    a={'run_id':'external-test','start_jst':'2026-11-27T10:00:00+09:00','execution_environment':'test',
       'summary':{'total':71,'period_verified':0},'qa_pass':False,
       'entries':[{'ticker':str(i),'status':'未確認','reason':'test','comparison_period':{},'primary_releases':[],
                   'index_attempts':[]} for i in range(71)]}
    (tmp_path/'audit.json').write_text(json.dumps(a))
    persist(tmp_path/'audit_ledger.sqlite3',a)
    r=receipt(tmp_path,'external-test')
    assert len(r['entries'])==71 and not r['strict_qa_pass']
    with pytest.raises(ValueError):receipt(tmp_path,'different-run')
    (tmp_path/'audit.json').write_text(json.dumps(dict(a,qa_pass=True)))
    with pytest.raises(ValueError):receipt(tmp_path,'external-test')
