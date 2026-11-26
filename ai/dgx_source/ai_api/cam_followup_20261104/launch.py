"""Confirm writable output and save the child PID before returning from docker exec."""
import argparse, json, os, subprocess, sys, time
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--selection',type=Path,required=True);a=p.parse_args()
assert os.environ.get('CUDA_VISIBLE_DEVICES') == ''
out=a.selection.parent
assert '/outputs/door_e02_live/cam_followup_20261104/' in str(out)
with (out/'run.log').open('x') as stream:
    child=subprocess.Popen([sys.executable,'-u','ai_api/cam_followup_20261104/run.py','--selection',str(a.selection)],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
    time.sleep(1)
    receipt=dict(pid=child.pid,python=sys.executable,device='cpu',selection=str(a.selection),initialExitCode=child.poll())
    (out/'launch.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt),flush=True)
    if child.poll() is not None:
        print((out/'run.log').read_text()[-3000:],flush=True)
        raise SystemExit(child.returncode or 1)
