"""Safety regression tests for GitHub staging and delivery switch."""
from pathlib import Path
import json

def test_schedule_and_push_delivery_isolation():
    workflow=Path('.github/workflows/pharma46.yml').read_text(encoding='utf-8')
    deadline=Path('.github/workflows/pharma46-deadline.yml').read_text(encoding='utf-8')
    assert '--send' not in workflow
    assert 'MAIL_APP_PASSWORD' not in workflow
    assert "github.event_name == 'schedule' && vars.PHARMA46_DEADLINE_DELIVERY != 'false'" in deadline
    assert "12 20 * * *" in deadline and "17 20 * * *" in deadline
    assert "Generate deadline preview (no mail)" in deadline


def test_registry_order_and_safety():
    from pharma46.engine import ORDER
    companies=json.loads(Path('pharma46/sources.json').read_text(encoding='utf-8'))['companies']
    assert len(companies)==len(set(x['ticker'] for x in companies))==46
    assert [x['ticker'] for x in companies]==ORDER
    assert 'kelun-biotech.com' in companies[ORDER.index('6990 HK')]['official_indexes'][0]
    assert 'antengene.com' not in json.dumps(companies).lower()

def test_mail_requires_config_and_cannot_claim_success(tmp_path,monkeypatch):
    from pharma46.delivery import send_report
    for key in ('MAIL_USER','MAIL_APP_PASSWORD','MAIL_TO'):
        monkeypatch.delenv(key,raising=False)
    result=send_report('TEST NEVER SEND','No messages', '2026-11-25')
    assert result['status']=='NOT_CONFIGURED'


def test_daily_window_and_cross_sender_subjects():
    from pharma46.delivery import scheduled_window,same_report_subject,JST
    from datetime import datetime
    assert scheduled_window('2026-11-28',datetime(2026,11,28,5,10,tzinfo=JST))
    assert scheduled_window('2026-11-28',datetime(2026,11,28,5,19,tzinfo=JST))
    assert not scheduled_window('2026-11-28',datetime(2026,11,28,5,9,tzinfo=JST))
    assert not scheduled_window('2026-11-28',datetime(2026,11,28,5,30,tzinfo=JST))
    assert not scheduled_window('2026-11-28',datetime(2026,11,28,5,20,tzinfo=JST))
    assert not scheduled_window('2026-11-28',datetime(2026,11,29,5,12,tzinfo=JST))
    assert same_report_subject('製薬公式監視 2026-11-28【暫定・未確認46社】','2026-11-28')
    assert not same_report_subject('【製薬71社】2026/11/28 公式発表監視','2026-11-28')
    assert not same_report_subject('【テスト】製薬公式監視 2026-11-28','2026-11-28')
