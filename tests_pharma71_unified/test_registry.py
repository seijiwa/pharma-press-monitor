import json
from pathlib import Path
from datetime import datetime
from pharma46.engine import collect,render_report,ORDER
from pharma46.fetch import JST
from pharma71_unified.registry import load_registry,ticker_order
from pharma71_unified.cli import verified_feeds
from tests_pharma46.test_end_to_end import SyntheticCompanyFetcher,NOW

def test_exact_71_and_core_order():
    r=load_registry();order=ticker_order(r)
    assert len(order)==71 and order[:46]==ORDER and 'ROP' in order and 'ROG' not in order
    assert {c['name'] for c in r['companies']}.__len__()==71
    assert 'https://investor.lilly.com/'==r['companies'][0]['official_indexes'][0]

def test_all_71_fail_closed(tmp_path):
    r=load_registry();order=ticker_order(r)
    e,err,_=collect(r,{'companies':{}},asof=NOW,fetcher=SyntheticCompanyFetcher(r,all_fail=True),
        evidence_dir=tmp_path/'evidence',workers=3,expected_order=order)
    assert not err and [x['ticker'] for x in e]==order
    assert all(x['status']=='未確認' for x in e)
    _,_,s=render_report(NOW,e,err,'synthetic')
    assert s['total']==71 and s['period_verified']==0 and s['unconfirmed']==71
    verified_feeds(e,tmp_path/'feeds')
    assert len(list((tmp_path/'feeds').glob('*.xml')))==72
    assert '<item>' not in (tmp_path/'feeds/all.xml').read_text()
