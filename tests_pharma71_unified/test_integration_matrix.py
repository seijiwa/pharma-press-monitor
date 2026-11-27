from pharma71_unified.integration import matrix,parent_scope
def e(t,status='未確認',start='2026-11-26T00:00:00+09:00'):
    return {'ticker':t,'status':status,'comparison_period':{'start_jst':start,'end_jst':'2026-11-27T00:00:00+09:00'},'primary_releases':[]}
def test_sec_does_not_promote_newsroom():
    r=matrix([e('SUPN')],{'entries':[{'ticker':'SUPN','status':'FILING_METADATA_RETRIEVED','issuer_identity_verified':True}]},[])
    assert r['rows'][0]['status']=='SEC_WINDOW_ONLY_NEWSROOM_UNCONFIRMED'
    assert not r['rows'][0]['newsroom_period_verified'] and not r['production_ready']
def test_issuer_identity_required():
    r=matrix([e('SUPN')],{'entries':[{'ticker':'SUPN','status':'FILING_METADATA_RETRIEVED'}]},[])
    assert r['rows'][0]['status']=='NO_VERIFIED_PERIOD'
def test_parent_window_not_silently_shortened():
    entries=[e('RNA'),e('REATA'),e('JNANA'),e('NOVN','なし','2026-11-26T23:00:00+09:00'),e('BIIB','なし')]
    p=parent_scope(entries,{},None)
    assert p[0]['status']=='PARENT_SCOPE_UNCONFIRMED'
    assert p[1]['status']=='PARENT_LISTING_VERIFIED_KEYWORD_SCOPE_LIMITED'
    assert p[2]['status']=='PARENT_SCOPE_UNCONFIRMED'


def test_parent_asset_aliases():
    import re
    from pharma71_unified.integration import PARENT
    assert re.search(PARENT['REATA'][2],'SKYCLARYS update',re.I)
    assert re.search(PARENT['JNANA'][2],'repinatrabit phase 3',re.I)
