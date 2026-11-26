"""Audit current DOOR train/model-selection boundaries; never open test/reserved images."""
import csv,hashlib,json
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from door_experiment.preflight import audit_manifests

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
 return h.hexdigest()
def dump(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def main():
 root=Path(__file__).resolve().parents[1];tables,audit=audit_manifests(root)
 out=root/'outputs/door_independence'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 print('[INDEPENDENCE OUTPUT]',out,flush=True)
 fp_path=root/'ai_api/verification/audit_followup_20261016T182934_010033Z/fingerprints.json'
 fingerprints={r['image_path']:r for r in json.loads(fp_path.read_text())}
 source_summary=json.loads((fp_path.parent/'summary.json').read_text())
 if source_summary['status']!='complete' or source_summary['finalTestUsed']:raise ValueError('Unexpected fingerprint scope')
 allrows=[r for rows in tables.values() for r in rows]
 if any(r['image_path'] not in fingerprints or 'dhash' not in fingerprints[r['image_path']] for r in allrows):raise ValueError('Missing fingerprint')
 report=dict(status='running',scope='current train vs model_selection; full-image 64-bit dHash<=8; candidate discovery only',counts={k:len(v) for k,v in tables.items()},known_group_boundary_check='passed',known_suspected_relation_check='passed',final_test_read=False,reserved_images_read=False,originals_modified=False,model_changed=False,training_performed=False,source_hashes={str(fp_path.relative_to(root)):sha(fp_path)},limitations=['Full-image dHash may miss crops, angles, illumination and the same physical part.','A candidate is not a confirmed duplicate or leakage.','Previous human decisions must be reconciled before requesting any repeat review.'])
 dump(out/'summary.json',report)
 try:
  checked=[];changes=[]
  with ThreadPoolExecutor(max_workers=4) as pool:
   for i,(row,digest) in enumerate(zip(allrows,pool.map(lambda r:sha(r['image_path']),allrows)),1):
    expected=fingerprints[row['image_path']]['sha256'];checked.append(dict(image_path=row['image_path'],sha256=digest))
    if digest!=expected:changes.append(row['image_path'])
    if i%1000==0 or i==len(allrows):print('[CURRENT FILE HASH]',i,'/',len(allrows),flush=True)
  dump(out/'current_file_hashes.json',checked);report['current_files_checked']=len(checked);report['files_changed_since_fingerprint']=changes
  if changes:raise ValueError('Changed images: cached visual fingerprints invalid')
  digest_groups=defaultdict(list)
  for role,rows in tables.items():
   for row in rows:digest_groups[fingerprints[row['image_path']]['sha256']].append(dict(role=role,image_path=row['image_path'],group_id=row['group_id']))
  exact=[v for v in digest_groups.values() if len({r['role'] for r in v})>1];dump(out/'exact_cross_role_duplicates.json',exact)
  pairs=[];origin_counts=Counter();previously_unsearched=0
  train=[(r,fingerprints[r['image_path']]) for r in tables['train']]
  for i,row in enumerate(tables['model_selection'],1):
   a=fingerprints[row['image_path']]
   for other,b in train:
    distance=(a['dhash']^b['dhash']).bit_count()
    if distance<=8:
     old_same=a['split']==b['split'];previously_unsearched+=int(old_same);origin_counts[(a['split'],b['split'])]+=1
     pairs.append(dict(distance=distance,exact_bytes=a['sha256']==b['sha256'],model_selection_image=row['image_path'],train_image=other['image_path'],model_selection_group=row['group_id'],train_group=other['group_id'],original_roles=[a['split'],b['split']],outside_previous_search=old_same,model_selection_class=row['class_id'],train_class=other['class_id'],status='heuristic_candidate_human_history_not_reconciled'))
   if i%500==0 or i==len(tables['model_selection']):print('[CROSS-ROLE SEARCH]',i,'/',len(tables['model_selection']),flush=True)
  pairs.sort(key=lambda p:(not p['exact_bytes'],p['distance'],p['model_selection_image'],p['train_image']))
  dump(out/'visual_candidates.json',pairs)
  affected={p['model_selection_image'] for p in pairs}
  run=root/'outputs/door_next_training/door_visible_20261028_065548_667023'
  with (run/'best_model_selection_predictions.csv').open(encoding='utf-8-sig') as f:pred=list(csv.DictReader(f))
  if {r['image_path'] for r in pred}!={r['image_path'] for r in tables['model_selection']}:raise ValueError('Prediction scope differs')
  affected_confusion=Counter(('TP' if r['class_id']=='1' else 'FP') if r['predicted_class']=='1' else ('FN' if r['class_id']=='1' else 'TN') for r in pred if r['image_path'] in affected)
  report.update(status='automated_audit_complete_independence_not_established',exact_cross_role_groups=len(exact),compared_pairs=len(tables['train'])*len(tables['model_selection']),visual_candidate_pairs=len(pairs),candidate_model_selection_images=len(affected),candidate_pairs_outside_previous_search=previously_unsearched,candidate_original_role_counts={f'{a}/{b}':n for (a,b),n in origin_counts.items()},candidate_affected_saved_confusion=dict(affected_confusion),independence_established=False,retraining_required='not_decided_pending_identity_evidence',existing_score_invalidated=False)
  print('[INDEPENDENCE RESULT]',json.dumps(report,ensure_ascii=False),flush=True)
 except BaseException as exc:
  report.update(status='failed_or_interrupted',error_type=type(exc).__name__);raise
 finally:
  dump(out/'summary.json',report);print('[INDEPENDENCE REPORT]',out/'summary.json',flush=True)
if __name__=='__main__':main()
