import sys,unittest,tempfile,json
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from pharma71_unified_mail import validated_audit
class TestFreshness(unittest.TestCase):
    def test_stale_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'audit.json').write_text(json.dumps({'start_jst':'2026-11-26T03:30:00+09:00'}))
            with self.assertRaisesRegex(ValueError,'STALE'):validated_audit(p,datetime(2026,11,27,5,21,tzinfo=ZoneInfo('Asia/Tokyo')),set())
    def test_future_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'audit.json').write_text(json.dumps({'start_jst':'2026-11-27T06:00:00+09:00'}))
            with self.assertRaisesRegex(ValueError,'STALE'):validated_audit(p,datetime(2026,11,27,5,21,tzinfo=ZoneInfo('Asia/Tokyo')),set())

    def test_actual_audit_format(self):
        p=Path('unified-staging/data/pharma71_unified')
        if not (p/'audit.json').is_file():self.skipTest('audit checkout unavailable')
        import csv
        from datetime import timedelta
        with open('companies.csv',encoding='utf-8-sig') as f:expected={r['Company'] for r in csv.DictReader(f)}
        a=json.loads((p/'audit.json').read_text())
        # Use the actual audited run as a fixture. Only time of day is shifted
        # for this offline test; it does not certify current-day live delivery.
        dt=datetime.fromisoformat(a['start_jst']).replace(hour=3,minute=30,second=0,microsecond=0)
        a['start_jst']=dt.isoformat()
        # For the offline fixture, shift the comparison-period cutoff too.
        for e in a['entries']:
            e['comparison_period']['start_jst']=dt.replace(hour=2).isoformat()
            e['comparison_period']['end_jst']=dt.isoformat()
        a['audit_date_jst']=dt.date().isoformat()
        with tempfile.TemporaryDirectory() as t:
            q=Path(t);(q/'audit.json').write_text(json.dumps(a))
            self.assertEqual(len(validated_audit(q,dt+timedelta(hours=1),expected)['entries']),71)
            from pharma71_unified_mail import section
            label,body=section(dt+timedelta(hours=1),q)
            self.assertIn('全71対象の判定',body)
            self.assertIn('未確認',label)
            a['summary']['period_verified']+=1
            (q/'audit.json').write_text(json.dumps(a))
            with self.assertRaisesRegex(ValueError,'COUNTS'):validated_audit(q,dt+timedelta(hours=1),expected)

    def test_cross_platform_reservation(self):
        from unittest.mock import patch,MagicMock
        from urllib.error import HTTPError
        from pharma71_delivery_lock import reserve
        now=datetime(2026,11,28,5,21,tzinfo=ZoneInfo('Asia/Tokyo'))
        with patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/repo','GH_TOKEN':'test'}),patch('pharma71_delivery_lock.urlopen') as op:
            op.return_value.__enter__.return_value.status=201
            self.assertTrue(reserve(now))
            req=op.call_args.args[0]
            self.assertTrue(req.full_url.endswith('/delivery/2026-11-28.json'))
            self.assertEqual(json.loads(req.data)['branch'],'pharma71-delivery-ledger')
            op.side_effect=HTTPError(req.full_url,422,'already exists',None,None)
            self.assertFalse(reserve(now))

    def test_delivery_window(self):
        from pharma71_delivery_lock import delivery_window
        for h,m,expected in [(5,9,False),(5,10,True),(5,24,True),(6,30,True),(6,31,False),(11,58,False)]:
            self.assertEqual(delivery_window(datetime(2026,11,28,h,m,tzinfo=ZoneInfo('Asia/Tokyo'))),expected)

    def test_overnight_history_survives_second_run(self):
        from pharma71_unified_mail import rolling_originals
        now=datetime(2026,11,28,5,21,tzinfo=ZoneInfo('Asia/Tokyo'))
        p={'original_confirmed':True,'url':'https://example.org/first','receipt':{'fetched_jst':'2026-11-28T01:45:00+09:00'}}
        old=dict(p,url='https://example.org/old',receipt={'fetched_jst':'2026-11-27T05:00:00+09:00'})
        future=dict(p,url='https://example.org/future',receipt={'fetched_jst':'2026-11-28T06:00:00+09:00'})
        with tempfile.TemporaryDirectory() as t:
            (Path(t)/'verified_original_history.json').write_text(json.dumps({'LLY':[p,p,old,future]}))
            self.assertEqual([r[2]['url'] for r in rolling_originals(t,now,set())],[p['url']])
            self.assertEqual(rolling_originals(t,now,{p['url']}),[])

    def test_unzoned_audit_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'audit.json').write_text(json.dumps({'start_jst':'2026-11-28T03:30:00'}))
            with self.assertRaisesRegex(ValueError,'UNZONED'):validated_audit(p,datetime(2026,11,28,5,21,tzinfo=ZoneInfo('Asia/Tokyo')),set())
