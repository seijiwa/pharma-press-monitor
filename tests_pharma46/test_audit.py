import json
from pathlib import Path
from datetime import datetime,timezone,timedelta
import pytest
from pharma46.fetch import FetchResult,FetchError,JST
from pharma46.engine import ORDER,BATCHES,process_company,scan_index,suspect_cache,validate_report
from pharma46.extract import parse_date,listing_entries,next_page_urls,article_details
from pharma46.delivery import send_report

NOW=datetime(2026,11,25,8,0,tzinfo=JST)
INDEX='https://test.example.com/press-releases'
URL_CURRENT='https://test.example.com/press-releases/2026/11/25/first-trial-release'
URL_PAST='https://test.example.com/press-releases/2026/11/23/older-trial-release'
PAGE1=f'''<html><body><main><h1>Press Releases</h1>
<article><time datetime="2026-11-25">November 25, 2026</time><a href="{URL_CURRENT}">Company provides important Phase 3 clinical trial update</a></article>
<a rel="next" href="{INDEX}?page=2">Next</a></main></body></html>'''
PAGE2=f'''<html><body><main><article><time datetime="2026-11-23">November 23, 2026</time><a href="{URL_PAST}">Company provides older clinical trial results to investors</a></article></main></body></html>'''
ARTICLE='''<html><head><meta property="article:published_time" content="2026-11-25T06:00:00+09:00"><meta property="og:title" content="Company provides important Phase 3 clinical trial update"></head><body><article><h1>Company provides important Phase 3 clinical trial update</h1>'''+('The company presented trial results in its official investor relations release. '*7)+'''</article></body></html>'''

class FakeFetcher:
    def __init__(self,pages,age=0):self.pages=pages;self.age=age;self.calls=[]
    def get(self,url):
        self.calls.append(url)
        if url not in self.pages:raise FetchError('FAKE_404',['FAKE_404'])
        return FetchResult(requested_url=url,final_url=url,html=self.pages[url],http_status=200,method='requests',
                           fetched_jst=NOW.isoformat(),snapshot_sha256='a'*64,
                           response_date='Wed, 25 Nov 2026 00:00:00 GMT',age_seconds=self.age)

def company(index=INDEX):return {'ticker':'TEST','name':'Example Pharma','batch_id':'A','official_indexes':[index]}

def test_46_fixed_universe():
    data=json.loads(Path('pharma46/sources.json').read_text())
    assert len(data['companies'])==46
    assert [x['ticker'] for x in data['companies']]==ORDER
    assert all(len(x['official_indexes'])>0 for x in data['companies'])
    assert 'https://investor.lilly.com/news-releases' not in data['companies'][0]['official_indexes']
    assert 'antengene.com' not in json.dumps(data).lower()

def test_dated_item_and_next_page():
    items=listing_entries(INDEX,PAGE1)
    assert items[0]['listing_date']=='2026-11-25'
    assert next_page_urls(INDEX,PAGE1)==[INDEX+'?page=2']

def test_date_formats():
    assert parse_date('2026-11-25')=='2026-11-25'
    assert parse_date('November 25, 2026')=='2026-11-25'
    assert parse_date('25 November 2026')=='2026-11-25'

def test_complete_page_chain_and_verified_article(tmp_path):
    f=FakeFetcher({INDEX:PAGE1,INDEX+'?page=2':PAGE2,URL_CURRENT:ARTICLE})
    d=scan_index(f,company(),INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert d['pagination_complete'] and d['found_baseline_boundary']
    assert len(d['listing_page_urls_checked'])==2
    assert d['candidate_releases'][0]['original_confirmed']
    assert URL_CURRENT in f.calls

def test_dated_old_listing_can_be_no_new_if_complete(tmp_path):
    f=FakeFetcher({INDEX:PAGE2})
    d=scan_index(f,company(),INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert d['pagination_complete'] and d['newer_listing_count']==0

def test_missing_second_page_never_counts_as_no_news(tmp_path):
    f=FakeFetcher({INDEX:PAGE1,URL_CURRENT:ARTICLE})
    d=scan_index(f,company(),INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert not d['pagination_complete']
    assert any(x['failure']=='FAKE_404' for x in d['errors'])

def test_stale_headers_disqualify_even_with_other_evidence(tmp_path):
    f=FakeFetcher({INDEX:PAGE1,INDEX+'?page=2':PAGE2,URL_CURRENT:ARTICLE},age=200000)
    d=scan_index(f,company(),INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert not d['pagination_complete']
    assert d['stale_cache'][0]['reason']=='AGE_GT_48H'

def test_missing_original_disqualifies_company(tmp_path):
    f=FakeFetcher({INDEX:PAGE1,INDEX+'?page=2':PAGE2})
    d=process_company(company(),f,NOW,{'companies':{}},tmp_path)
    assert d['status']=='未確認'
    assert d['attempt_start_jst'] and d['attempt_end_jst']
    assert d['previous_success_jst'] is None
    assert d['comparison_period']['type']=='provisional_24h'

def test_original_confirmed_but_index_incomplete_is_unconfirmed(tmp_path):
    f=FakeFetcher({INDEX:PAGE1,URL_CURRENT:ARTICLE})
    d=process_company(company(),f,NOW,{},tmp_path)
    assert d['status']=='未確認'
    assert d['primary_releases'][0]['original_confirmed']

def test_no_email_without_secrets(monkeypatch,tmp_path):
    for k in ('MAIL_USER','MAIL_APP_PASSWORD','MAIL_TO'):monkeypatch.delenv(k,raising=False)
    assert send_report('subject','body','2026-11-25')['status']=='NOT_CONFIGURED'
