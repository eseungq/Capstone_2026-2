"""Open one authenticated, unprivileged container shell in an owned tmux session."""
import json,os,shlex,subprocess,sys,uuid
from pathlib import Path

ROOT=Path('/path/to/private/validated-project')
SESSION='ai-cpu-codex'

def main():
 if not sys.stdin.isatty():raise SystemExit('Use an interactive SSH terminal (ssh -t) for the initial authentication.')
 if os.environ.get('TERM') in (None,'','dumb'):os.environ['TERM']='xterm-256color'
 runtime=ROOT/'outputs/door_e02_live/cpu_session_20261104';runtime.mkdir(parents=True,exist_ok=True,mode=0o700)
 exists=subprocess.run(['tmux','has-session','-t',SESSION],capture_output=True).returncode==0
 if exists:
  os.execvp('tmux',['tmux','attach-session','-t',SESSION])
 nonce=uuid.uuid4().hex
 (runtime/'request.json').write_text(json.dumps(dict(session=SESSION,nonce=nonce,uid=os.getuid(),gid=os.getgid()),indent=2)+'\n')
 register=ROOT/'ai_api/cpu_session_20261104/register.py'
 inside=shlex.join(['/usr/bin/python',str(register),'--nonce',nonce])+' && exec bash --noprofile --norc -i'
 command=['sudo','docker','exec','-it','-u',f'{os.getuid()}:{os.getgid()}',
  '-e','CUDA_VISIBLE_DEVICES=','-e','OMP_NUM_THREADS=2','-e','MKL_NUM_THREADS=2',
  '-e','PYTHONDONTWRITEBYTECODE=1','-e',f'PYTHONPATH=/tmp/door-e02-team-packages:{ROOT}',
  '-w',str(ROOT),'door-e02-team-api','bash','--noprofile','--norc','-c',inside]
 print('One-time Docker authentication. Keep this CPU container shell for subsequent jobs.',flush=True)
 os.execvp('tmux',['tmux','new-session','-s',SESSION,'-c',str(ROOT),shlex.join(command)])

if __name__=='__main__':main()
