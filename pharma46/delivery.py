"""Gmail SMTP delivery with IMAP Sent-folder de-duplication. Fail closed if verification fails."""
import email.utils,imaplib,json,os,smtplib,ssl
from email import policy
from email.parser import BytesParser
from datetime import datetime,timedelta,timezone
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


JST=timezone(timedelta(hours=9))

def scheduled_window(day,now=None):
    now=now or datetime.now(JST)
    now=now.astimezone(JST)
    return now.date().isoformat()==day and 240 <= now.hour*60+now.minute < 320

def same_report_subject(subject,day):
    # Exclude the separate 71-name digest and explicitly labeled tests.
    date_tokens=(day,day.replace('-','/'),day.replace('-','/').replace('/0','/'))
    return (any(token in subject for token in date_tokens) and
            ('製薬公式監視' in subject or '46社' in subject) and
            '71社' not in subject and 'テスト' not in subject and 'TEST' not in subject.upper())

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
        if ids and ids[0]:return True
        day=datetime.strptime(report_key,'%Y%m%d').date()
        status,ids=imap.search(None,'SINCE',(day-timedelta(days=1)).strftime('%d-%b-%Y'))
        if status!='OK':raise RuntimeError('IMAP_SENT_DATE_SEARCH_FAILED')
        candidates=(ids[0] or b'').split() if ids else []
        for offset in range(0,len(candidates),50):
            sequence=b','.join(candidates[offset:offset+50]).decode('ascii')
            status,headers=imap.fetch(sequence,'(BODY.PEEK[HEADER.FIELDS (SUBJECT)])')
            if status!='OK':raise RuntimeError('IMAP_SENT_HEADER_FETCH_FAILED')
            subjects=[BytesParser(policy=policy.default).parsebytes(x[1]) for x in headers if isinstance(x,tuple) and isinstance(x[1],bytes)]
            if len(subjects)!=len(candidates[offset:offset+50]):raise RuntimeError('IMAP_SENT_HEADER_COUNT_MISMATCH')
            if any(same_report_subject(str(m.get('Subject','')),day.isoformat()) for m in subjects):return True
        return False


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
    if os.getenv('DELIVERY_MODE')=='scheduled' and not scheduled_window(day):
        return {'status':'NOT_SENT_OUTSIDE_WINDOW','message_id':None}
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
    if key in ledger and ledger[key].get('status')=='sent':
        return {'status':'NOT_SENT_LEDGER_UNCONFIRMED','message_id':ledger[key].get('message_id')}
    msg=EmailMessage()
    msg['From']=user;msg['To']=recipient;msg['Subject']=subject;msg['Date']=email.utils.formatdate(localtime=False)
    msg['Message-ID']=message_id
    msg['X-Pharma-Audit-ID']=key
    msg.set_content(body,subtype='plain',charset='utf-8')
    try:
        with smtplib.SMTP('smtp.gmail.com',587,timeout=25) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.user,smtp.password=user,''.join(password.split())
            smtp.auth('LOGIN',smtp.auth_login,initial_response_ok=False)
            if os.getenv('DELIVERY_MODE')=='scheduled' and not scheduled_window(day):
                return {'status':'NOT_SENT_OUTSIDE_WINDOW','message_id':None}
            refused=smtp.send_message(msg)
            if refused:raise RuntimeError('SMTP_RECIPIENT_REFUSED')
    except Exception as e:
        return {'status':'NOT_SENT_SMTP_FAILED','message_id':None,'error':type(e).__name__+':'+str(e)[:180]}
    ledger[key]={'status':'sent','message_id':message_id,'source':'smtp'}
    ledgerfile.parent.mkdir(parents=True,exist_ok=True)
    ledgerfile.write_text(json.dumps(ledger,indent=2),encoding='utf-8')
    return {'status':'SENT','message_id':message_id,'smtp_accepted':True,'recipient_inbox_verified':False}
