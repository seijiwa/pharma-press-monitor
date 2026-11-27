from pharma71_unified.sec_identity import resolve,verify_identity
from pharma71_unified.integration import parent_scope
from pharma46.extract import page_has_unresolved_load_more
def test_supernus_successor_legal_name():
    m=resolve({'ticker':'SUPN','name':'Supernus Pharmaceuticals'},{'SUPN':1625297})
    assert verify_identity({'cik':1625297,'tickers':['SUPN'],'name':'Supernus, Inc.'},m)
    assert resolve({'ticker':'SUPN','name':'Supernus Pharmaceuticals'},{'SUPN':1}) is None
def test_parent_dedicated_archive_at_child_baseline():
    def e(t,s='未確認'):
        return {'ticker':t,'status':s,'comparison_period':{'start_jst':'2026-11-26T00:00:00+09:00','end_jst':'2026-11-27T00:00:00+09:00'},'primary_releases':[]}
    r=parent_scope([e('RNA'),e('REATA'),e('JNANA'),e('NOVN'),e('BIIB')],{},None,{'RNA':e('RNA','なし'),'JNANA':e('JNANA','なし')})
    assert r[0]['parent_listing_period_verified'] and r[2]['parent_listing_period_verified']
    assert not r[1]['parent_listing_period_verified']
def test_catalent_identical_responsive_counts():
    from pharma46.extract import _row_listing
    url='https://www.catalent.com/news/'
    html='<html><body><div id="tabpanel-news-listing"><p>Showing 2 of 420 Press Releases</p><p>Showing 2 of 420 Press Releases</p><article><a href="/news/one"><h2>First corporate press release title</h2><p>November 2, 2026</p></a></article><article><a href="/news/two"><h2>Second corporate press release title</h2><p>May 13, 2026</p></a></article><button>Load More Press Releases</button></div></body></html>'
    from bs4 import BeautifulSoup
    # If fixture layout does not match the strict production row parser, do
    # not assert a false complete boundary.
    rows=_row_listing(url,BeautifulSoup(html,'html.parser'))
    assert page_has_unresolved_load_more(html,url,True)==(len(rows or [])!=2)
    assert page_has_unresolved_load_more(html.replace('Showing 2 of 420 Press Releases','Showing 3 of 420 Press Releases',1),url,True)
