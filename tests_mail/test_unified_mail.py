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
