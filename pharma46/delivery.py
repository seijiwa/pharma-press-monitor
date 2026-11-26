"""Gmail SMTP delivery with IMAP Sent-folder de-duplication. Fail closed if verification fails."""
import email.utils,imaplib,json,os,smtplib,ssl
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path


def _sent_folder(conn):
    status,folders=conn.list()
    if status!='OK':raise RuntimeError('IMAP_LIST_FAILED')
    for line in folders:
        if b'\\Sent' in line and b'"' in line:
            # IMAP folder label is the last quoted item.
            line=line.decode('utf-8','replace')
            import re
            q=re.findall(r'"([^"]+)"',line)
            if q:return q[-1]
    # An account may use a localized Gmail folder name, but do NOT search Inbox.
    raise RuntimeError('IMAP_SENT_FOLDER_UNAVAILABLE')


def already_sent(user,password,report_key):
    """Check actual Gmail Sent messages, not only a GitHub state file."""
    msgid=f'<pharma46-{report_key}@pharma-monitor.local>'
    with imaplib.IMAP4_SSL('imap.gmail.com',993,timeout=25) as imap:
        imap.login(user,password)
        folder=_sent_folder(imap)
        if imap.select('"'+folder.replace('"','')+'"',readonly=True)[0]!='OK':
            raise RuntimeError('IMAP_SENT_SELECT_FAILED')
        status,ids=imap.search(None,'HEADER','Message-ID','"'+msgid+'"')
        if status!='OK':raise RuntimeError('IMAP_SENT_SEARCH_FAILED')
        imap.logout()
        return bool(ids and ids[0])


def send_report(subject,body,day,ledger_path='data/pharma46_mail_ledger.json'):
    """No secrets => not sent. IMAP unavailable => do not risk duplicate."""
    user=os.getenv('MAIL_USER','').strip()
    password=os.getenv('MAIL_APP_PASSWORD','').strip()
    recipient=os.getenv('MAIL_TO','').strip()
    key=day.replace('-','')
    message_id=f'<pharma46-{key}@pharma-monitor.local>'
    ledgerfile=Path(ledger_path)
    try:ledger=json.loads(ledgerfile.read_text(encoding='utf-8'))
    except (FileNotFoundError,ValueError):ledger={}
    if key in ledger and ledger[key].get('status')=='sent':
        return {'status':'ALREADY_SENT_LEDGER','message_id':ledger[key].get('message_id')}
    if not (user and password and recipient):
        return {'status':'NOT_CONFIGURED','message_id':None,
                'reason':'MAIL_USER, MAIL_APP_PASSWORD, and MAIL_TO must be configured as GitHub secrets/vars'}
    try:
        found=already_sent(user,password,key)
    except Exception as e:
        return {'status':'NOT_SENT_IMAP_CHECK_FAILED','message_id':None,'error':str(e)[:220]}
    if found:
        ledger[key]={'status':'sent','message_id':message_id,'source':'imap_existing'}
        ledgerfile.parent.mkdir(parents=True,exist_ok=True)
        ledgerfile.write_text(json.dumps(ledger,indent=2),encoding='utf-8')
        return {'status':'ALREADY_SENT_IMAP','message_id':message_id}
    msg=EmailMessage()
    msg['From']=user;msg['To']=recipient;msg['Subject']=subject;msg['Date']=email.utils.formatdate(localtime=False)
    msg['Message-ID']=message_id
    msg['X-Pharma-Audit-ID']=key
    msg.set_content(body,subtype='plain',charset='utf-8')
    try:
        with smtplib.SMTP_SSL('smtp.gmail.com',465,timeout=40,context=ssl.create_default_context()) as smtp:
            smtp.login(user,password)
            smtp.send_message(msg)
    except Exception as e:
        return {'status':'NOT_SENT_SMTP_FAILED','message_id':None,'error':type(e).__name__+':'+str(e)[:180]}
    ledger[key]={'status':'sent','message_id':message_id,'source':'smtp'}
    ledgerfile.parent.mkdir(parents=True,exist_ok=True)
    ledgerfile.write_text(json.dumps(ledger,indent=2),encoding='utf-8')
    return {'status':'SENT','message_id':message_id}
