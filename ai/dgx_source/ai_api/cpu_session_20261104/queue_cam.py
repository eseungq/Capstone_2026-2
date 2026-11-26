"""Queue the already-frozen CAM calculation in the authenticated CPU pane, without sudo."""
import json,os,shlex,subprocess
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path('/path/to/private/validated-project');SESSION='ai-cpu-codex'

def main():
 runtime=ROOT/'outputs/door_e02_live/cpu_session_20261104'
 request=json.loads((runtime/'request.json').read_text());ready=json.loads((runtime/'ready.json').read_text())
 assert ready['nonce']==request['nonce'] and ready['session']==SESSION and ready['uid']==os.getuid()!=0
 assert ready['CUDA_VISIBLE_DEVICES']==''
 subprocess.run(['tmux','has-session','-t',SESSION],check=True)
 panes=subprocess.check_output(['tmux','list-panes','-t',SESSION,'-F','#{pane_id} #{pane_dead}'],text=True).splitlines()
 assert len(panes)==1
 pane,dead=panes[0].split();assert dead=='0'
 out=Path(json.loads((ROOT/'ai_api/cam_methods_20261104/latest.json').read_text())['output'])
 assert out.is_relative_to(ROOT/'outputs/door_e02_live/cam_methods_20261104')
 if (out/'report.json').exists() or (out/'run.log').exists():
  print('EXISTING_JOB_PRESERVED',out);return
 dispatch=out/'dispatch.json'
 with dispatch.open('x') as stream:
  stream.write(json.dumps(dict(status='queued',session=SESSION,pane=pane,nonce=ready['nonce'],queuedUTC=datetime.now(timezone.utc).isoformat(),sudoUsed=False),indent=2)+'\n')
 python=shlex.join(['/usr/bin/python','-u',str(ROOT/'ai_api/cam_methods_20261104/run.py'),'--manifest',str(out/'manifest.json')])
 logfile=shlex.quote(str(out/'run.log'));exitfile=shlex.quote(str(out/'exit_code.txt'))
 command='( set -o noclobber; if exec 9>'+logfile+'; then '+python+' >&9 2>&1; task_cam_exit=$?; printf "%s\\n" "$task_cam_exit" >'+exitfile+'; fi )'
 subprocess.run(['tmux','send-keys','-t',pane,'-l',command],check=True)
 subprocess.run(['tmux','send-keys','-t',pane,'Enter'],check=True)
 subprocess.run(['tmux','detach-client','-s',SESSION],capture_output=True)
 print('CAM_JOB_QUEUED_WITHOUT_SUDO',out)

if __name__=='__main__':main()
