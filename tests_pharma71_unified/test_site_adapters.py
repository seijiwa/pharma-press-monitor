from pharma46.extract import listing_entries
import pytest

@pytest.mark.parametrize("url,html,expected",[
 ("https://news.abbvie.com/", """<div class="item"><a href="/2026-11-25-featured">Pinned feature, November 25, 2026</a></div><div class="wd_item_wrapper"><div class="wd_date">November 23, 2026</div><div class="wd_title"><a href="/2026-11-23-release">Approved new treatment</a></div></div>""","2026-11-23"),
 ("https://ir.vikingtherapeutics.com/press-releases", """<li class="wd_item"><div class="wd_date">Nov 15, 2026</div><div class="wd_item_wrapper"><div class="wd_title"><a href="/2026-11-15-release">Clinical results expected November 30, 2026</a></div></div></li>""","2026-11-15"),
 ("https://www.novartis.com/news", """<div id="tab-all"><li class="each-item"><a href="/news/media-releases/new"><time datetime="2026-11-23T07:00:00Z">Nov 23, 2026</time><h3>Release headline</h3></a></li></div><div id="tab-stories"><li class="each-item"><a href="/news/stories/old"><time datetime="2024-01-01">Jan 1, 2024</time><h3>Other tab</h3></a></li></div>""","2026-11-23"),
 ("https://www.galderma.com/newsroom", """<a class="news-teaser" href="/news/new"><div class="header"><p>11 . 18 . 2026</p><p>News story</p></div><h2 class="title">Release headline</h2></a>""","2026-11-18"),
 ("https://smmttx.com/news/press-releases/default.aspx", """<div class="module_item"><div class="module_item-wrap"><div class="module_date-time">November 19, 2026</div><a class="module_headline-link" href="/news/press-releases/news-details/2026/new/default.aspx">Call on November 30, 2026</a></div></div>""","2026-11-19"),
 ("https://c2n.com/news-releases", """<article class="blog-item"><time class="blog-date">11/18/26</time><h1 class="blog-title"><a href="/news-releases/new">Company release</a></h1></article>""","2026-11-18"),
 ("https://www.sumitomo-pharma.com/news/", """<li><p class="date-container"><span class="date">Nov. 25, 2026</span></p><p class="text"><a href="/news/20261125-1.html">Clinical development announcement</a></p></li>""","2026-11-25"),
 ("https://www.daiichisankyo.com/media/press_release/", """<li class="active"><div class="newsDate">November 12, 2026</div><div class="newsTitle"><a href="/files/news/pressrelease/pdf/202611/20261112_E.pdf">Clinical development announcement</a></div></li>""","2026-11-12"),
 ("https://www.biomarin.com/news/press-releases/", """<article class="press-release"><h3><a href="/news/press-releases/new">Conference announcement</a></h3><p class="date">November 4, 2026</p></article>""","2026-11-04"),
])
def test_scoped_publication_dates(url,html,expected):
    rows=listing_entries(url,html,preserve_order=True)
    assert len(rows)==1 and rows[0]['listing_date']==expected

def test_malformed_official_row_not_silently_skipped():
    html='<div class="wd_item_wrapper"><div class="wd_title"><a href="/2026-11-25-new">Missing publication date</a></div></div>'
    assert listing_entries('https://news.abbvie.com/',html)==[]
