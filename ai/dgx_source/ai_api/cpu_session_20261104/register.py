"""Verify the established CPU shell; no model load and no permission changes."""
import argparse,importlib.metadata,json,os,socket
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path('/path/to/private/validated-project')
p=argparse.ArgumentParser();p.add_argument('--nonce',required=True);a=p.parse_args()
runtime=ROOT/'outputs/door_e02_live/cpu_session_20261104'
request=json.loads((runtime/'request.json').read_text())
assert a.nonce==request['nonce'] and os.getuid()==request['uid']!=0
assert os.environ.get('CUDA_VISIBLE_DEVICES')==''
manifest=ROOT/'outputs/door_next_training/door_visible_20261029_162657_477520/run_config.json'
expected=json.loads(manifest.read_text())['versions']
versions={name:importlib.metadata.version(name) for name in expected};assert versions==expected
container_id=(ROOT/'outputs/door_e02_live/container_id.txt').read_text().strip()
assert socket.gethostname()==container_id[:12]
ready=dict(session=request['session'],nonce=a.nonce,uid=os.getuid(),containerHostname=socket.gethostname(),shellPID=os.getppid(),CUDA_VISIBLE_DEVICES=os.environ.get('CUDA_VISIBLE_DEVICES'),versions=versions,createdUTC=datetime.now(timezone.utc).isoformat(),permissionChanges=False)
tmp=runtime/'ready.json.tmp';tmp.write_text(json.dumps(ready,indent=2)+'\n');tmp.replace(runtime/'ready.json')
print('CPU_SESSION_READY: authenticated shell available for reuse; no model or policy changes.',flush=True)
