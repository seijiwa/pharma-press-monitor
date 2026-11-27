from pharma46.engine import transient_failure,merge_retry
def test_retry_policy():
    def row(failure):return {'status':'未確認','index_attempts':[{'errors':[{'failure':failure}]}]}
    assert transient_failure(row('HTTP_503'))
    assert transient_failure(row('REQUEST_Timeout'))
    assert not transient_failure(row('HTTP_403 | BROWSER_Timeout'))
    assert not transient_failure(row('HTTP_429'))
def test_retry_preserves_originals():
    first={'ticker':'LLY','comparison_period':{},'status':'未確認','reason':'timeout','index_attempts':[],'alternative_attempts':[],'primary_releases':[{'url':'a','original_confirmed':True}]}
    second=dict(first,status='なし',reason='verified',primary_releases=[{'url':'b','original_confirmed':True}])
    result=merge_retry(first,second)
    assert result['status']=='なし'
    assert {x['url'] for x in result['primary_releases']}=={'a','b'}
