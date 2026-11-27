"""Portable external collector. No inbound listener or GitHub write credentials."""
import os,sys,time,subprocess,uuid,fcntl
from pathlib import Path
from .comparison_receipt import emit
def main():
    root=Path(os.getenv('PHARMA71_DATA_DIR','/data/pharma71'));root.mkdir(parents=True,exist_ok=True)
    interval=max(1200,int(os.getenv('PHARMA71_INTERVAL_SECONDS','1200')))
    with (root/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            started=time.monotonic()
            env=dict(os.environ,PHARMA71_ENVIRONMENT=os.getenv('PHARMA71_ENVIRONMENT','external-worker'))
            env['GITHUB_RUN_ID']='external-'+uuid.uuid4().hex
            reg=root/'regulatory'
            rc=subprocess.run([sys.executable,'-m','pharma71_unified.regulatory','--root',str(reg)],env=env).returncode
            cmd=[sys.executable,'-m','pharma71_unified.cli','--root',str(root/'newsroom'),'--workers','3']
            if rc==0 and (reg/'regulatory.json').exists():cmd+=['--regulatory-file',str(reg/'regulatory.json')]
            rc=subprocess.run(cmd,env=env).returncode
            if rc==0:emit(root/'newsroom',env['GITHUB_RUN_ID'])
            print('external worker completed:',rc,flush=True)
            if os.getenv('PHARMA71_RUN_ONCE')=='1':return rc
            time.sleep(max(10,interval-(time.monotonic()-started)))
if __name__=='__main__':sys.exit(main())
