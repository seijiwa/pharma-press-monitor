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


def load_independent_audit(data_dir, registry, day, latest):
    path = data_dir / f'pharma_monitor_{day.isoformat()}_audit.json'
    try:
        audit = json.loads(path.read_text(encoding='utf-8'))
        started = iso_dt(audit['start_jst'])
        completed = iso_dt(audit['completed_jst'])
        if (audit['audit_date_jst'] == day.isoformat()
                and audit['expected_tickers'] == ORDER
                and audit['source_scope'] == 'pharma46-independent'
                and audit['is_live_direct_http'] is True
                and started is not None and completed is not None
                and started.astimezone(JST).date() == day
                and started <= completed <= latest
                and not audit['qa_errors']
                and not validate_report(registry, audit['entries'])):
            return started, audit['entries']
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        pass
    return None, []


def verified_interval(entry, collection_time):
    if (entry['status'] == '未確認' or not entry.get('tool_evidence_ref')
            or not entry.get('new_success_jst')):
        return None
    period = entry.get('comparison_period', {})
    start = iso_dt(period.get('start_jst'))
    end = iso_dt(period.get('end_jst'))
    if start is not None and end is not None and start <= end <= collection_time:
        return start, end
    return None


def continuously_verified(intervals, start, end):
    cursor = start
    for left, right in sorted(i for i in intervals if i is not None):
        if left > cursor:
            break
        cursor = max(cursor, right)
        if cursor >= end:
            return True
    return False


def build_report(data_dir, registry, now):
    cutoff = datetime.combine(now.date(), time(5, 30), JST)
    yesterday = cutoff - timedelta(days=1)
    started, entries = load_independent_audit(data_dir, registry, cutoff.date(), min(cutoff, now))
    if started:
        earlier_start, earlier = load_independent_audit(data_dir, registry, yesterday.date(), started)
        prior = {item['ticker']: item for item in earlier}
        rows = []
        for entry in entries:
            previous = prior.get(entry['ticker'])
            current_interval = verified_interval(entry, started)
            prior_interval = verified_interval(previous, earlier_start) if previous else None
            if entry['status'] != '未確認' and not continuously_verified(
                    [prior_interval, current_interval], yesterday, started):
                entry = dict(entry, status='未確認', pagination_complete=False,
                             reason='前日05:30から収集基準時刻までに未確認区間あり')
            elif (entry['status'] == 'なし' and current_interval[0] > yesterday
                  and previous['status'] == 'あり'):
                # A prior run bridges the interval, but day-only publication dates
                # cannot establish which side of 05:30 its reports belong to.
                entry = dict(entry, status='未確認', reason='前回確認記事の公開時刻と05:30境界を照合できず',
                             primary_releases=previous['primary_releases'] + entry['primary_releases'])
            rows.append(entry)
        subject, body, summary = render_report(min(cutoff, now), rows, [], 'Pharma46 独立収集の保存済み監査')
        note = (f'報告対象（JST） {yesterday.isoformat()} ～ {min(cutoff, now).isoformat()}（配信目標05:30）。'
                f'期間網羅の判定は {started.isoformat()} まで。収集基準時刻から締切までは未確認。')
        body = body.replace('\n\n', f'\n\n{note}\n\n', 1)
        return subject, add_recent_originals(body, data_dir, min(cutoff, now)), summary

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
    if args.send and not (summary['period_verified'] or summary['primary_originals']):
        outcome = {'status': 'DEFERRED_NO_USABLE_CURRENT_EVIDENCE'}
    else:
        outcome = send_report(subject, body, now.date().isoformat()) if args.send else {'status': 'NO_MAIL'}
    print(json.dumps({'summary': summary, 'delivery': outcome}, ensure_ascii=False))
    # This runner has no recipient receipt. SMTP acceptance is an intermediate state.
    if args.send:
        if outcome['status'] not in ('SMTP_ACCEPTED', 'ALREADY_SENT_IMAP', 'NOT_SENT_ALREADY_RESERVED'):
            return 2
        print('Mail transport state recorded; actual recipient receipt still requires independent verification.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
