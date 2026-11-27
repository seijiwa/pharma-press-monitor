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
            if e['status']!='未確認':e['new_success_jst']=dt.isoformat()
        a['audit_date_jst']=dt.date().isoformat()
        with tempfile.TemporaryDirectory() as t:
            q=Path(t);(q/'audit.json').write_text(json.dumps(a))
            self.assertEqual(len(validated_audit(q,dt+timedelta(hours=1),expected)['entries']),71)
            from pharma71_unified_mail import section
            label,body=section(dt+timedelta(hours=1),q)
            self.assertIn('全71対象の判定',body)
            self.assertIn('買収済み3対象の親会社限定監視',body)
            self.assertIn('未確認',label)
            from pharma71_unified_mail import validate_scope_counts
            a['integrated_monitoring']['summary']['independent_newsroom_verified']+=1
            with self.assertRaisesRegex(ValueError,'INTEGRATED_COUNTS'):validate_scope_counts(a['integrated_monitoring'],a['summary']['period_verified'])
            a['integrated_monitoring']['summary']['independent_newsroom_verified']-=1
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
            with patch('pharma71_delivery_lock.ledger_exists',return_value=True):
                self.assertFalse(reserve(now))
            with patch('pharma71_delivery_lock.ledger_exists',return_value=False):
                with self.assertRaisesRegex(RuntimeError,'without confirmed reservation'):reserve(now)

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

    def test_daily_send_failure_does_not_acknowledge_or_retry(self):
        from unittest.mock import patch
        from smtplib import SMTPServerDisconnected
        import pharma71_email as m
        now=datetime(2026,11,28,5,21,tzinfo=ZoneInfo('Asia/Tokyo'))
        with patch.dict('os.environ',{'PHARMA71_GMAIL_USER':'test@example.org','PHARMA71_GMAIL_APP_PASSWORD':'fake'}),patch.object(m,'datetime') as clock,patch.object(m,'request_ref',return_value=404),patch.object(m,'reserve',return_value=True) as claim,patch.object(m,'mark_accepted') as ack,patch.object(m.smtplib,'SMTP') as smtp:
            clock.now.return_value=now
            smtp.return_value.__enter__.return_value.send_message.side_effect=SMTPServerDisconnected('unknown outcome')
            with self.assertRaises(SMTPServerDisconnected):m.deliver('daily',now,'test','body')
            claim.assert_called_once()
            ack.assert_not_called()
            smtp.return_value.__enter__.return_value.send_message.assert_called_once()
    def test_lost_reservation_does_not_send(self):
        from unittest.mock import patch
        import pharma71_email as m
        now=datetime(2026,11,28,5,21,tzinfo=ZoneInfo('Asia/Tokyo'))
        with patch.dict('os.environ',{'PHARMA71_GMAIL_USER':'test@example.org','PHARMA71_GMAIL_APP_PASSWORD':'fake'}),patch.object(m,'datetime') as clock,patch.object(m,'request_ref',return_value=404),patch.object(m,'reserve',return_value=False),patch.object(m,'mark_accepted') as ack,patch.object(m.smtplib,'SMTP') as smtp:
            clock.now.return_value=now
            m.deliver('daily',now,'test','body')
            smtp.return_value.__enter__.return_value.send_message.assert_not_called()
            ack.assert_not_called()

    def test_stale_audit_still_preserves_history_and_71_rows(self):
        from pharma71_unified_mail import section
        now=datetime(2026,11,28,5,21,tzinfo=ZoneInfo('Asia/Tokyo'))
        with tempfile.TemporaryDirectory() as t:
            q=Path(t)
            (q/'audit.json').write_text('broken json')
            (q/'verified_original_history.json').write_text(json.dumps({'LLY':[{'original_confirmed':True,'url':'https://example.org/release','receipt':{'fetched_jst':'2026-11-28T02:00:00+09:00'}}]}))
            (q/'companies.csv').write_text('Company\n'+'\n'.join('Company '+str(i) for i in range(71)))
            label,body=section(now,q,q/'companies.csv')
            self.assertEqual(label,'【統合監査未確認】')
            self.assertEqual(body.count('未確認（当日統合監査未検証）'),71)
            self.assertIn('https://example.org/release',body)

    def test_early_delivery_prefers_recent_audit_but_does_not_block_later(self):
        from pharma71_email import early_send_ready
        now=datetime(2026,11,28,5,11,tzinfo=ZoneInfo('Asia/Tokyo'))
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'audit.json'
            p.write_text(json.dumps({'start_jst':'2026-11-28T03:30:00+09:00'}))
            self.assertFalse(early_send_ready(now,t))
            self.assertTrue(early_send_ready(now.replace(minute=21),t))
            p.write_text(json.dumps({'start_jst':'2026-11-28T04:37:00+09:00'}))
            self.assertTrue(early_send_ready(now,t))

    def test_ledger_exists_requires_file_identity(self):
        from unittest.mock import patch
        from pharma71_delivery_lock import ledger_exists
        with patch.dict('os.environ',{'GITHUB_REPOSITORY':'owner/repo','GH_TOKEN':'fake'}),patch('pharma71_delivery_lock.urlopen') as op:
            r=op.return_value.__enter__.return_value
            r.status=200
            r.read.return_value=json.dumps({'type':'file','path':'delivery/test.json','sha':'abc'}).encode()
            self.assertTrue(ledger_exists('delivery/test.json'))
            r.read.return_value=json.dumps({'type':'dir','path':'delivery/test.json','sha':'abc'}).encode()
            with self.assertRaisesRegex(RuntimeError,'confirmed file'):ledger_exists('delivery/test.json')

    def test_deadline_crossed_after_reservation_does_not_send(self):
        from unittest.mock import patch
        import pharma71_email as m
        from pharma71_delivery_lock import delivery_window
        now=datetime(2026,11,28,6,30,tzinfo=ZoneInfo('Asia/Tokyo'))
        self.assertFalse(delivery_window(now.replace(tzinfo=None)))
        with patch.dict('os.environ',{'PHARMA71_GMAIL_USER':'test@example.org','PHARMA71_GMAIL_APP_PASSWORD':'fake'}),patch.object(m,'datetime') as clock,patch.object(m,'request_ref',return_value=404),patch.object(m,'reserve',return_value=True),patch.object(m,'mark_accepted') as ack,patch.object(m.smtplib,'SMTP') as smtp:
            clock.now.side_effect=[now,now.replace(minute=31)]
            with self.assertRaisesRegex(SystemExit,'window expired'):m.deliver('daily',now,'test','body')
            smtp.return_value.__enter__.return_value.send_message.assert_not_called()
            ack.assert_not_called()

    def test_legacy_clock_rejects_future_and_naive(self):
        from pharma71_email import checked_timestamp
        now=datetime(2026,11,28,5,21,tzinfo=ZoneInfo('Asia/Tokyo'))
        self.assertEqual(checked_timestamp('2026-11-27T20:21:00+00:00',now),now)
        for stamp in ('2026-11-28T05:22:00+09:00','2026-11-28T05:20:00'):
            with self.assertRaises(ValueError):checked_timestamp(stamp,now)

    def test_continuity_rejects_forged_gap_counts(self):
        from pharma71_unified_mail import validate_continuity
        order=['T'+str(i) for i in range(71)]
        a={'start_jst':'2026-11-28T04:37:00+09:00','expected_tickers':order}
        d={'window_start_jst':'2026-11-27T05:30:00+09:00','window_end_jst':a['start_jst'],'rows':[{'ticker':t,'status':'VERIFIED_TO_COLLECTION','gaps':[]} for t in order],'verified':71,'unconfirmed':0,'without_recovered_receipts_verified':71,'without_recovered_receipts_tickers':order}
        self.assertTrue(validate_continuity(d,a))
        d['verified']=70
        self.assertFalse(validate_continuity(d,a))
        d['verified']=71
        d['rows'][0]['gaps']=[{'start_jst':d['window_start_jst'],'end_jst':d['window_end_jst']}]
        self.assertFalse(validate_continuity(d,a))

    def test_yesterday_early_send_overlap_and_bad_timestamp(self):
        from pharma71_unified_mail import rolling_originals
        now=datetime(2026,11,28,5,21,tzinfo=ZoneInfo('Asia/Tokyo'))
        p={'original_confirmed':True,'url':'https://example.org/overlap','receipt':{'fetched_jst':'2026-11-27T05:15:00+09:00'}}
        bad=dict(p,url='https://example.org/bad',receipt={'fetched_jst':'not-a-date'})
        with tempfile.TemporaryDirectory() as t:
            (Path(t)/'verified_original_history.json').write_text(json.dumps({'LLY':[bad,p]}))
            warnings=[]
            self.assertEqual([r[2]['url'] for r in rolling_originals(t,now,set(),warnings)],[p['url']])
            self.assertEqual(warnings,['LLY'])
