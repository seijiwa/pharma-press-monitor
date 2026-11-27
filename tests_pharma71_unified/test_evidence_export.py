import json,hashlib,gzip,zipfile
import pytest
from pharma71_unified.evidence_export import references,verify_bundle
def test_reference_walk():
    assert list(references({'a':[{'snapshot_path':'x','sha256':'abc'}]}))==[('x','abc')]
def test_verify_bundle_detects_tamper(tmp_path):
    p=tmp_path/'test.zip';run='external-'+'a'*32
    raw=json.dumps({'run_id':run}).encode();d=hashlib.sha256(raw).hexdigest()
    m={'run_id':run,'audit_sha256':d,'files':{'newsroom/audit.json':{'file_sha256':d}},'evidence_complete':True}
    with zipfile.ZipFile(p,'w') as z:
        z.writestr('newsroom/audit.json',raw);z.writestr('manifest.json',json.dumps(m))
    assert verify_bundle(p,run)['evidence_complete']
    with pytest.raises(ValueError):verify_bundle(p,'external-'+'b'*32)
    with pytest.raises(ValueError):verify_bundle(p,run,'wrong')
    with zipfile.ZipFile(p,'w') as z:
        z.writestr('newsroom/audit.json',b'wrong');z.writestr('manifest.json',json.dumps(m))
    with pytest.raises(ValueError):verify_bundle(p,run)
