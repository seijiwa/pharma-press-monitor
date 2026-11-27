"""Offline simulated all-46 integration, not a claim of live site coverage."""
import json
from pathlib import Path
from copy import deepcopy
from urllib.parse import urlparse
from datetime import datetime,timedelta
from pharma46.fetch import JST,FetchResult,FetchError
from pharma46.engine import collect,ORDER,render_report

NOW=datetime(2026,11,25,8,0,tzinfo=JST)
BODY=('A verified official newsroom article publishes the complete data from a controlled clinical study. '*8)

def synthetic_registry(registry):
    """Use reserved test domains for generic end-to-end HTML, not live-site adapters.

    Live-site selectors have separate fixture tests. Never loosen a production
    parser to accept generic mock HTML on a real company's exact newsroom URL.
    """
    mock=deepcopy(registry)
    for c in mock['companies']:
        key=c['ticker'].lower().replace(' ','-')
        c['official_indexes']=[f'https://fixture-{key}.example/news']
        c.pop('known_official_release_floor',None)
    return mock

class SyntheticCompanyFetcher:
    def __init__(self,registry,all_fail=False):
        self.all_fail=all_fail;self.urls={};self.calls=[]
        for c in registry['companies']:
            index=c['official_indexes'][0];h=urlparse(index).netloc
            article=f'https://{h}/news/2026/11/25/test-release-{c["ticker"].replace(" ","-").lower()}'
            previous=f'https://{h}/news/2026/11/22/older-release-{c["ticker"].replace(" ","-").lower()}'
            self.urls[index]=f'''<html><body><main><article><time datetime="2026-11-25">November 25, 2026</time><a href="{article}">Company announces important results from pivotal clinical trial</a></article><article><time datetime="2026-11-22">November 22, 2026</time><a href="{previous}">Historical previously published medical trial results update</a></article></main></body></html>'''
            self.urls[article]=f'''<html><head><meta property="article:published_time" content="2026-11-25T07:00:00+09:00"><meta property="og:title" content="Company announces important results from pivotal clinical trial"></head><body><article>{BODY}</article></body></html>'''
    def get(self,url):
        self.calls.append(url)
        if self.all_fail or url not in self.urls:raise FetchError('FAKE_UNAVAILABLE',['FAKE_UNAVAILABLE'])
        return FetchResult(requested_url=url,final_url=url,html=self.urls[url],http_status=200,method='requests',
                           fetched_jst=NOW.isoformat(),snapshot_sha256='f'*64,
                           response_date='Wed, 25 Nov 2026 00:00:00 GMT',age_seconds=0)

def test_full_46_offline_simulation(tmp_path):
    registry=synthetic_registry(json.loads(Path('pharma46/sources.json').read_text()))
    fetcher=SyntheticCompanyFetcher(registry)
    entries,errors,state=collect(registry,{'companies':{}},asof=NOW,fetcher=fetcher,
                                 evidence_dir=tmp_path,workers=3)
    assert [x['ticker'] for x in entries]==ORDER
    assert errors==[]
    assert all(x['status']=='あり' for x in entries)
    assert all(x['primary_releases'][0]['new_status']=='FIRST_OBSERVED_NOT_PROVEN_NEW' for x in entries)
    assert len(state['companies'])==46
    subject,body,summary=render_report(NOW,entries,errors,'OFFLINE SYNTHETIC TEST')
    assert summary['period_verified']==46
    assert summary['primary_originals']==46
    assert 'OFFLINE SYNTHETIC TEST' in body
    assert '未確認0社' not in subject or summary['unconfirmed']==0


def test_all_http_errors_never_count_as_no_release(tmp_path):
    registry=json.loads(Path('pharma46/sources.json').read_text())
    entries,errors,_=collect(registry,{'companies':{}},asof=NOW,
                              fetcher=SyntheticCompanyFetcher(registry,all_fail=True),
                              evidence_dir=tmp_path,workers=3)
    assert not errors
    assert len(entries)==46
    assert all(x['status']=='未確認' for x in entries)
    assert all(x['homepage_visit_status']=='失敗' for x in entries)
    _,_,summary=render_report(NOW,entries,errors,'SYNTHETIC FAILURE')
    assert summary['period_verified']==0 and summary['unconfirmed']==46
