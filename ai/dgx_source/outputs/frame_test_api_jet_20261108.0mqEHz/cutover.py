from pathlib import Path
import json
import os
import signal
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

stage=Path(sys.argv[1])
root=Path('/path/to/private/validated-project')
prior=root/'outputs/frame_test_api_20261107.d37a92'
filename='frame_unified_test_api_20261107.py'
base='http://127.0.0.1:'
host='127.0.0.1'
frame='frame-swin-tiny-unified-e08-2425d7e46572-dev'

def listing(port):
    with urlopen(f'{base}{port}/internal/v1/models',timeout=2) as res:
        return json.load(res)['data']

def port_ready():
    with socket.socket() as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host,8773))==0

def matching_process():
    matches=[]
    for path in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            args=[os.fsdecode(x) for x in path.read_bytes().split(b'\0') if x]
            if args[:3]==[sys.executable,'-u',str(prior/filename)] and '--port' in args and args[args.index('--port')+1]=='8773':
                matches.append((int(path.parent.name),args))
        except (OSError,IndexError):
            continue
    if len(matches)!=1:
        raise RuntimeError(f'Expected one old FRAME process; got {len(matches)}')
    return matches[0]

def start(directory,log_name):
    args=[sys.executable,'-u',str(directory/filename),'--project',str(root),'--runtime',str(directory),
          '--host',host,'--port','8773','--image-origin','http://127.0.0.1:8080']
    with (directory/log_name).open('ab') as log:
        return subprocess.Popen(args,cwd=root,env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1'),
                                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)

def await_ready(proc):
    for _ in range(90):
        if proc.poll() is not None:
            break
        try:
            rows=listing(8773)
            if rows==[dict(modelVersion=frame,partCode='FRAME',calibratorVersion=None,loadable=True)]:
                return True
        except (OSError,ValueError):
            pass
        time.sleep(0.5)
    return False

report=json.loads((stage/'demo_jet/report.json').read_text())
if report['camPalette']!='JET' or report['camAlpha']!=0.5:
    raise ValueError('The JET 50 percent GPU fixture result is missing')
if not any(row['partCode']=='DOOR' and row['loadable'] for row in listing(8771)):
    raise RuntimeError('DOOR baseline not ready')
if listing(8773)[0]['modelVersion']!=frame:
    raise RuntimeError('Unexpected FRAME listener')
pid,_=matching_process()
os.kill(pid,signal.SIGTERM)
for _ in range(50):
    if not port_ready():
        break
    time.sleep(0.2)
else:
    raise RuntimeError('Old FRAME listener did not stop')

new=start(stage,'server.log')
if not await_ready(new):
    if new.poll() is None:
        new.terminate()
        new.wait(timeout=10)
    fallback=start(prior,'rollback.log')
    recovered=await_ready(fallback)
    raise RuntimeError(f'New FRAME process failed. Old process restored: {recovered}')
live=dict(framePid=new.pid,frameModels=listing(8773),doorModels=listing(8771),
          palette=report['camPalette'],alpha=report['camAlpha'])
(stage/'cutover.json').write_text(json.dumps(live,indent=2)+'\n')
print(json.dumps(live))
