"""Morning mail attachment text, fail closed on stale/malformed audit."""
import csv,json
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
TOKYO=ZoneInfo("Asia/Tokyo")
HISTORICAL={'RNA','REATA','JNANA'}

def validated_audit(root,now,expected_names):
    root=Path(root)
    a=json.loads((root/'audit.json').read_text(encoding='utf-8'))
    started=datetime.fromisoformat(a['start_jst'])
    if started.tzinfo is None:raise ValueError('UNZONED_AUDIT')
    started=started.astimezone(TOKYO)
    # The daily 03:30 JST collection must be current, not an old manual run.
    if started.date()!=now.date() or started.hour<1 or started>now or now-started>timedelta(hours=5):
        raise ValueError('STALE_OR_OUTSIDE_MORNING_WINDOW')
    if a.get('audit_date_jst')!=now.date().isoformat():raise ValueError('WRONG_AUDIT_DATE')
    if a.get('qa_errors')!=[]:raise ValueError('STRUCTURAL_QA_FAILURE')
    if not str(a.get('run_id','')).isdigit():raise ValueError('NOT_GITHUB_AUDIT')
    entries=a['entries'];order=a['expected_tickers'];names=[e['company_name'] for e in entries]
    if len(entries)!=71 or len(set(order))!=71 or [e['ticker'] for e in entries]!=order or len(set(names))!=71 or set(names)!=expected_names:raise ValueError('UNIVERSE_MISMATCH')
    passed=0
    for e in entries:
        if e['status'] not in ('あり','なし','未確認'):raise ValueError('UNKNOWN_STATUS')
        if e['status']!='未確認':
            if not (e['pagination_complete'] and e['listing_page_urls_checked'] and e['new_success_jst'] and not e['stale_cache_status']):raise ValueError('COVERAGE_RECEIPT_MISSING')
            passed+=1
    if a['summary']['period_verified']!=passed or a['summary']['unconfirmed']!=71-passed:raise ValueError('COUNTS_MISMATCH')
    reg=a.get('regulatory_observations',{})
    if reg.get('run_id')!=a['run_id'] or reg.get('newsroom_coverage_credit') is not False:raise ValueError('REGULATORY_RUN_MISMATCH')
    scope=a['integrated_monitoring']
    if [x['ticker'] for x in scope['rows']]!=order:raise ValueError('SCOPE_MISMATCH')
    for e,x in zip(entries,scope['rows']):
        if x.get('newsroom_period_verified') is not (e['status']!='未確認'):raise ValueError('SCOPE_DIRECT_MISMATCH')
        p=e['comparison_period'];s=datetime.fromisoformat(p['start_jst']);z=datetime.fromisoformat(p['end_jst'])
        if s.tzinfo is None or z.tzinfo is None or not s<=z<=now:raise ValueError('INVALID_COMPARISON_PERIOD')
    return a

def rolling_originals(root,now,seen):
    """Retain first observations across multiple collection runs. Date-only
    publications are not represented as exact publication timestamps."""
    history=json.loads((Path(root)/'verified_original_history.json').read_text(encoding='utf-8'))
    if not isinstance(history,dict):raise ValueError('invalid original history')
    cutoff=(now-timedelta(days=1)).replace(hour=5,minute=30,second=0,microsecond=0)
    rows=[]
    for ticker,items in history.items():
        for p in items:
            if p.get('original_confirmed') is not True or not p.get('url') or p['url'] in seen:continue
            stamp=p.get('receipt',{}).get('fetched_jst')
            if not stamp:continue
            dt=datetime.fromisoformat(stamp)
            if dt.tzinfo is None:continue
            dt=dt.astimezone(TOKYO)
            if cutoff<dt<=now:
                rows.append((dt,ticker,p))
                seen.add(p['url'])
    return sorted(rows,key=lambda x:x[0],reverse=True)

def unavailable_section(now,root,csv_path,reason):
    lines=[f'統合監査: 当日分の検証済み結果を取得できませんでした ({reason})。発表なしとは判定しません。',
           '【取得済み原文の履歴（当日監査未確認、前回朝以降の初回確認）】']
    try:
        rows=rolling_originals(root,now,set())
        for stamp,ticker,p in rows:
            lines.append(f'・{ticker} | 初回確認 {stamp:%m/%d %H:%M} JST | 発表日 {p.get("published_date")} | {p.get("original_title")}\n  {p["url"]}')
        if not rows:lines.append('該当原文なし（保存履歴の範囲のみ）。')
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        lines.append('原文履歴未確認。')
    lines+=['','【全71対象の当日統合監査判定】']
    try:
        with open(csv_path,encoding='utf-8-sig',newline='') as f:names=[r['Company'] for r in csv.DictReader(f)]
        if len(names)!=71 or len(set(names))!=71:raise ValueError('invalid universe')
        lines.extend(f'・{name} | 未確認（当日統合監査未検証）' for name in names)
    except (OSError,ValueError,KeyError,TypeError):
        lines.append('71対象の名簿も取得できませんでした。')
    lines+=['','以下の従来監視は補助情報のみです。','']
    return '\n'.join(lines)

def section(now,root='unified-staging/data/pharma71_unified',csv_path='companies.csv'):
    try:
        with open(csv_path,encoding='utf-8-sig',newline='') as f:expected={r['Company'] for r in csv.DictReader(f)}
        a=validated_audit(root,now,expected)
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as exc:
        return '【統合監査未確認】',unavailable_section(now,root,csv_path,type(exc).__name__)
    s=a['summary'];reg=a['regulatory_observations'];scope=a['integrated_monitoring'];ss=scope['summary'];rs=reg.get('summary',{})
    lines=['【当日71対象・統合監査】',f'取得基準: {a["start_jst"]} / GitHub run {a["run_id"]}',f'公式一覧期間確認 {s["period_verified"]}/71 / 未確認 {s["unconfirmed"]} / 構造QAエラー0',
           f'独立企業 {ss["independent"]}: 公式一覧 {ss["independent_newsroom_verified"]}, SECのみ {ss["independent_sec_only"]}, 両方未確認 {ss["independent_no_verified_period"]}',
           f'買収済み対象 {ss["historical"]}: 親会社一覧限定確認 {ss["parent_limited"]}, 未確認 {ss["parent_unconfirmed"]}',
           f'SEC: {reg.get("status")} / 開示期間確認 {rs.get("filing_windows_verified",0)} / 開示 {rs.get("filings",0)}件 / 原文添付資料 {rs.get("verified_exhibits",0)}件',
           'SECの確認範囲は8-K/6-Kであり、公式ニュース全体の網羅確認ではありません。',
           '', '【公式発表原文】']
    seen=set()
    for e in a['entries']:
        for p in e.get('primary_releases',[]):
            if p.get('original_confirmed') is not True or not p.get('url') or p['url'] in seen:continue
            seen.add(p['url']);lines.append(f'・{e["ticker"]} | {p.get("new_status","新規性未判定")} | {p.get("published_date")} | {p.get("original_title")}\n  {p["url"]}')
    if not seen:lines.append('今回取得分の確認原文0件。未確認企業で発表がないことを意味しません。')
    lines+=['','【前回朝05:30以降に初回確認した原文（先行取得分を含む）】','確認時刻を基準とした履歴です。発表日がそれ以前のものもあり、新規発表とは限りません。']
    try:
        earlier=rolling_originals(root,now,seen)
        for dt,ticker,p in earlier:
            lines.append(f'・{ticker} | 初回確認 {dt:%m/%d %H:%M} JST | 発表日 {p.get("published_date")} | {p.get("original_title")}\n  {p["url"]}')
        if not earlier:lines.append('今回分以外の該当する確認原文なし（履歴内のみ）。')
    except (OSError,ValueError,TypeError,KeyError,AttributeError):
        lines.append('取得履歴未確認。先行取得分の完全性を保証できません。')
    lines.append('以下の企業別期間判定は最新取得分の比較期間であり、前回配信以降全体の網羅性ではありません。')
    lines+=['','【SEC提出書類・原文添付資料（会社発表とは別）】']
    for e in reg.get('entries',[]):
        if not e.get('issuer_identity_verified'):continue
        for x in e.get('filings',[]):lines.append(f'・{e["ticker"]} | {x["form"]} | filing date {x["filing_date"]}\n  {x["url"]}')
        for d in e.get('exhibit_results',[]):
            for x in d.get('exhibits',[]):
                if x.get('original_confirmed') is True:lines.append(f'  SEC提出添付資料: {x.get("description") or x.get("type","EX-99")} | {x["url"]}')
    for key in ('tdnet','hkex','eqs'):
        r=reg.get(key,{});z=r.get('summary',{})
        lines+=['',f'【{key.upper()}補完開示】 {r.get("status","NOT_RUN")} | 候補 {z.get("disclosure_candidates",0)}件 / 原文 {z.get("verified_originals",0)}件']
        for x in r.get('entries',[]):
            lines.append(f'・{x["ticker"]} | {x.get("published_date") or x.get("published_jst") or x.get("published_hkt_raw")} | {x.get("title")} | {"原文確認" if x.get("original_confirmed") else "候補のみ"}\n  {x.get("url") or "URL未確認"}')
    daily=a.get('daily_newsroom_coverage',{})
    if daily.get('window_end_jst')==a['start_jst'] and [r.get('ticker') for r in daily.get('rows',[])]==a['expected_tickers']:
        lines+=['','【前回朝から今回取得までの連続網羅】',
                f'{daily["window_start_jst"]} ～ {daily["window_end_jst"]} | 連続確認 {daily["verified"]}/71 | 未確認区間あり {daily["unconfirmed"]}/71',
                f'復元記録に依存しない連続確認: {daily.get("without_recovered_receipts_verified","未検証")}社。復元した原文の再照合は未実施。',
                '公式一覧のみの判定。SEC補完は加算しない。最終取得から配信までの区間は未確認。']
        for r in daily['rows']:
            if r['gaps']:lines.append('・'+r['ticker']+' | '+'; '.join(g['start_jst']+' ～ '+g['end_jst'] for g in r['gaps']))
    else:lines+=['','【前回朝からの連続網羅】未検証。最新取得分の判定とは別。']
    lines+=['','【全71対象の判定】']
    for e,x in zip(a['entries'],scope['rows']):
        period=e['comparison_period']
        lines.append(f'・{e["ticker"]} {e["company_name"]} | {e["status"]} | {x["status"]} | {period["start_jst"]} ～ {period["end_jst"]} | {e["reason"]}')
    lines+=['','【以下は従来監視による補助情報（原文・期間網羅とは別）】','']
    return ('【統合監査・未確認あり】' if not a['qa_pass'] else '【統合監査済】'),'\n'.join(lines)
