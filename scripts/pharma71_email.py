"""Build and deliver the Pharma71 daily source-health report."""
import csv
import json
import os
import smtplib
import ssl
import sys
from collections import Counter
from datetime import datetime, timedelta
from email.message import EmailMessage
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

TOKYO = ZoneInfo("Asia/Tokyo")
SITE = "https://seijiwa.github.io/pharma-press-monitor/"
LABELS = {"OK": "公式ページ取得", "RSS_ONLY": "公式RSSのみ", "FAIL": "未確認（取得失敗）"}


def report(now):
    with open("companies.csv", encoding="utf-8-sig", newline="") as file:
        companies = [row["Company"] for row in csv.DictReader(file)]
    statuses = json.loads(Path("data/status.json").read_text())
    if len(set(companies)) != 71 or set(statuses) != set(companies):
        raise ValueError("Expected a status for each of the 71 configured companies")
    checked = [datetime.fromisoformat(row["checked_at"]) for row in statuses.values()]
    latest = max(checked).astimezone(TOKYO)
    counts = Counter(row["status"] for row in statuses.values())
    if counts.keys() - LABELS.keys():
        raise ValueError("Unknown source status")
    missing = counts["FAIL"] + counts["RSS_ONLY"]
    stale = now - latest > timedelta(minutes=90)
    subject = f"【製薬71社】{now:%Y/%m/%d} 公式発表監視"
    if missing or stale:
        subject += "【未確認・一部確認あり】"
    lines = [
        f"集計時刻（日本時間） {now:%Y/%m/%d %H:%M}",
        f"最新の取得記録（日本時間） {latest:%Y/%m/%d %H:%M}",
        " / ".join(f"{label} {counts[key]}社" for key, label in LABELS.items()),
        "取得失敗や一覧の未確認範囲では、発表の有無を判定できません。",
        SITE,
    ]
    if stale:
        lines.append("最新の取得記録が90分以上前です。掲載の有無は未確認です。")
    lines.extend(["", "直近24時間に監視が検出した掲載（発表日時とは別）"])
    events = json.loads(Path("data/events.json").read_text())
    recent = [
        event for event in events
        if now - timedelta(hours=24) < datetime.fromisoformat(event["detected_at"]) <= now
    ]
    for event in sorted(recent, key=lambda item: item["detected_at"], reverse=True):
        lines.append(f"・{event['company']} {event['title']}\n  {event['url']}")
    if not recent:
        lines.append("期間内の新規検出記録はありません。")
    lines.extend(["", "全71社の取得状況"])
    for company in companies:
        row = statuses[company]
        stamp = datetime.fromisoformat(row["checked_at"]).astimezone(TOKYO)
        lines.append(f"・{company} | {LABELS[row['status']]} | {stamp:%m/%d %H:%M} JST")
    return subject, "\n".join(lines) + "\n"


def request_ref(tag, create=False):
    base = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/git"
    path = "/refs" if create else f"/ref/tags/{tag}"
    payload = {"ref": f"refs/tags/{tag}", "sha": os.environ["GITHUB_SHA"]}
    request = Request(base + path, data=json.dumps(payload).encode() if create else None,
                      headers={"Authorization": f"Bearer {os.environ['GH_TOKEN']}",
                               "Accept": "application/vnd.github+json",
                               "Content-Type": "application/json"})
    try:
        with urlopen(request, timeout=20) as response:
            return response.status
    except HTTPError as error:
        if (not create and error.code == 404) or (create and error.code == 422):
            return error.code
        raise


def deliver(mode, now, subject, body):
    address = os.environ.get("PHARMA71_GMAIL_USER", "").strip()
    password = "".join(os.environ.get("PHARMA71_GMAIL_APP_PASSWORD", "").split())
    if not address or not password:
        raise SystemExit("Required GitHub secrets: PHARMA71_GMAIL_USER and PHARMA71_GMAIL_APP_PASSWORD")
    tag = f"pharma71-{mode}-{now:%Y-%m-%d}"
    if request_ref(tag + "-accepted") == 200:
        print("Already accepted for this date. Skipping duplicate.")
        return
    if request_ref(tag + "-reserved") == 200:
        raise SystemExit("A prior attempt reserved this date. Check Gmail before any retry.")
    message = EmailMessage()
    message["From"] = address
    message["To"] = address
    message["Subject"] = f"【テスト】{subject}" if mode == "test" else subject
    message["Message-ID"] = f"<{tag}@pharma-press-monitor.github.io>"
    message.set_content(body)
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=25) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.user, smtp.password = address, password
        smtp.auth("LOGIN", smtp.auth_login, initial_response_ok=False)
        if request_ref(tag + "-reserved", create=True) != 201:
            raise SystemExit("The date could not be reserved. Delivery stopped.")
        if smtp.send_message(message):
            raise SystemExit("Gmail did not accept the recipient.")
        if request_ref(tag + "-accepted", create=True) != 201:
            raise SystemExit("Gmail accepted the message. Check Gmail before retrying.")
        print("Gmail accepted the message.")


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode not in {"preview", "test", "daily"}:
        raise SystemExit("Invalid delivery mode")
    now = datetime.now(TOKYO)
    subject, body = report(now)
    if mode == "preview":
        print(subject)
        print(body)
    else:
        deliver(mode, now, subject, body)
