import pytest,json
from pharma71_unified.hkex import resolve_ids,parse_rows,pdf_url
def test_stock_id_separate_from_code():
    assert resolve_ids([{'c':'06990','i':'1234'}])=={'06990':'1234'}
    with pytest.raises(ValueError):resolve_ids([{'c':'06990','i':'1234'},{'c':'06990','i':'4567'}])
def test_exchange_exact_issuer_date():
    row={'STOCK_CODE':'06990','STOCK_NAME':'KELUN-BIOTECH','TITLE':'Voluntary announcement','DATE_TIME':'27/11/2026 08:30','FILE_LINK':'/listedco/listconews/sehk/2026/1127/a.pdf'}
    r=parse_rows({'result':json.dumps([row])},'06990','2026-11-24','2026-11-27')
    assert len(r)==1 and not r[0]['original_confirmed'] and r[0]['url'].endswith('a.pdf')
    with pytest.raises(ValueError):parse_rows({'result':json.dumps([dict(row,STOCK_CODE='09926')])},'06990','2026-11-24','2026-11-27')
    with pytest.raises(ValueError):parse_rows({'result':json.dumps([dict(row,DATE_TIME='23/11/2026')])},'06990','2026-11-24','2026-11-27')
    assert not pdf_url('https://www1.hkexnews.hk.example.com/listedco/listconews/a.pdf')
