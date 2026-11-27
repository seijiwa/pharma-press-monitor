"""Cross-run and cross-platform delivery reservation (GitHub Contents API).
Only an atomic new file creation authorizes a send; never overwrite a reservation."""
import base64,json,os
from urllib.error import HTTPError
from urllib.request import Request,urlopen
BRANCH='pharma71-delivery-ledger'

def reserve(now):
    path='delivery/'+now.strftime('%Y-%m-%d')+'.json'
    payload={'date_jst':now.strftime('%Y-%m-%d'),'source':'github-smtp','state':'reserved','reserved_jst':now.isoformat(),'run_id':os.getenv('GITHUB_RUN_ID')}
    request=Request('https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']+'/contents/'+path,
        data=json.dumps({'message':'Reserve daily Pharma71 delivery','branch':BRANCH,
             'content':base64.b64encode(json.dumps(payload).encode()).decode()}).encode(),
        headers={'Authorization':'Bearer '+os.environ['GH_TOKEN'],'Accept':'application/vnd.github+json','Content-Type':'application/json'},
        method='PUT')
    try:
        with urlopen(request,timeout=20) as response:return response.status==201
    except HTTPError as exc:
        if exc.code in (409,422):
            print('Delivery reservation already exists or conflicted. No email sent.')
            return False
        raise
