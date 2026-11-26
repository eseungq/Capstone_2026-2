"""Start one fixed CPU CAM comparison, preserving launch and error receipts."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();out=a.manifest.parent
assert os.environ.get('CUDA_VISIBLE_DEVICES')=='' and '/outputs/door_e02_live/cam_methods_20261104/' in str(out)
with (out/'run.log').open('x') as stream:
 child=subprocess.Popen([sys.executable,'-u','ai_api/cam_methods_20261104/run.py','--manifest',str(a.manifest)],stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True)
 for i in range(30):
  if (out/'report.json').exists() or child.poll() is not None:break
  time.sleep(.5)
 receipt=dict(pid=child.pid,device='cpu',manifest=str(a.manifest),initialExitCode=child.poll());(out/'launch.json').write_text(json.dumps(receipt,indent=2)+'\n');print(json.dumps(receipt),flush=True)
 if child.poll() is not None and child.returncode!=0:print((out/'run.log').read_text()[-4000:],flush=True);raise SystemExit(child.returncode)
