from pharma71_unified.integration import parent_regulatory_matches
def test_parent_sec_does_not_promote_coverage():
    parents=[{'ticker':'REATA','parent_ticker':'BIIB','status':'PARENT_SCOPE_UNCONFIRMED','parent_listing_period_verified':False}]
    reg={'entries':[{'ticker':'BIIB','issuer_identity_verified':True,'exhibit_results':[{'filing_date':'2026-11-27','exhibits':[{'url':'https://www.sec.gov/test','original_confirmed':True,'description':'Earnings','body_excerpt':'SKYCLARYS'}]}]}]}
    result=parent_regulatory_matches(parents,reg)[0]
    assert len(result['matched_sec_exhibits'])==1
    assert not result['parent_listing_period_verified']
    assert result['status']=='PARENT_SCOPE_UNCONFIRMED'
