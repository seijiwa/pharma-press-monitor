import sqlite3,pytest
from pharma71_unified.regulatory import parse_tickers,parse_submissions
from pharma71_unified.ledger import persist
def test_sec_filing_scope_and_identity():
    d={'cik':123,'tickers':['TEST'],'filings':{'recent':{'accessionNumber':['0000000123-26-000001','0000000123-26-000002'],'filingDate':['2026-11-26','2026-11-20'],'form':['8-K','10-Q'],'primaryDocument':['report.htm','old.htm']}}}
    rows,boundary,count=parse_submissions(d,'TEST',123,'2026-11-25','2026-11-27')
    assert count==2 and boundary and len(rows)==1 and not rows[0]['original_confirmed']
    with pytest.raises(ValueError):parse_submissions(d,'WRONG',123,'2026-11-25','2026-11-27')
def test_ambiguous_ticker_rejected():
    with pytest.raises(ValueError):parse_tickers({'0':{'ticker':'T','cik_str':1},'1':{'ticker':'T','cik_str':2}})
def test_ledger_idempotent_retains_original(tmp_path):
    path=tmp_path/'ledger.sqlite3'
    a={'run_id':'1','start_jst':'2026-11-27T10:00:00+09:00','entries':[{'ticker':'T','primary_releases':[{'url':'https://example.com/a','original_confirmed':True}]}]}
    persist(path,a);persist(path,a)
    b={'run_id':'2','start_jst':'2026-11-27T10:20:00+09:00','entries':[{'ticker':'T','primary_releases':[]}]}
    persist(path,b)
    with sqlite3.connect(path) as con:
        assert con.execute('SELECT count(*) FROM runs').fetchone()[0]==2
        assert con.execute('SELECT count(*) FROM originals').fetchone()[0]==1
    with pytest.raises(ValueError):persist(path,dict(a,entries=[]))
