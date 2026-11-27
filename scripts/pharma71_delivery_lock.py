"""Cross-run and cross-platform delivery reservation (GitHub Contents API).
Only an atomic new file creation authorizes a send; never overwrite a reservation."""
import base64,json,os,time
from urllib.error import HTTPError
from urllib.request import Request,urlopen
BRANCH='pharma71-delivery-ledger'

def delivery_window(now):
    from datetime import time
    from zoneinfo import ZoneInfo
    if now.tzinfo is None or now.utcoffset() is None:return False
    local=now.astimezone(ZoneInfo('Asia/Tokyo'))
    return time(5,10)<=local.time()<time(6,31)

def ledger_exists(path):
    url='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/contents/'+path+'?ref='+BRANCH
    req=Request(url,headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json'})
    for attempt in range(3):
        try:
            with urlopen(req,timeout=8) as response:
                if response.status!=200:raise RuntimeError('Unexpected ledger read response')
                item=json.loads(response.read())
                if item.get('type')!='file' or item.get('path')!=path or not item.get('sha'):
                    raise RuntimeError('Ledger path is not a confirmed file')
                return True
        except HTTPError as exc:
            if exc.code!=404:raise
            if attempt<2:time.sleep(.25)
    return False

def create_once(path,payload):
    request=Request('https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/contents/'+path,
        data=json.dumps({'message':'Reserve daily Pharma71 delivery','branch':BRANCH,
             'content':base64.b64encode(json.dumps(payload).encode()).decode()}).encode(),
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','Content-Type':'application/json'},
        method='PUT')
    try:
        with urlopen(request,timeout=20) as response:
            if response.status!=201:raise RuntimeError('Unexpected ledger create response')
            return True
    except HTTPError as exc:
        if exc.code in (409,422):
            if ledger_exists(path):
                print('Ledger file already exists; no overwrite.')
                return False
            raise RuntimeError('Ledger conflict without confirmed reservation; delivery stopped') from exc
        raise

def reserve(now):
    day=now.strftime('%Y-%m-%d')
    return create_once('delivery/'+day+'.json',{'date_jst':day,'source':'github-smtp','state':'reserved','reserved_jst':now.isoformat(),'run_id':os.getenv('GITHUB_RUN_ID')})

def mark_accepted(now,day):
    day=day.isoformat()
    return create_once('delivery/'+day+'-accepted.json',{'date_jst':day,'source':'github-smtp','state':'accepted','accepted_jst':now.isoformat(),'run_id':os.getenv('GITHUB_RUN_ID')})

def live_probe():
    """Real API collision probe on a test-only path. No SMTP or production reservation."""
    import re
    run=os.environ['GITHUB_RUN_ID'];attempt=os.environ.get('GITHUB_RUN_ATTEMPT','1')
    if not re.fullmatch(r'\d+',run) or not re.fullmatch(r'\d+',attempt):raise ValueError('invalid test ID')
    p='tests/lock-'+run+'-'+attempt+'.json'
    if not create_once(p,{'state':'test-only','run_id':run}):raise RuntimeError('first reservation probe failed')
    if create_once(p,{'state':'test-only-duplicate','run_id':run}):raise RuntimeError('duplicate unexpectedly accepted')
    print('LIVE_LEDGER_PROBE_PASS: first creation accepted, second rejected; no email')
    from concurrent.futures import ThreadPoolExecutor
    race='tests/race-'+run+'-'+attempt+'.json'
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims=list(pool.map(lambda i:create_once(race,{'state':'test-only','claim':i}),[1,2]))
    if sum(claims)!=1:raise RuntimeError('concurrent reservation failed safety gate')
    print('LIVE_CONCURRENT_RESERVATION_PASS: exactly one winner; no email')
