"""Regression tests for previously observed false assurances / missed releases."""
import json
from datetime import timedelta
from pathlib import Path
from pharma46.engine import scan_index,process_company,collect,ORDER
from pharma46.extract import parse_date,listing_entries
from test_audit import NOW,INDEX,URL_CURRENT,URL_PAST,PAGE1,PAGE2,ARTICLE,FakeFetcher,company


def _card(when,href,title):
    return f'<article><time datetime="{when}">{when}</time><a href="{href}">{title}</a></article>'


def test_japanese_chinese_and_korean_date_formats():
    assert parse_date('2026年11月25日')=='2026-11-25'
    assert parse_date('2026. 11. 25')=='2026-11-25'
    assert parse_date('2026/11/25')=='2026-11-25'


def test_pinned_old_release_never_closes_window_early(tmp_path):
    """A pinned old article on page one must not hide page-two new articles."""
    late=f'{INDEX}/2026/11/25/late-major-trial-release'
    index=f'<html><main>{_card("2026-11-20", URL_PAST, "An old pinned investor clinical trial announcement")}{_card("2026-11-25",URL_CURRENT,"Company provides important Phase 3 clinical trial update")}<a rel="next" href="{INDEX}?page=2">Next</a></main></html>'
    page2=f'<html><main>{_card("2026-11-25",late,"Major new pivotal clinical trial announcement from company")}{_card("2026-11-19",URL_PAST,"Historic regulatory development released previously")}</main></html>'
    f=FakeFetcher({INDEX:index,INDEX+'?page=2':page2,URL_CURRENT:ARTICLE})
    out=scan_index(f,company(),INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert INDEX+'?page=2' in f.calls
    assert not out['pagination_complete']
    assert any(e['failure']=='UNSORTED_DATED_LISTING' for e in out['errors'])
    assert late in [e['url'] for e in out['candidate_releases']]


def test_cross_page_newer_item_disqualifies_even_if_old_boundary_found(tmp_path):
    new2=f'{INDEX}/2026/11/25/unexpected-newer-on-page-2'
    index=PAGE1
    page2=f'<html><main>{_card("2026-11-26",new2,"Additional clinical result from unexpected ordering")}{_card("2026-11-23",URL_PAST,"Earlier regulatory filing for the clinical program")}</main></html>'
    f=FakeFetcher({INDEX:index, INDEX+'?page=2':page2, URL_CURRENT:ARTICLE})
    out=scan_index(f,company(),INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert not out['pagination_complete']
    assert any(x['failure']=='CROSS_PAGE_DATE_ORDER_INVERSION' for x in out['errors'])


def test_verified_newer_press_release_exposes_old_list_even_with_fresh_http_date(tmp_path):
    c=company()
    c['known_official_release_floor']={'date':'2026-11-25','url':URL_CURRENT}
    f=FakeFetcher({INDEX:PAGE2})
    out=scan_index(f,c,INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert not out['pagination_complete']
    assert any(x['reason']=='KNOWN_VERIFIED_ORIGINAL_NOT_IN_LISTING' for x in out['stale_cache'])


def test_previous_verified_original_in_state_becomes_freshness_floor(tmp_path):
    f=FakeFetcher({INDEX:PAGE2})
    state={'companies':{'TEST':{'latest_verified_original':{'date':'2026-11-25','url':URL_CURRENT}}}}
    out=process_company(company(),f,NOW,state,tmp_path)
    assert out['status']=='未確認'
    assert out['stale_cache_status']


def test_unrelated_same_day_article_fails_original_title_match(tmp_path):
    wrong=ARTICLE.replace('Company provides important Phase 3 clinical trial update','Another company celebrates its annual employee awards')
    f=FakeFetcher({INDEX:PAGE1,INDEX+'?page=2':PAGE2,URL_CURRENT:wrong})
    out=scan_index(f,company(),INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert not out['pagination_complete']
    assert out['candidate_releases'][0]['original_confirmed'] is False


def test_future_dated_article_excluded_from_recent_window(tmp_path):
    far_future=f'{INDEX}/2027/01/05/far-future-announcement'
    older=f'<html><main>{_card("2027-01-05",far_future,"Future announcement not yet published by company")}{_card("2026-11-20",URL_PAST,"Historical trial results from last week")}</main></html>'
    f=FakeFetcher({INDEX:older})
    out=scan_index(f,company(),INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert out['newer_listing_count']==0
    assert out['candidate_releases']==[]


def test_unresolved_load_more_even_with_page_links_cannot_pass(tmp_path):
    page=f'<html><main>{_card("2026-11-23",URL_PAST,"Historical regulatory update from company")}<button>Load more</button><a rel="next" href="{INDEX}?page=2">Next</a></main></html>'
    f=FakeFetcher({INDEX:page})
    out=scan_index(f,company(),INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert not out['pagination_complete']
    assert out['incomplete_load_more']


def test_unseen_same_day_release_does_not_claim_exact_post_baseline_timestamp(tmp_path):
    registry=json.loads(Path('pharma46/sources.json').read_text())
    from test_end_to_end import SyntheticCompanyFetcher,synthetic_registry
    registry=synthetic_registry(registry)
    state={'companies':{}}
    for t in ORDER:state['companies'][t]={'last_verified_success_jst':'2026-11-25T06:00:00+09:00'}
    fetched,errors,new_state=collect(registry,state,asof=NOW,
                            fetcher=SyntheticCompanyFetcher(registry),evidence_dir=tmp_path,workers=3)
    assert errors==[]
    assert all(any(p['new_status']=='UNSEEN_IN_DATE_WINDOW_TIME_UNCERTAIN' for p in e['primary_releases']) for e in fetched)
    assert all(e['status']=='あり' for e in fetched)


def test_fresh_first_page_and_old_second_page_not_labeled_stale(tmp_path):
    c=company()
    c['known_official_release_floor']={'date':'2026-11-25','url':URL_CURRENT}
    f=FakeFetcher({INDEX:PAGE1,INDEX+'?page=2':PAGE2,URL_CURRENT:ARTICLE})
    out=scan_index(f,c,INDEX,NOW-timedelta(days=1),NOW,tmp_path)
    assert out['pagination_complete']
    assert not out['stale_cache']
