"""Initialize only the configured volume, then drop privileges before networking."""
import os,pwd,stat,sys
from pathlib import Path

def main():
    root=Path(os.environ.get('PHARMA71_DATA_DIR','/data/pharma71'))
    if root!=Path('/data/pharma71') or root.resolve()!=root:
        raise ValueError('Unexpected collector volume path')
    user=pwd.getpwnam('collector')
    if os.geteuid()==0:
        root.mkdir(parents=True,exist_ok=True)
        if not stat.S_ISDIR(root.lstat().st_mode):raise ValueError('Not a directory')
        os.chown(root,user.pw_uid,user.pw_gid)
        os.chmod(root,0o750)
        os.setgroups([])
        os.setgid(user.pw_gid)
        os.setuid(user.pw_uid)
    if os.geteuid()!=user.pw_uid or os.getegid()!=user.pw_gid:
        raise RuntimeError('Worker privilege drop failed')
    os.environ['HOME']=user.pw_dir
    os.environ['USER']=user.pw_name
    if not os.access(root,os.W_OK|os.X_OK):raise PermissionError('Persistent volume not writable')
    print('collector volume writable; uid='+str(os.geteuid()),flush=True)
    os.execv(sys.executable,[sys.executable,'-m','pharma71_unified.worker'])

if __name__=='__main__':main()
