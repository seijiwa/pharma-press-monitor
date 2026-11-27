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
