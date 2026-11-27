from pharma71_unified.sec_identity import resolve,verify_identity
from pharma71_unified.tdnet import parse_listing,allowed_pdf,BASE
def test_foreign_ticker_never_maps_to_unrelated_us_company():
    company={'ticker':'SAN','name':'Sanofi'}
    assert resolve(company,{'SAN':1}) is None
    m=resolve(company,{'SAN':1,'SNY':1121404})
    assert m['sec_ticker']=='SNY'
    assert verify_identity({'cik':1121404,'tickers':['SNY'],'name':'Sanofi'},m)
    assert not verify_identity({'cik':1121404,'tickers':['SNY'],'name':'Banco Santander SA'},m)
    assert resolve({'ticker':'CSL','name':'CSL'}, {'CSL':2}) is None
def test_tdnet_code_and_source():
    h='<table id="main-list-table"><tr><td class="kjTime">15:30</td><td class="kjCode">45680</td><td class="kjName">第一三共</td><td class="kjTitle"><a href="140120261127123456.pdf">開示資料</a></td></tr><tr><td class="kjTime">15:31</td><td class="kjCode">99990</td><td class="kjName">他社</td><td class="kjTitle"><a href="140120261127999999.pdf">他社資料</a></td></tr></table>'
    rows,pages=parse_listing(h,BASE+'I_list_001_20261127.html','2026-11-27')
    assert len(rows)==1 and rows[0]['ticker']=='4568 JP' and not rows[0]['original_confirmed']
    assert allowed_pdf(rows[0]['url']) and not allowed_pdf('https://www.release.tdnet.info.example.com/inbs/123.pdf')
