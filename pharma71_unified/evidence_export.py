"""Private, content-verified evidence export; no inbound server or public bucket."""
import gzip,hashlib,json,os,re,tempfile,zipfile,shutil
from pathlib import Path
from .comparison_receipt import receipt

def sha_file(path):
    with open(path,'rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def references(obj):
    if isinstance(obj,dict):
        if obj.get('snapshot_path') and obj.get('sha256'):yield obj['snapshot_path'],obj['sha256']
        for v in obj.values():yield from references(v)
    elif isinstance(obj,list):
        for v in obj:yield from references(v)
def build_bundle(root,run_id,out):
    root=Path(root).resolve()
    if not re.fullmatch(r'external-[0-9a-f]{32}',run_id):raise ValueError('invalid run ID')
    r=receipt(root/'newsroom',run_id)
    audit=root/'newsroom'/'audit.json'
    data=json.loads(audit.read_text())
    records={};problems=[]
    for raw,expected in references(data):
        p=Path(raw).resolve()
        if not p.is_relative_to(root) or not p.is_file():
            problems.append({'path':str(raw),'reason':'MISSING_OR_OUTSIDE_ROOT'});continue
        rel=p.relative_to(root).as_posix()
        try:
            if p.suffix=='.gz':
                with gzip.open(p,'rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
            else:actual=sha_file(p)
            if actual!=expected:
                problems.append({'path':rel,'reason':'RECEIPT_HASH_MISMATCH'});continue
            records[rel]={'file_sha256':sha_file(p),'receipt_sha256':expected,'bytes':p.stat().st_size}
        except (OSError,ValueError) as exc:problems.append({'path':rel,'reason':type(exc).__name__})
    for name in ('audit.json','report.md','state.json'):
        p=root/'newsroom'/name
        if not p.is_file():raise ValueError('missing required current output')
        records['newsroom/'+name]={'file_sha256':sha_file(p),'bytes':p.stat().st_size}
    m={'version':1,'run_id':run_id,'audit_sha256':r['audit_sha256'],'files':records,'problems':problems,
       'evidence_complete':not problems}
    with zipfile.ZipFile(out,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=5) as z:
        for rel in sorted(records):z.write(root/rel,rel)
        z.writestr('manifest.json',json.dumps(m,ensure_ascii=False,sort_keys=True))
    return m

def verify_bundle(path,expected_run_id,expected_sha=None):
    if expected_sha and sha_file(path)!=expected_sha:raise ValueError('bundle digest mismatch')
    with zipfile.ZipFile(path) as z:
        m=json.loads(z.read('manifest.json'))
        if m['run_id']!=expected_run_id:raise ValueError('bundle run mismatch')
        if set(z.namelist())!=set(m['files'])|{'manifest.json'} or len(z.namelist())!=len(set(z.namelist())):raise ValueError('unexpected bundle members')
        for rel,v in m['files'].items():
            if Path(rel).is_absolute() or '..' in Path(rel).parts:raise ValueError('unsafe archive name')
            with z.open(rel) as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
            if actual!=v['file_sha256']:raise ValueError('bundle member hash mismatch')
        audit=z.read('newsroom/audit.json')
        if hashlib.sha256(audit).hexdigest()!=m['audit_sha256'] or json.loads(audit)['run_id']!=expected_run_id:raise ValueError('audit identity mismatch')
        return m

def publish(root,run_id):
    keys=('EVIDENCE_ENDPOINT','EVIDENCE_BUCKET','EVIDENCE_REGION','EVIDENCE_ACCESS_KEY','EVIDENCE_SECRET_KEY')
    if not all(os.getenv(k) for k in keys):return {'status':'NOT_CONFIGURED','run_id':run_id}
    import boto3
    from botocore.config import Config
    with tempfile.TemporaryDirectory(prefix='pharma71-evidence-') as tmp:
        path=Path(tmp)/'bundle.zip'
        m=build_bundle(root,run_id,path)
        digest=sha_file(path)
        verify_bundle(path,run_id,digest)
        if path.stat().st_size>100*1024*1024:raise ValueError('evidence bundle exceeds 100 MB')
        s3=boto3.client('s3',endpoint_url=os.environ['EVIDENCE_ENDPOINT'],region_name=os.environ['EVIDENCE_REGION'],
            aws_access_key_id=os.environ['EVIDENCE_ACCESS_KEY'],aws_secret_access_key=os.environ['EVIDENCE_SECRET_KEY'],
            config=Config(signature_version='s3v4',s3={'addressing_style':'virtual'},connect_timeout=15,read_timeout=60,retries={'max_attempts':2}))
        bucket=os.environ['EVIDENCE_BUCKET'];key='runs/'+run_id+'.zip'
        s3.upload_file(str(path),bucket,key,ExtraArgs={'Metadata':{'sha256':digest,'run-id':run_id},'ContentType':'application/zip'})
        response=s3.get_object(Bucket=bucket,Key=key)
        try:remote=hashlib.file_digest(response['Body'],'sha256').hexdigest()
        finally:response['Body'].close()
        if remote!=digest:raise ValueError('stored bundle hash mismatch')
        result={'status':'VERIFIED_PRIVATE_UPLOAD' if m['evidence_complete'] else 'UPLOADED_WITH_EVIDENCE_GAPS',
            'run_id':run_id,'object_key':key,'sha256':digest,'bytes':path.stat().st_size,'files':len(m['files']),'problems':len(m['problems'])}
        # This short-lived read-only link is emitted only in the private
        # Railway service log, never into GitHub or the user report.
        if os.getenv('PHARMA71_SIGNED_EXPORT')=='1':
            result['read_url']=s3.generate_presigned_url('get_object',Params={'Bucket':bucket,'Key':key},ExpiresIn=7200)
        return result

def storage_guard(root,minimum=100*1024*1024):
    free=shutil.disk_usage(root).free
    if free<minimum:raise OSError('persistent storage below reserved capacity')
    return free
