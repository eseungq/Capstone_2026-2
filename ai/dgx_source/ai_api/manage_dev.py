"""Optional local development convenience; not a prerequisite or deployment platform.

Uses the existing foreground launcher. Stops only the CID recorded by this launch,
never an arbitrary container name or another prototype service.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.request import build_opener,ProxyHandler
from ai_api.server import Downloader
from ai_api.verify_gpu import ROOT

SESSION=ROOT/'ai_api/runtime/managed_door_session.json'
EXPECTED_SHA='8d042c7bfab20ba2527ef3693aed08e0df7e1b1ce58acc45b44de7ae5d0d6ab7'


def docker_command():
    return ['sudo','docker'] if os.environ.get('DOOR_DOCKER_SUDO')=='1' else ['docker']


def read_session(path=SESSION,runtime=ROOT/'ai_api/runtime'):
    record=json.loads(path.read_text())
    if record.get('scope')!='owned-development-serve-launch':raise ValueError('Unknown session record')
    cidfile=Path(record['cidfile']).resolve()
    if cidfile.parent!=runtime.resolve() or not cidfile.name.startswith('serve_') or cidfile.suffix!='.cid':raise ValueError('CID file is not a managed serve launch')
    if not cidfile.exists():return record,None
    cid=cidfile.read_text().strip()
    if not re.fullmatch('[0-9a-f]{64}',cid):raise ValueError('Invalid container ID; no container will be stopped')
    return record,cid


def inspect(cid):
    result=subprocess.run(docker_command()+['inspect','--type','container',cid],capture_output=True,text=True,timeout=30)
    if result.returncode:
        if 'no such object' in result.stderr.lower() or 'no such container' in result.stderr.lower():return None
        raise RuntimeError('Docker inspection failed; check existing permissions/sudo cache. No process stopped.')
    values=json.loads(result.stdout)
    if len(values)!=1:raise ValueError('Ambiguous container result')
    return values[0]


def require_owned(info,cid,project=ROOT):
    if info.get('Id')!=cid or info.get('Name')!='/door-ai-api-serve' or info.get('Config',{}).get('Image')!='nvcr.io/nvidia/pytorch:25.11-py3':raise ValueError('Container identity differs; refusing action')
    if not any(m.get('Source')==str(project) and m.get('Destination')==str(project) for m in info.get('Mounts',[])):raise ValueError('Project mount differs; refusing action')


def preflight():
    version=os.environ.get('DOOR_API_MODEL_VERSION','');origin=os.environ.get('DOOR_API_IMAGE_ORIGIN','')
    if not version or version.startswith('mock-'):raise ValueError('Set an explicit real-model development identifier; not mock-')
    if os.environ.get('DOOR_API_DEVELOPMENT_CONTRACT')!='1':raise ValueError('Set DOOR_API_DEVELOPMENT_CONTRACT=1; final contract is still pending')
    if not origin:raise ValueError('DOOR_API_IMAGE_ORIGIN is missing. Obtain the origin reachable FROM DGX/container; do not invent localhost.')
    Downloader([origin])  # syntax/origin validation only; no download


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('action',choices=['start','status','stop']);args=parser.parse_args()
    if args.action=='start':
        preflight()
        if SESSION.exists():
            _,cid=read_session()
            if cid:
                info=inspect(cid)
                if info:
                    require_owned(info,cid)
                    if info.get('State',{}).get('Running'):raise RuntimeError('Managed server already running; use status/stop first')
        env=os.environ.copy();env['DOOR_API_SESSION_RECORD']=str(SESSION)
        print('[DEVELOPMENT ONLY] Existing foreground launcher; Ctrl+C stops this run. No production registration.',flush=True)
        raise SystemExit(subprocess.call(['bash',str(ROOT/'ai_api/run_gpu.sh'),'serve'],cwd=ROOT,env=env))
    if not SESSION.exists():print('[NOT STARTED] No server recorded by this tool; no action taken.');return
    record,cid=read_session()
    if cid is None:print('[NOT READY] Recorded launcher has not created its container. Inspect its log; no other service touched.');return
    info=inspect(cid)
    if info is None:print('[STOPPED] Recorded container no longer exists.');return
    require_owned(info,cid)
    if not info.get('State',{}).get('Running'):print('[STOPPED] Recorded container is not running.');return
    if args.action=='stop':
        subprocess.run(docker_command()+['stop',cid],check=True,timeout=60);print('[STOPPED] Only the recorded container was targeted.');return
    bindings=info.get('HostConfig',{}).get('PortBindings',{}).get('8770/tcp')
    if bindings!=[{'HostIp':'127.0.0.1','HostPort':'8770'}]:raise ValueError('Expected loopback binding differs; no remote check performed')
    opener=build_opener(ProxyHandler({}))
    try:
        with opener.open('http://127.0.0.1:8770/internal/v1/models',timeout=30) as response:
            inventory=json.load(response);inventory_sha=response.headers.get('X-AI-Model-SHA256')
    except Exception as exc:raise RuntimeError('Container is running but AI readiness not confirmed; inspect startup log.') from exc
    backend='data' in inventory
    rows=inventory.get('data' if backend else 'models',[])
    if len(rows)!=1 or rows[0].get('partCode')!='DOOR' or rows[0].get('modelVersion')!=record['modelVersion'] or (inventory_sha if backend else rows[0].get('modelSha256'))!=EXPECTED_SHA or rows[0].get('loadable' if backend else 'available') is not True:raise RuntimeError('AI model/version/readiness mismatch')
    print(json.dumps({'state':'ready','model':rows[0],'developmentOnly':True,'backendConnectivity':'not_verified'},ensure_ascii=False,indent=2))

if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,subprocess.SubprocessError,OSError) as exc:raise SystemExit(str(exc))
