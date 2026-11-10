import csv,sys
from pathlib import Path
p=Path(__file__).resolve().parent
r=list(csv.DictReader(open(p/'companies.csv',encoding='utf-8-sig')))
assert len(r)==71, len(r)
assert all(x['Official/Source page'].startswith('http') for x in r)
assert len({x['Company'] for x in r})==71
b=[x for x in r if x['Company']=='Biogen']; assert len(b)==1 and 'biogen' in b[0]['Official/Source page'].lower()
print('PASS: 71/71 unique companies; all official source URLs populated; Biogen included:',b[0]['Official/Source page'])

# These tests use temporary files only; no test articles reach published feeds.
import contextlib,io,json,tempfile,xml.etree.ElementTree as ET
import run as monitor
from unittest.mock import patch

def article(url,title):return {'url':url,'title':title,'score':5}
fixture='<nav><a href="/news/menu-not-a-press-release">Menu entry</a></nav><a href="/news-releases/news-release-details/new-release" aria-label="Read more about Biogen Announces New Clinical Results"></a>'
items=monitor.candidates('https://investors.biogen.com/news',fixture)
assert len(items)==1 and items[0]['title']=='Biogen Announces New Clinical Results'
assert monitor.candidates('https://akesobio.com/en/media/akeso-news/','<a href="/en/media/akeso-news/261105/" title="Akeso Announces New Clinical Results"></a>')
assert monitor.candidates('https://www.daiichisankyo.com/media/press_release/','<a href="/files/news/pressrelease/pdf/202610/20261030_E.pdf">Daiichi Sankyo Announces New Clinical Results</a>')
fixture='<div class="data_row"><div class="data_title">2026.11.09</div><div class="div_content">Innovent Announces Phase 3 Results</div><div><a href="/InvestorsAndMedia/PressReleaseDetail?key=623">Discover More</a></div></div>'
assert monitor.candidates('https://en.innoventbio.com/InvestorsAndMedia/PressRelease',fixture)[0]['title']=='Innovent Announces Phase 3 Results'
fixture='<div class="item href"><p class="time">2026-11-10</p><h3>Kelun Announces New Clinical Results</h3></div>'
assert monitor.candidates('https://en.kelun-biotech.com/newsCenter.aspx?mid=18',fixture)[0]['key'].startswith('https://en.kelun-biotech.com/newsCenter.aspx?mid=18#release-')

with tempfile.TemporaryDirectory() as directory:
    root=Path(directory)
    with (root/'companies.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=r[0].keys());writer.writeheader();writer.writerow(r[0])
    replacement={'ROOT':root,'DATA':root/'data','DOCS':root/'docs','STATE':root/'data/state.json','EVENTS':root/'data/events.json','STATUS':root/'data/status.json'}
    with contextlib.ExitStack() as stack:
        for name,value in replacement.items():stack.enter_context(patch.object(monitor,name,value))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        source=r[0]['Official/Source page']
        one=article('https://news.abbvie.com/2026-11-01-existing','Existing release')
        two=article('https://news.abbvie.com/2026-11-02-new','New release & XML characters')
        with patch.object(monitor,'collect',return_value=(source,'test',[one])):monitor.main()
        assert json.loads(monitor.EVENTS.read_text())==[]
        with patch.object(monitor,'collect',return_value=(source,'test',[one,two])):monitor.main();monitor.main()
        assert len(json.loads(monitor.EVENTS.read_text()))==1
        assert len(ET.parse(root/'docs/feed.xml').findall('.//item'))==1
        before=monitor.STATE.read_text()
        with patch.object(monitor,'collect',side_effect=RuntimeError('test unavailable')):
            try:monitor.main()
            except SystemExit as e:assert e.code==2
            else:raise AssertionError('Failed source must fail the run')
        assert monitor.STATE.read_text()==before
        assert json.loads(monitor.STATUS.read_text())[r[0]['Company']]['status']=='FAIL'
        assert len(ET.parse(root/'docs/feed.xml').findall('.//item'))==1
print('PASS: article parsers, first-run baseline, new detection, deduplication, RSS XML, and failure preservation')
