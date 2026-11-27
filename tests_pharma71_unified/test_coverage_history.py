from datetime import datetime,timedelta,timezone
from pharma71_unified.coverage_history import gaps,record,evaluate
def test_adjacent_intervals_not_gap():
    a=datetime(2026,11,27,5,30,tzinfo=timezone.utc);b=a+timedelta(hours=5);c=b+timedelta(hours=1)
    assert gaps([(a,b),(b,c)],a,c)==[]
    assert gaps([(a,b),(b+timedelta(minutes=1),c)],a,c)==[(b,b+timedelta(minutes=1))]
def test_unconfirmed_run_does_not_erase_prior_or_fill_gap():
    z=datetime(2026,11,28,3,30,tzinfo=timezone(timedelta(hours=9)))
    s=z-timedelta(hours=2)
    e={'ticker':'LLY','status':'なし','pagination_complete':True,'tool_evidence_ref':'abc','new_success_jst':z.isoformat(),'comparison_period':{'start_jst':s.isoformat(),'end_jst':z.isoformat()}}
    audit={'run_id':'1','entries':[e]}
    first=record({},audit,z)
    assert len(first['LLY'])==1
    result=evaluate(first,['LLY'],z)
    assert result['verified']==0 and result['rows'][0]['gaps']
    e['status']='未確認'
    second=record(first,audit,z+timedelta(hours=1))
    assert first==second

def test_recovery_uses_earliest_missing_interval():
    from pharma71_unified.coverage_history import recovery_start,morning_window
    z=datetime(2026,11,28,3,30,tzinfo=timezone(timedelta(hours=9)))
    a,_=morning_window(z);b=a+timedelta(hours=1);c=b+timedelta(hours=1)
    rows={'LLY':[{'start_jst':b.isoformat(),'end_jst':c.isoformat(),'receipt_sha256':'abc','run_id':'1'}]}
    assert recovery_start(rows,'LLY',z,c.isoformat())==a.isoformat()
    rows['LLY'][0]['start_jst']=a.isoformat()
    assert recovery_start(rows,'LLY',z,c.isoformat()) is None
