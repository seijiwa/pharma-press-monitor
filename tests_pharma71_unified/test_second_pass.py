from pharma46.extract import listing_entries,next_page_urls,page_has_unresolved_load_more
from pharma71_unified.api_observations import parse_api

def test_immunome_official_slug():
    h='<div class="content-wrapper"><div class="dynamic">November 18, 2026</div><h3><a href="/immunome-to-present/">Company to Present at Upcoming Conferences</a></h3></div>'
    assert listing_entries('https://investors.immunome.com/news-releases/',h)[0]['listing_date']=='2026-11-18'

def test_grifols_press_only():
    h='<div class="card-content"><p class="text-lg text-bold">Release headline</p><p class="card-metadata">November 18, 2026</p><div class="button-row"><a href="/en/view-news/-/news/new">Read Release</a></div></div><div class="card-content"><a href="/documents/file.pdf">Financial archive</a></div>'
    assert len(listing_entries('https://www.grifols.com/en/newsroom',h))==1

def test_alkermes_dated_press_rows_only():
    h='<div><p><strong><span>November 24, 2026</span></strong><br/>Alkermes announces clinical results</p><p><a href="https://investor.alkermes.com/news-releases/news-release-details/test">Read more</a></p></div>'
    row=listing_entries('https://www.alkermes.com/news',h)[0]
    assert row['listing_date']=='2026-11-24' and row['title']=='Alkermes announces clinical results'

def test_zealand_directly_linked_distributor_only():
    h='<arcticle class="card card-list card-article"><div class="card__meta"><time>24 Nov 2026</time></div><div class="card-list__main"><h2>Zealand Pharma release headline</h2></div><div class="card-list__cta"><a href="https://www.globenewswire.com/news-release/2026/11/24/123/0/en/zealand-pharma-announces-test.html">Read More</a></div></arcticle>'
    url='https://www.zealandpharma.com/news-media/'
    assert len(listing_entries(url,h))==1
    assert listing_entries(url,h.replace('zealand-pharma-announces-test','unrelated-company-release'))==[]

def test_jnj_explicit_page_and_unrelated_button():
    url='https://www.jnj.com/media-center/press-releases'
    h='<bsp-load-more data-url="?p=2"><button>Load more</button></bsp-load-more>'
    assert next_page_urls(url,h)==[url+'?p=2']
    assert not page_has_unresolved_load_more(h,url)
    assert page_has_unresolved_load_more(h+'<button>Load more</button>',url)
    assert page_has_unresolved_load_more(h.replace('?p=2','https://bad.example/?p=2'),url)

def test_viking_declared_offset_only_after_boundary():
    url='https://ir.vikingtherapeutics.com/press-releases'
    h='<ul class="wd_item_list"><li class="wd_item"><div class="wd_date">November 15, 2026</div><div class="wd_title"><a href="/new">Company announces result</a></div></li></ul><button class="wd_load_more-trigger" data-limit="1" data-offset="1" data-total="2" data-content=".wd_item_list">Load more</button>'
    assert page_has_unresolved_load_more(h,url,False)
    assert not page_has_unresolved_load_more(h,url,True)
    assert page_has_unresolved_load_more(h.replace('data-offset="1"','data-offset="2"'),url,True)

def test_novo_api_missing_date_remains_candidate():
    data={'status':200,'data':{'resultBeanList':[{'language':'en','title':'Official company release','fromIntegration':True,'id':123}]}}
    rows,keys,count=parse_api('NOVOB',data)
    assert count==1 and len(rows)==1 and rows[0]['listing_date'] is None

def test_samsung_api_dated_candidate():
    data={'dataMainList':[{'engSbjt':'Official company release','engSortcutLink':'test','regDate':'2026-11-25'}]}
    rows,keys,count=parse_api('207940 KS',data)
    assert rows[0]['listing_date']=='2026-11-25' and count==1
