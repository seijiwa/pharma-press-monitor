from datetime import datetime
from pharma46.fetch import JST
from pharma46.api_observations import coverage_check

def test_novo_api_requires_complete_dated_boundary_and_freshness():
    now=datetime(2026,11,28,5,0,tzinfo=JST)
    data={'data':{'resultBeanList':[{'language':'en'},{'language':'en'}],'numberOfResults':2}}
    rows=[{'url':'https://www.novonordisk.com/a','listing_date':'2026-11-27'},{'url':'https://www.novonordisk.com/b','listing_date':'2026-11-20'}]
    stamp='Fri, 27 Nov 2026 20:00:00 GMT'
    assert coverage_check('NOVOB',data,rows,'2026-11-27','2026-11-28',now,stamp,0) is None
    assert coverage_check('NOVOB',data,rows[:1],'2026-11-27','2026-11-28',now,stamp,0)=='API_TRUNCATED_OR_UNPARSED'
    assert coverage_check('NOVOB',data,rows,'2026-11-27','2026-11-28',now,'Tue, 24 Nov 2026 20:00:00 GMT',0)=='API_STALE_HTTP'
    assert coverage_check('NOVOB',data,list(reversed(rows)),'2026-11-27','2026-11-28',now,stamp,0)=='API_UNSORTED'

def test_samsung_api_rejects_wrong_scope():
    now=datetime(2026,11,28,5,0,tzinfo=JST)
    data={'dataMainList':[{'boardCtgryCcd':'2'}],'totalCnt':{'cnt':1}}
    rows=[{'url':'https://samsungbiologics.com/a','listing_date':'2026-11-20'}]
    assert coverage_check('207940 KS',data,rows,'2026-11-27','2026-11-28',now,'Fri, 27 Nov 2026 20:00:00 GMT',0)=='API_MIXED_SCOPE'
