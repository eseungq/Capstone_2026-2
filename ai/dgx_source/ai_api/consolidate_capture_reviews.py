"""Consolidate human capture decisions with immutable history and provisional scene links."""
import csv,hashlib,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageOps,ImageChops,ImageStat
from ai_api.duplicate_groups import read_csv,dump
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 latest=json.loads((ROOT/'ai_api/verification/latest_data_proposal.json').read_text());groups=json.loads((ROOT/latest['groupDirectory']/'groups.json').read_text());path_group={p:g for g in groups for p in g['members']};metadata={r['image_path']:r for r in read_csv(ROOT/latest['groupDirectory']/'grouped_manifest.csv')}
 candidates={r['image_path']:r for r in read_csv(ROOT/latest['representativeDirectory']/'candidate_manifest.csv')}
 base=ROOT/'ai_api/verification';paths=[base/'capture_selection_20261017T172736_078787Z/selection_proposals.json',base/'capture_audit_20261017T172917_949346Z/user_boundary_review.json',base/'scope_reference_20261017T174241_378142Z/user_reference_acceptance.json',base/'capture_search_20261017T175242_632360Z/user_capture_review.json',base/'scratch_scope_20261017T180713_695219Z/user_capture_review_v2.json',base/'label_review_import_20261017T042134_367319Z/corrected_user_review.json']
 hashes={str(p):sha(p) for p in paths};history=defaultdict(list)
 def event(path,status,source,notes,ident,target='not_specified'):
  if path not in metadata:raise ValueError('Image outside original train/internal manifests')
  history[path].append(dict(status=status,source=str(source),notes=notes,displayId=ident,targetDoor=target))
 for r in json.loads(paths[0].read_text()):event(r['imagePath'],'ACCEPTED_CAPTURE_CANDIDATE' if r['selectionProposal']=='PRIMARY_CAPTURE_CANDIDATE' else 'SUPPLEMENTARY_PARTIAL_VIEW',paths[0],r['observation']['notes'],r['id'])
 for r in json.loads(paths[1].read_text())['records']:event(r['imagePath'],'HOLD_BOUNDARY',paths[1],r['userObservation'],r['id'])
 for r in json.loads(paths[2].read_text())['records']:event(r['imagePath'],'ACCEPTED_CAPTURE_CANDIDATE',paths[2],r['priorUserObservation'],r['id'])
 for p in paths[3:5]:
  review=json.loads(p.read_text())
  if sha(Path(review['source']))!=review['sourceSHA256']:raise ValueError('Review evidence changed')
  for r in review['records']:
   decision=r.get('userDecision',r.get('decision'))
   if not decision:raise ValueError('Missing user decision')
   event(r['imagePath'],'ACCEPTED_CAPTURE_CANDIDATE' if decision=='USER_ACCEPTED_CAPTURE_CANDIDATE' else decision,p,r.get('userObservation',r.get('notes','')),r['id'],r.get('targetDoor','not_specified'))
 for r in json.loads(paths[5].read_text())['records']:
  if r['decision']=='CAPTURE_UNSUITABLE':event(r['representativeCandidate'],'HOLD_CAPTURE_UNSUITABLE',paths[5],r['reason'],r['id'])
 out=base/('capture_consolidated_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ'));out.mkdir()
 pair_rows=json.loads((base/'scratch_scope_20261017T180713_695219Z/selected_cases.json').read_text());pair=[next(r for r in pair_rows if r['id']==f'scratch_candidate_{n}') for n in [17,68]]
 evidence=[];thumbs=[]
 for r in pair:
  label=json.loads(Path(r['json_path']).read_text(encoding='utf-8-sig'))
  with Image.open(r['image_path']) as original:image=ImageOps.exif_transpose(original).convert('RGB')
  evidence.append(dict(id=r['id'],imagePath=r['image_path'],fileSHA256=sha(Path(r['image_path'])),decodedRGBSHA256=hashlib.sha256(image.tobytes()).hexdigest(),displaySize=image.size,sourceDateCaptured=label['images'][0].get('date_captured'),existingGroupId=r['group_id']))
  thumbs.append(image.resize((256,256)))
 cluster=dict(id='provisional_scene_scratch_17_68',status='suspected_same_physical_scene_not_confirmed',evidence=evidence,sameFile=evidence[0]['fileSHA256']==evidence[1]['fileSHA256'],sameDecodedRGB=evidence[0]['decodedRGBSHA256']==evidence[1]['decodedRGBSHA256'],thumbnailMAE256=sum(ImageStat.Stat(ImageChops.difference(*thumbs)).mean)/3,observations=['matching visible scratch layout, door seam, wheel and lower trim','source date_captured values differ by1second; metadata alone does not prove identity'],proposedTreatment='keep together in future split proposals; do not count as two independent defect events; retain originals',existingGroupsModified=False)
 dump(out/'scene_pair_evidence.json',cluster)
 pairpaths={r['image_path'] for r in pair};rows=[]
 for path,events in sorted(history.items()):
  last=events[-1];m=metadata[path];g=path_group[path]
  row=dict(image_path=path,group_id=g['groupId'],capture_status=last['status'],target_door=last['targetDoor'],proposed_class_id=int(candidates[path]['proposed_class_id']) if path in candidates else int(m['class_id']),source_category=m['categories'],label_basis='inherited_or_existing_proposal_not_newly_validated',original_split=m['originalSplit'],last_display_id=last['displayId'],capture_notes=last['notes'],provisional_scene_cluster=cluster['id'] if path in pairpaths else '',scene_independence_confirmed=False,source_json_path=m['json_path'],source_image_sha256=sha(Path(path)),latest_review=last['source'])
  rows.append(row)
 dump(out/'decision_history.json',dict(history=history,sourceHashes=hashes))
 for name,items in [('all_reviewed_images.csv',rows),('accepted_capture_candidates.csv',[r for r in rows if r['capture_status']=='ACCEPTED_CAPTURE_CANDIDATE']),('held_or_supplementary.csv',[r for r in rows if r['capture_status']!='ACCEPTED_CAPTURE_CANDIDATE'])]:
  with (out/name).open('w',newline='') as f:w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(items)
 accepted=[r for r in rows if r['capture_status']=='ACCEPTED_CAPTURE_CANDIDATE'];distribution=Counter((r['proposed_class_id'],r['source_category'],r['target_door']) for r in accepted)
 with (out/'accepted_distribution.csv').open('w',newline='') as f:w=csv.writer(f);w.writerow(['proposed_class_id','source_category','target_door','images']);w.writerows([(*k,v) for k,v in sorted(distribution.items())])
 assert len({r['image_path'] for r in rows})==len(rows);assert all(sha(Path(name))==h for name,h in hashes.items())
 dump(out/'summary.json',dict(status='consolidated_examples_not_training_dataset',reviewedImages=len(rows),historyEvents=sum(map(len,history.values())),captureStatusCounts=dict(Counter(r['capture_status'] for r in rows)),acceptedImages=len(accepted),acceptedKnownGroups=len({r['group_id'] for r in accepted}),acceptedClassCounts=dict(Counter(r['proposed_class_id'] for r in accepted)),acceptedDoorCounts=dict(Counter(r['target_door'] for r in accepted)),provisionalSceneClusters=1,acceptedConservativeSceneUnits=len({r['provisional_scene_cluster'] or r['group_id'] for r in accepted}),sourceHashes=hashes,scriptSHA256=sha(Path(__file__)),originalsModified=False,existingGroupsModified=False,splitChanged=False,trainingStarted=False,finalTestUsed=False,limitations='Capture examples only; unknown target doors retained; image labels not newly validated; conservative scene units are not verified independent physical parts'))
 print(out);print('status',Counter(r['capture_status'] for r in rows));print('accepted',len(accepted),Counter(r['proposed_class_id'] for r in accepted),Counter(r['target_door'] for r in accepted))
if __name__=='__main__':main()
