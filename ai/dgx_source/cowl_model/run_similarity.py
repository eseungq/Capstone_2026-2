"""Prepare/resume the complete cowl audit with an exclusive lock and preserved pilot."""
import argparse,fcntl,hashlib,json,shutil,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--prepare-only',action='store_true');args=ap.parse_args()
 runtime=ROOT/'outputs/cowl_similarity_runtime';runtime.mkdir(parents=True,exist_ok=True)
 with (runtime/'audit.lock').open('a') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:raise SystemExit('카울커버 점검이 이미 실행 중입니다. 중복 실행하지 않습니다.')
  pointer=ROOT/'cowl_model/latest_full_similarity.json'
  if pointer.exists():out=Path(json.loads(pointer.read_text())['directory'])
  else:
   pilot=Path(json.loads((ROOT/'cowl_model/latest_similarity.json').read_text())['directory']);old=json.loads((pilot/'summary.json').read_text())
   if old['status']!='pilot_complete_not_full_audit':raise ValueError('Expected completed pilot to preserve')
   out=ROOT/'outputs/cowl_similarity'/('full_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));shutil.copytree(pilot,out)
   (out/'pilot_summary_preserved.json').write_bytes((pilot/'summary.json').read_bytes());(out/'origin.json').write_text(json.dumps(dict(pilot=str(pilot),pilotPreserved=True),indent=2));pointer.write_text(json.dumps(dict(directory=str(out)),indent=2))
  summary=json.loads((out/'summary.json').read_text());script=ROOT/'cowl_model/audit_similarity.py';inventory=Path(summary['inventory'])
  if summary['script_sha256']!=hashlib.sha256(script.read_bytes()).hexdigest() or summary['inventory_sha256']!=hashlib.sha256(inventory.read_bytes()).hexdigest():raise ValueError('Code/inventory differs from cache')
  records=[json.loads(l) for l in (out/'fingerprints.jsonl').read_text().splitlines()]
  if len({r['image_id'] for r in records})!=len(records):raise ValueError('Duplicate cached IDs')
  with inventory.open(encoding='utf-8-sig') as f:
   import csv
   source={r['image_id']:r for r in csv.DictReader(f) if r['status']=='ok'}
  if not all(r['image_id'] in source for r in records):raise ValueError('Unknown cached IDs')
  archives={Path(r['image_archive']) for r in source.values()}
  for archive in archives:
   if '/1.Training/원천데이터/' not in str(archive) or not archive.is_file():raise ValueError('Unexpected or missing Training archive')
  # Verify original source stat matches the metadata inventory before using offsets.
  inv_summary=json.loads((inventory.parent/'summary.json').read_text())
  for name,expected in inv_summary['archiveStats'].items():
   p=Path(name);stat=p.stat()
   if dict(bytes=stat.st_size,mtime_ns=stat.st_mtime_ns)!=expected:raise ValueError('Source archive changed since inventory')
  check=dict(status='prepared_not_executed' if args.prepare_only else 'launching',directory=str(out),cached=len(records),total=len(source),remaining=len(source)-len(records),pilotPreserved=True,trainingStarted=False,script_sha256=summary['script_sha256'],inventory_sha256=summary['inventory_sha256'])
  (out/'launch_preflight.json').write_text(json.dumps(check,ensure_ascii=False,indent=2));print(json.dumps(check,ensure_ascii=False,indent=2),flush=True)
  if args.prepare_only:return
  if summary['status']=='complete_candidates_unreviewed':print('전체 계산은 이미 완료됐습니다. 후보 검토가 다음 단계입니다.');return
  stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');log=runtime/f'full_{stamp}.log';print('[LOG]',log,flush=True)
  command=[sys.executable,'-u','-m','cowl_model.audit_similarity','--all','--resume',str(out)]
  # Foreground execution: Ctrl+C stops only this invocation, cache is retained.
  with log.open('w') as stream:
   process=subprocess.Popen(command,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
   try:
    for line in process.stdout:print(line,end='',flush=True);stream.write(line);stream.flush()
    code=process.wait()
   except BaseException:
    if process.poll() is None:process.terminate();process.wait()
    raise
  print('[COWL FULL EXIT]',code,flush=True);raise SystemExit(code)
if __name__=='__main__':main()
