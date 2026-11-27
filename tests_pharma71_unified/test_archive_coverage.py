import json
from datetime import datetime
from email.utils import format_datetime
from pharma46.fetch import JST
from pharma46.extract import page_has_unresolved_load_more
from pharma71_unified.official_fallback import lundbeck_archive_coverage
NOW=datetime(2026,11,27,10,tzinfo=JST)
HDR=format_datetime(NOW)

def archive():
    return {'filters':[{'property':'type','options':[{'value':'Press Release','selected':False}]},{'property':'year','options':[{'value':y,'selected':False} for y in ('2026','2025')]},{'property':'language','options':[{'value':'en','selected':True},{'value':'da','selected':False}]}],
            'items':[{'language':'en','title':'Official update','id':1,'year':'2026','publishDate':'2026-11-24T08:00:00+00:00','url':'https://news.cision.com/h--lundbeck-a-s/r/official-update,c1'},
                     {'language':'en','title':'Earlier release','id':2,'year':'2025','publishDate':'2025-10-10T08:00:00+00:00','url':'https://news.cision.com/h--lundbeck-a-s/r/earlier-release,c2'}]}
def test_lundbeck_unfiltered_archive_boundary():
    d=archive()
    rows,err=lundbeck_archive_coverage(json.dumps(d),'2026-11-26','2026-11-28',NOW,HDR,'0')
    assert err is None and len(rows)==2
    d['filters'][0]['options'][0]['selected']=True
    assert lundbeck_archive_coverage(json.dumps(d),'2026-11-26','2026-11-28',NOW,HDR,'0')[1]=='LUNDBECK_FILTERED_ARCHIVE'
def test_lundbeck_rejects_invalid_current_record_and_stale():
    d=archive();d['items'][0]['url']='https://news.cision.com/other/r/wrong'
    assert lundbeck_archive_coverage(json.dumps(d),'2026-11-26','2026-11-28',NOW,HDR,'0')[1]=='LUNDBECK_INVALID_CURRENT_RECORD'
    assert lundbeck_archive_coverage(json.dumps(archive()),'2026-11-26','2026-11-28',NOW,HDR,'200000')[1]=='LUNDBECK_STALE_RESPONSE'
def test_catalent_declared_visible_count_requires_boundary():
    u='https://www.catalent.com/news/'
    h='<div id="tabpanel-news-listing"><article><a href="/news/older"><p>November 2, 2026</p><h2>Official company release</h2></a></article><button>Load More Press Releases</button><p>Showing 1 of 420 Press Releases</p></div>'
    assert page_has_unresolved_load_more(h,u,False)
    assert not page_has_unresolved_load_more(h,u,True)
    assert page_has_unresolved_load_more(h.replace('Showing 1','Showing 2'),u,True)
    assert page_has_unresolved_load_more(h+'<button>Load more</button>',u,True)
