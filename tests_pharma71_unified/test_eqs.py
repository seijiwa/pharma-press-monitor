import pytest
from pharma71_unified.eqs import archive_links,verify,release_url,SOURCES
URL='https://www.eqs-news.com/news/ad-hoc/bayer-update/2f30aacd-cc34-45a3-8032-90d09fea8bfc_en'
def test_eqs_issuer_binding():
    url,isin,names=SOURCES['BAYN']
    h=f'<h1>Bayer AG</h1><p>{isin}</p><a href="{URL}">Bayer AG announcement</a>'
    assert URL in archive_links(h,url,isin,names)
    with pytest.raises(ValueError):archive_links(h.replace(isin,'DE0000000000'),url,isin,names)
    assert not release_url(URL.replace('www.eqs-news.com','www.eqs-news.com.example.org'))
def test_eqs_original_needs_exact_issuer_and_date():
    _,isin,names=SOURCES['BAYN']
    h='<html><head><title>Bayer corporate announcement</title></head><body><h1>Bayer AG</h1><p>25-Nov-2026 / 08:00 CET</p><p>Company: Bayer AG</p><p>ISIN: '+isin+'</p><p>EQS News Service</p><p>'+('Corporate release details. '*40)+'</p></body></html>'
    assert verify(h,URL,isin,names)['published_date']=='2026-11-25'
    assert verify(h.replace('Company: Bayer AG','Company: Other AG'),URL,isin,names) is None
