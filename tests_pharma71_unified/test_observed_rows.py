from pharma46.extract import listing_entries
from pharma71_unified.registry import load_registry

def test_observed_press_release_links():
    r={x['ticker']:x for x in load_registry()['companies']}
    assert r['KURA']['official_indexes'][0]=='https://ir.kuraoncology.com/press-releases'
    assert r['EXEL']['official_indexes'][0]=='https://ir.exelixis.com/press-releases'
    assert r['ERAS']['official_indexes'][0]=='https://investors.erasca.com/news-events/news-releases'
    assert r['GENENTECH']['official_indexes'][0]=='https://www.gene.com/media/press-releases'

def test_neurocrine_dedicated_short_date():
    h='<div class="py-5 border-b border-brand-green-deep"><div class="investor-news-date">11/10/26</div><div class="investor-event-title">Neurocrine announces a 2026 conference</div><div class="nir-widget--news--read-more"><a href="/news-releases/news-release-details/test">Read More</a></div></div>'
    assert listing_entries('https://neurocrine.gcs-web.com/investors/news-releases',h)[0]['listing_date']=='2026-11-10'

def test_innovent_js_rendered_news_row():
    h='<div class="data_list"><div class="data_row"><div class="data_title"><span>2026.11.17</span></div><div class="div_content">Innovent Announces Takeda Granted SAKIGAKE Designation</div><div><a class="neibujump" href="/InvestorsAndMedia/PressReleaseDetail?key=628">Discover More</a></div></div></div>'
    e=listing_entries('https://en.innoventbio.com/InvestorsAndMedia/PressRelease',h)[0]
    assert e['listing_date']=='2026-11-17' and 'key=628' in e['url']

def test_kelun_hidden_publisher_links_not_javascript():
    h='<div class="text-box"><p class="time">2026年11月16日</p><h3 class="title h-text">科伦博泰官方公告</h3><a href="javascript:void(0)">查看详情</a><input class="otherlinks" value="https://mp.weixin.qq.com/s/example"/></div>'
    url='https://www.kelun-biotech.com/newsCenter.aspx?mid=18'
    e=listing_entries(url,h)[0]
    assert e['listing_date']=='2026-11-16' and e['url']=='https://mp.weixin.qq.com/s/example'
    assert listing_entries(url,h.replace('mp.weixin.qq.com','example.com'))==[]

def test_catalent_publication_field_not_article_excerpt():
    h='<div id="tabpanel-news-listing"><article><a href="/news/release"><p>November 2, 2026</p><h2>Catalent Appoints Group President</h2><p>Previously announced October 5, 2026</p></a></article></div>'
    assert listing_entries('https://www.catalent.com/news',h)[0]['listing_date']=='2026-11-02'

def test_kelun_generic_html_is_not_official_listing():
    url='https://www.kelun-biotech.com/newsCenter.aspx?mid=18'
    h='<main><article><time datetime="2026-11-25">November 25, 2026</time><a href="/news/2026/11/25/test-release">Generic unrelated article headline</a></article></main>'
    assert listing_entries(url,h)==[]

def test_kelun_recent_external_original_not_automatically_verified(tmp_path):
    from pharma46.engine import scan_index
    from test_end_to_end import NOW,SyntheticCompanyFetcher
    from datetime import timedelta
    url='https://www.kelun-biotech.com/newsCenter.aspx?mid=18'
    company={'ticker':'6990 HK','name':'Kelun'}
    f=SyntheticCompanyFetcher({'companies':[]})
    f.urls[url]='<div class="text-box"><p class="time">2026年11月25日</p><h3 class="title">Company announces important results from pivotal clinical trial</h3><input class="otherlinks" value="https://mp.weixin.qq.com/s/example"/></div><div class="text-box"><p class="time">2026年11月22日</p><h3 class="title">Historical release headline</h3><input class="otherlinks" value="https://mp.weixin.qq.com/s/older"/></div>'
    f.urls['https://mp.weixin.qq.com/s/example']='<html><head><meta property="og:title" content="Company announces important results from pivotal clinical trial"><meta property="article:published_time" content="2026-11-25T07:00:00+09:00"></head><body><article>'+('Clinical results from a controlled trial. '*20)+'</article></body></html>'
    result=scan_index(f,company,url,NOW-timedelta(days=1),NOW,tmp_path)
    assert len(result['candidate_releases'])==1
    assert not result['candidate_releases'][0]['original_confirmed']
    assert not result['pagination_complete']
