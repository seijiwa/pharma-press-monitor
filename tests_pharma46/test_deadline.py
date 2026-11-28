import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from pharma46 import delivery
from pharma46.deadline import build_report, continuously_verified


def test_missing_or_cross_scope_audit_is_unconfirmed(tmp_path):
    registry = json.loads(Path('pharma46/sources.json').read_text())
    now = datetime(2026, 11, 28, 5, 30, tzinfo=delivery.JST)
    old = json.loads(Path('data/pharma_monitor_2026-11-28_audit.json').read_text())
    old.update(start_jst='2026-11-28T04:07:00+09:00', completed_jst='2026-11-28T05:29:59+09:00')
    for item in old['entries']:
        item['comparison_period'] = {'start_jst': '2026-11-27T05:30:00+09:00',
                                     'end_jst': '2026-11-28T04:07:00+09:00'}
    path = tmp_path / 'pharma_monitor_2026-11-28_audit.json'
    for scope, verified in [('pharma71', 0), ('pharma46-independent', old['summary']['period_verified'])]:
        old['source_scope'] = scope
        path.write_text(json.dumps(old))
        _, body, summary = build_report(tmp_path, registry, now)
        assert summary['period_verified'] == verified
        assert summary['unconfirmed'] == 46 - verified
        assert body.count('|未確認|') == 46 - verified
    old['completed_jst'] = '2026-11-28T05:30:01+09:00'
    path.write_text(json.dumps(old))
    assert build_report(tmp_path, registry, now)[2]['unconfirmed'] == 46


def configure_fake_mail(monkeypatch):
    for name in ('MAIL_USER', 'MAIL_TO', 'MAIL_APP_PASSWORD'):
        monkeypatch.setenv(name, 'fixture@example.invalid')
    monkeypatch.setattr(delivery, 'already_sent', lambda *_: False)
    smtp = MagicMock()
    smtp.return_value.__enter__.return_value.send_message.return_value = {}
    monkeypatch.setattr(delivery.smtplib, 'SMTP', smtp)
    return smtp


def test_outside_window_never_connects_to_smtp(monkeypatch):
    smtp = configure_fake_mail(monkeypatch)
    assert delivery.send_report('example', 'body', '2000-01-01')['status'] == 'NOT_SENT_OUTSIDE_WINDOW'
    smtp.assert_not_called()


def test_one_reservation_and_separate_smtp_acceptance(monkeypatch):
    smtp = configure_fake_mail(monkeypatch)
    monkeypatch.setattr(delivery, 'scheduled_window', lambda *_: True)
    paths = set()

    def create_once(path, payload, **kwargs):
        if path in paths:
            return False
        paths.add(path)
        return True

    monkeypatch.setattr(delivery, 'create_once', create_once)
    first = delivery.send_report('example', 'body', '2026-11-28')
    second = delivery.send_report('example', 'body', '2026-11-28')
    assert first['status'] == 'SMTP_ACCEPTED'
    assert first['recipient_inbox_verified'] is False
    assert second['status'] == 'NOT_SENT_ALREADY_RESERVED'
    assert paths == {'delivery46/2026-11-28.json', 'delivery46/2026-11-28-accepted.json'}
    smtp.return_value.__enter__.return_value.send_message.assert_called_once()


def test_window_closes_during_reservation(monkeypatch):
    smtp = configure_fake_mail(monkeypatch)
    monkeypatch.setattr(delivery, 'scheduled_window', MagicMock(side_effect=[True, True, False]))
    monkeypatch.setattr(delivery, 'create_once', MagicMock(return_value=True))
    outcome = delivery.send_report('example', 'body', '2026-11-28')
    assert outcome['status'] == 'RESERVED_WINDOW_CLOSED'
    smtp.return_value.__enter__.return_value.send_message.assert_not_called()


def test_smtp_failure_keeps_reservation_and_never_retries(monkeypatch):
    smtp = configure_fake_mail(monkeypatch)
    smtp.return_value.__enter__.return_value.send_message.side_effect = TimeoutError
    monkeypatch.setattr(delivery, 'scheduled_window', lambda *_: True)
    claim = MagicMock(side_effect=[True, False])
    monkeypatch.setattr(delivery, 'create_once', claim)
    first = delivery.send_report('example', 'body', '2026-11-28')
    second = delivery.send_report('example', 'body', '2026-11-28')
    assert first['status'] == 'RESERVED_SMTP_OUTCOME_UNKNOWN'
    assert second['status'] == 'NOT_SENT_ALREADY_RESERVED'
    smtp.return_value.__enter__.return_value.send_message.assert_called_once()


def test_originals_remain_available_without_current_audit(tmp_path):
    registry = json.loads(Path('pharma46/sources.json').read_text())
    now = datetime(2026, 11, 28, 5, 30, tzinfo=delivery.JST)
    release = {'ticker': 'LLY', 'date': '2026-11-27', 'title': 'Fixture'}
    (tmp_path / 'pharma46_state.json').write_text(json.dumps({'verified_originals': {
        'https://example.invalid/confirmed': {**release, 'observed_jst': '2026-11-27T06:00:00+09:00'},
        'https://example.invalid/late': {**release, 'observed_jst': '2026-11-28T05:31:00+09:00'},
    }}))
    _, body, summary = build_report(tmp_path, registry, now)
    assert 'https://example.invalid/confirmed' in body
    assert 'https://example.invalid/late' not in body
    assert summary['unconfirmed'] == 46



def test_interval_merge_requires_touching_or_overlap():
    start = datetime(2026, 11, 27, 5, 30, tzinfo=delivery.JST)
    middle = start.replace(hour=8)
    end = start.replace(day=28, hour=4)
    assert continuously_verified([(middle, end), (start, middle)], start, end)
    assert not continuously_verified([(start, middle), (middle.replace(minute=31), end)], start, end)
    assert not continuously_verified([(middle, end)], start, end)
