from pharma71_unified.wire import archive_rows,verify_article,exact_source,valid_release
URL='https://www.globenewswire.com/news-release/2026/11/27/1234/0/en/company-update.html'
TITLE='Denali Therapeutics announces clinical trial update'
ISSUER='Denali Therapeutics Inc.'
def test_exact_publisher_not_mentions():
    assert exact_source('Denali Therapeutics, Inc.',ISSUER)
    assert not exact_source('Research and Markets',ISSUER)
    assert not exact_source('Denali Therapeutics Inc. and Other Company',ISSUER)
def test_archive_rows_require_source_and_date():
    h=f'<article><p>November 27, 2026 08:00 ET | Source: {ISSUER}</p><h2><a href="{URL}">{TITLE}</a></h2></article>'
    assert archive_rows('https://www.globenewswire.com/search/organization/test',h,ISSUER)[0]['listing_date']=='2026-11-27'
    assert archive_rows('https://www.globenewswire.com/search/organization/test',h.replace(ISSUER,'Research and Markets'),ISSUER)==[]
    assert archive_rows('https://www.globenewswire.com/search/organization/test',h.replace('November 27','November 26'),ISSUER)==[]
def test_original_requires_publisher_header():
    html=f'<html><head><meta property="og:title" content="{TITLE}"><meta property="article:published_time" content="2026-11-27T08:00:00-05:00"></head><body><header><p>Source: {ISSUER}</p></header><article>'+('The company reports results from its pivotal clinical study. '*12)+'</article></body></html>'
    item={'title':TITLE,'listing_date':'2026-11-27'}
    assert verify_article(URL,html,item,ISSUER)
    assert verify_article(URL,html.replace('Source: '+ISSUER,'Source: Research and Markets'),item,ISSUER) is None
    assert verify_article(URL,html.replace('<header>','<div>').replace('</header>','</div>'),item,ISSUER) is None
    assert not valid_release('https://globenewswire.com.example.com/news-release/2026/11/27/1234/0/en/example.html')
