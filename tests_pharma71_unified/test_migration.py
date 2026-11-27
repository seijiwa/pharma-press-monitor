from datetime import datetime
from email.utils import format_datetime
from pharma46.fetch import JST
from pharma46.extract import listing_entries
from pharma71_unified.api_observations import parse_api,coverage_check
NOW=datetime(2026,11,27,10,tzinfo=JST)
HDR=format_datetime(NOW)
def test_biogen_exact_card_date():
    h='<div class="card cmp-card-tile"><div class="news-date">November 23, 2026</div><div class="card-body"><div class="card-title">Official release about 2027 trial</div><a href="/news-releases/news-release-details/example"></a></div></div>'
    assert listing_entries('https://investors.biogen.com/news/news-releases',h)[0]['listing_date']=='2026-11-23'
def test_ionis_date_not_headline():
    h='<div class="llf-row"><div class="nir-widget--news--date-time">Nov 17, 2026</div><div class="nir-widget--news--headline"><a href="/news-releases/news-release-details/test">Release announced for November 28, 2026</a></div></div>'
    assert listing_entries('https://ir.ionis.com/investor-news/press-releases',h)[0]['listing_date']=='2026-11-17'
def test_novo_strict_api_coverage():
    d={'status':200,'data':{'numberOfResults':2,'resultBeanList':[{'language':'en','title':'Official release one','fromIntegration':True,'id':1,'date':'2026-11-23T10:00:00'},{'language':'en','title':'Official release two','fromIntegration':True,'id':2,'date':'2026-11-20T10:00:00'}]}}
    rows,_,_=parse_api('NOVOB',d)
    assert coverage_check('NOVOB',d,rows,'2026-11-26','2026-11-28',NOW,HDR,'0') is None
    assert coverage_check('NOVOB',d,rows,'2026-11-19','2026-11-28',NOW,HDR,'0')=='API_BASELINE_NOT_REACHED'
    assert coverage_check('NOVOB',d,list(reversed(rows)),'2026-11-26','2026-11-28',NOW,HDR,'0')=='API_UNSORTED'
    assert coverage_check('NOVOB',d,rows,'2026-11-26','2026-11-28',NOW,HDR,'200000')=='API_STALE_HTTP'
    d['data']['numberOfResults']=51
    assert coverage_check('NOVOB',d,rows,'2026-11-26','2026-11-28',NOW,HDR,'0')=='API_TRUNCATED_OR_UNPARSED'
def test_samsung_actual_epoch_schema():
    d={'totalCnt':{'cnt':1},'dataMainList':[{'engSbjt':'Samsung Biologics release','engSortcutLink':'test','boarddtm':1793858400000,'boardCtgryCcd':'1'}]}
    rows,_,_=parse_api('207940 KS',d)
    assert rows[0]['listing_date']=='2026-11-05'
    assert coverage_check('207940 KS',d,rows,'2026-11-26','2026-11-28',NOW,HDR,'0') is None
    d['dataMainList'][0]['boardCtgryCcd']='2'
    assert coverage_check('207940 KS',d,rows,'2026-11-26','2026-11-28',NOW,HDR,'0')=='API_MIXED_SCOPE'
