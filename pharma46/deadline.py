"""Build the Pharma46 deadline report from independently collected evidence."""
import argparse
import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path

from .engine import JST, ORDER, iso_dt, render_report, validate_report
from .delivery import send_report


def add_recent_originals(body, data_dir, cutoff):
    """Include recent prior observations even when a previous delivery is unverified."""
    try:
        records = json.loads((data_dir / 'pharma46_state.json').read_text(encoding='utf-8'))
        records = records.get('verified_originals', {})
    except (OSError, ValueError, AttributeError):
        return body
    lines = []
    for url, item in records.items():
        try:
            observed = iso_dt(item['observed_jst'])
            if cutoff - timedelta(days=2) < observed <= cutoff and url not in body:
                lines.append(f"- {item['ticker']} | {item['date']} | {item['title']} | {url}")
        except (KeyError, TypeError, ValueError):
            continue
    if not lines:
        return body
    return body + '\n## 最近確認した一次原文（配信済みかは未照合）\n' + '\n'.join(sorted(lines)) + '\n'


def build_report(data_dir, registry, now):
    cutoff = datetime.combine(now.date(), time(5, 30), JST)
    path = data_dir / f'pharma_monitor_{now.date().isoformat()}_audit.json'
    try:
        audit = json.loads(path.read_text(encoding='utf-8'))
        started = iso_dt(audit['start_jst'])
        completed = iso_dt(audit['completed_jst'])
        entries = audit['entries']
        if (audit['audit_date_jst'] == now.date().isoformat()
                and audit['expected_tickers'] == ORDER
                and audit['source_scope'] == 'pharma46-independent'
                and audit['is_live_direct_http'] is True
                and cutoff - timedelta(hours=24) <= started <= completed <= min(cutoff, now)
                and not audit['qa_errors']
                and not validate_report(registry, entries)):
            subject, body, summary = render_report(cutoff, entries, [], 'Pharma46 独立収集の保存済み監査')
            note = (f'収集の基準時刻（JST） {started.isoformat()}。'
                    '期間網羅の判定は収集の基準時刻まで。基準時刻から配信締切までは未確認。')
            body = body.replace('\n\n', f'\n\n{note}\n\n', 1)
            return subject, add_recent_originals(body, data_dir, cutoff), summary
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass

    entries = [{
        'ticker': ticker,
        'status': '未確認',
        'homepage_visit_status': '未訪問',
        'latest_publication_date': None,
        'pagination_complete': False,
        'stale_cache_status': None,
        'primary_releases': [],
        'reason': '締切時点で使用可能な当日の独立46社監査なし',
    } for ticker in ORDER]
    subject, body, summary = render_report(cutoff, entries, [], 'Pharma46 締切時点の監査未取得')
    return subject, add_recent_originals(body, data_dir, min(cutoff, now)), summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', action='store_true', help='Require the scheduled delivery opt-in')
    args = parser.parse_args()
    if args.send and (os.getenv('GITHUB_EVENT_NAME') != 'schedule'
                      or os.getenv('PHARMA46_DEADLINE_DELIVERY') != 'true'):
        parser.error('real delivery requires the scheduled job and explicit opt-in')
    now = datetime.now(JST)
    registry = json.loads(Path('pharma46/sources.json').read_text(encoding='utf-8'))
    subject, body, summary = build_report(Path('data'), registry, now)
    Path('pharma46-deadline-report.md').write_text(body, encoding='utf-8')
    outcome = send_report(subject, body, now.date().isoformat()) if args.send else {'status': 'NO_MAIL'}
    print(json.dumps({'summary': summary, 'delivery': outcome}, ensure_ascii=False))
    # This runner has no recipient receipt. SMTP acceptance is an intermediate state.
    return 2 if args.send else 0


if __name__ == '__main__':
    raise SystemExit(main())
