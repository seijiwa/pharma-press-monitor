import pytest
from pharma71_unified.sec_exhibits import directory,allowed,exhibit_links,summarize,extract_body
F={'issuer_cik':123,'accession':'0000000123-26-000001','filing_date':'2026-11-27'}
def row(desc,href,kind):
    return f'<tr><td>2</td><td>{desc}</td><td><a href="{href}">doc</a></td><td>{kind}</td><td>1000</td></tr>'
def test_accession_scoped_exhibit_links():
    base=directory(F)
    h='<table class="tableFile">'+row('Press Release','ex99.htm','EX-99.1')+row('Wrong issuer','/Archives/edgar/data/999/000000099926000001/ex99.htm','EX-99.1')+row('Other','form.htm','8-K')+row('PDF','ex99.pdf','EX-99.2')+'</table>'
    rows=exhibit_links(h,F)
    assert len(rows)==1 and rows[0]['url']==base+'ex99.htm' and rows[0]['press_release_label']
    assert not allowed(base+'../x.htm',base)
    assert not allowed(base+'ex99.htm?x=1',base)
def test_exhibit_summary_never_counts_as_newsroom_coverage():
    r={'entries':[{'status':'FILING_METADATA_RETRIEVED','filings':[F],'exhibit_results':[{'exhibits':[{'original_confirmed':True,'press_release_label':True},{'original_confirmed':False}]}]},{'status':'NO_CURRENT_SEC_TICKER_MAPPING'}]}
    s=summarize(r)
    assert s['mapped']==1 and s['verified_exhibits']==1 and s['filing_windows_verified']==1
def test_remove_scripts():
    assert extract_body('<html><body><script>bad</script><div>Issuer document</div></body></html>')=='Issuer document'
