from datetime import datetime,timedelta,timezone
from pharma71_unified.regulatory_history import merge_history,report

NOW=datetime(2026,11,27,20,tzinfo=timezone.utc)
URL='https://www.sec.gov/Archives/edgar/data/123/456/ex99.htm'
def reg(stamp,verified=True):
    return {'run_id':'123','entries':[{'ticker':'LLY','issuer_identity_verified':verified,'exhibit_results':[{'filing_date':'2026-11-27','exhibits':[{'original_confirmed':True,'url':URL,'description':'EX-99','receipt':{'fetched_jst':stamp.isoformat(),'http_status':200,'sha256':'a'*64}}]}]}]}

def test_failed_regulatory_poll_retains_prior_verified_exhibits():
    prior={'regulatory_observations':reg(NOW-timedelta(hours=1))}
    failed={'run_id':'124','status':'SOURCE_UNAVAILABLE','entries':[]}
    h=merge_history(prior,failed,NOW)
    assert len(h)==1 and h[0]['run_id']=='123'
    assert URL in report(failed,h)
    assert URL not in report(prior['regulatory_observations'],h)

def test_history_excludes_unverified_stale_and_future():
    for prior in (reg(NOW,False),reg(NOW-timedelta(days=8)),reg(NOW+timedelta(seconds=1))):
        assert merge_history({'regulatory_observations':prior},{},NOW)==[]

def test_history_preserves_latest_receipt_and_deduplicates():
    prior=reg(NOW-timedelta(hours=1))
    current=reg(NOW);current['run_id']='124'
    h=merge_history({'regulatory_observations':prior},current,NOW)
    assert len(h)==1 and h[0]['run_id']=='124'
    assert merge_history({'sec_exhibit_history':h},{},NOW)==h
