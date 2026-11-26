from pharma46.engine import ORDER,BATCHES,validate_report

def test_failing_46_inputs_are_not_successful():
    registry={'companies':[{'ticker':t} for t in ORDER]}
    entries=[]
    for batch,tickers in BATCHES.items():
        for t in tickers:
            entries.append({'ticker':t,'status':'なし','pagination_complete':False,
                            'listing_page_urls_checked':[], 'latest_publication_date':None,
                            'oldest_publication_date':None,'new_success_jst':None,
                            'stale_cache_status':None,'homepage_visit_status':'未訪問',
                            'tool_evidence_ref':None,'primary_releases':[]})
    errs=validate_report(registry,entries)
    assert len(errs)==46
    assert all('SUCCESS_WITHOUT_COVERAGE_EVIDENCE' in e for e in errs)
