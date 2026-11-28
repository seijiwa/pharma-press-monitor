"""Pharma46 SMTP delivery with a repository-wide, date-scoped reservation."""
import email.utils,imaplib,os,smtplib,ssl
from email import policy
from email.parser import BytesParser
from datetime import datetime,timedelta,timezone
from email.message import EmailMessage
from scripts.pharma71_delivery_lock import create_once


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
    if now.utcoffset() is None:
        return False
    now=now.astimezone(JST)
    return now.date().isoformat()==day and 330 <= now.hour*60+now.minute < 335

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


def send_report(subject,body,day):
    """Use the same reservation for every participating Pharma46 sender."""
    user=os.getenv('MAIL_USER','').strip()
    password=''.join(os.getenv('MAIL_APP_PASSWORD','').split())
    recipient=os.getenv('MAIL_TO','').strip()
    if not (user and password and recipient):
        return {'status':'NOT_CONFIGURED'}
    if not scheduled_window(day):
        return {'status':'NOT_SENT_OUTSIDE_WINDOW'}

    key=day.replace('-','')
    message_id=f'<pharma46-{key}@pharma-monitor.local>'
    try:
        if already_sent(user,password,key):
            return {'status':'ALREADY_SENT_IMAP','recipient_inbox_verified':False}
    except Exception as exc:
        return {'status':'NOT_SENT_IMAP_CHECK_FAILED','error_type':type(exc).__name__}

    msg=EmailMessage()
    msg['From']=user
    msg['To']=recipient
    msg['Subject']=subject
    msg['Date']=email.utils.formatdate(localtime=False)
    msg['Message-ID']=message_id
    msg['X-Pharma-Audit-ID']=key
    msg.set_content(body,subtype='plain',charset='utf-8')
    reserved=False
    accepted=False
    try:
        with smtplib.SMTP('smtp.gmail.com',587,timeout=25) as smtp:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()
            smtp.user,smtp.password=user,password
            smtp.auth('LOGIN',smtp.auth_login,initial_response_ok=False)
            if not scheduled_window(day):
                return {'status':'NOT_SENT_OUTSIDE_WINDOW'}
            reserved=create_once(f'delivery46/{day}.json',{
                'date_jst':day,'state':'reserved','message_id':message_id,
                'reserved_jst':datetime.now(JST).isoformat(),'run_id':os.getenv('GITHUB_RUN_ID'),
            },message='Reserve daily Pharma46 delivery')
            if not reserved:
                return {'status':'NOT_SENT_ALREADY_RESERVED'}
            if not scheduled_window(day):
                return {'status':'RESERVED_WINDOW_CLOSED','message_id':message_id}
            if smtp.send_message(msg):
                raise RuntimeError('SMTP_RECIPIENT_REFUSED')
            accepted=True
    except Exception as exc:
        if not accepted:
            return {'status':'RESERVED_SMTP_OUTCOME_UNKNOWN' if reserved else 'NOT_SENT_PREPARATION_FAILED',
                    'message_id':message_id,'error_type':type(exc).__name__}
    try:
        recorded=create_once(f'delivery46/{day}-accepted.json',{
            'date_jst':day,'state':'accepted','message_id':message_id,
            'accepted_jst':datetime.now(JST).isoformat(),'run_id':os.getenv('GITHUB_RUN_ID'),
        },message='Record Pharma46 SMTP acceptance')
    except Exception:
        recorded=False
    return {'status':'SMTP_ACCEPTED','message_id':message_id,'acceptance_recorded':recorded,
            'smtp_accepted':True,'recipient_inbox_verified':False}
