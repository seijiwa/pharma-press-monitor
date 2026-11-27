from pharma71_unified.lonza_scope import combine

def row(status):
    return {'status':status,'comparison_period':{},'primary_releases':[],'listing_page_urls_checked':['news'],'new_success_jst':'test','pagination_complete':True}

def test_media_failure_downgrades_news_only():
    r=combine(row('なし'),{'pagination_complete':False,'candidate_releases':[]})
    assert r['status']=='未確認' and r['new_success_jst'] is None

def test_media_success_does_not_promote_unverified_news():
    s={'pagination_complete':True,'candidate_releases':[{'url':'media','original_confirmed':True}],'listing_page_urls_checked':['media']}
    r=combine(row('未確認'),s)
    assert r['status']=='未確認' and len(r['primary_releases'])==1

def test_both_scopes_pass():
    s={'pagination_complete':True,'candidate_releases':[],'listing_page_urls_checked':['media']}
    r=combine(row('なし'),s)
    assert r['status']=='なし' and r['listing_page_urls_checked']==['news','media']
