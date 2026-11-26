"""Safety regression tests for GitHub staging and delivery switch."""
from pathlib import Path
import json

def test_schedule_cannot_send_before_cutover():
    workflow=Path('.github/workflows/pharma46.yml').read_text(encoding='utf-8')
    assert "vars.PHARMA_ENABLE_DELIVERY == 'true'" in workflow
    assert "github.event_name == 'schedule' || inputs.send_email" not in workflow
    assert "github.event_name == 'workflow_dispatch' && inputs.send_email == true" in workflow
    assert "runs-on: ubuntu-24.04" in workflow
    assert "continue-on-error: true" in workflow

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
    result=send_report('TEST NEVER SEND','No messages', '2026-11-25',ledger_path=tmp_path/'ledger.json')
    assert result['status']=='NOT_CONFIGURED'
    assert result['message_id'] is None
    assert not (tmp_path/'ledger.json').exists()
