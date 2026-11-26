"""Rank direct neighborhoods of confirmed/suspected groups; propose constraints, never identity merges."""
import base64,csv,hashlib,json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image
from ai_api.duplicate_groups import components
from ai_api.rank_similarity import metrics
from ai_api.refresh_door_split import constrain
from door_experiment.triage_independence import fingerprint

def load(p):return json.loads(Path(p).read_text())
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 root=Path(__file__).resolve().parents[1];draft=Path(load(root/'outputs/door_revision_draft/latest.json')['directory']);ds=load(draft/'summary.json');imp=Path(ds['sourceImport']);groups=load(draft/'groups.json');membership={p:g['groupId'] for g in groups for p in g['members']};links=load(imp/'all_confirmed_same_photo_links.json');anchors={membership[r['train_image']] for r in links};constraints=load(draft/'suspected_part_constraints.json');sus={g for c in constraints for g in c['duplicateGroupIds']};allrows=read(draft/'all_role_visual_candidates.csv');current=[r for r in allrows if {r['role_a'],r['role_b']}=={'train','model_selection'}];pending=[r for r in current if r['previous_judgment']=='UNREVIEWED'];near=[r for r in pending if {r['group_a'],r['group_b']}&(anchors|sus)];distant=[r for r in pending if r not in near]
 out=root/'outputs/door_group_neighborhoods'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);print('[NEIGHBORHOOD OUTPUT]',out,flush=True)
 cache_path=Path(load(root/'outputs/door_independence_triage/latest.json')['directory'])/'pixel_feature_cache.json';cache={r['path']:r for r in load(cache_path)};fps={};paths=sorted({r[k] for r in near for k in ['image_a','image_b']});missing=[];oldfp_path=root/'ai_api/verification/audit_followup_20261016T182934_010033Z/fingerprints.json';expected={r['image_path']:r['sha256'] for r in load(oldfp_path)}
 for path in paths:
  if sha(path)!=expected[path]:raise ValueError('Source file changed')
  if path in cache:
   c=cache[path]
   if c['file_sha256']!=expected[path]:raise ValueError('Cache source differs')
   fps[path]=dict(rgb=Image.frombytes('RGB',(64,64),base64.b64decode(c['rgb64_b64'])),edge=Image.frombytes('L',(62,62),base64.b64decode(c['edge62_b64'])),aspect=c['display_size'][0]/c['display_size'][1],size=c['display_size'],pixel_sha256=c['display_rgb_sha256'])
  else:missing.append(path)
 with ThreadPoolExecutor(max_workers=2) as pool:
  for path,v in pool.map(fingerprint,missing):
   if v['file_sha256']!=expected[path]:raise ValueError('Decoded source changed')
   fps[path]=v
 for r in near:
  a,b=fps[r['image_a']],fps[r['image_b']];r.update(metrics((a['rgb'],a['edge'],a['aspect']),(b['rgb'],b['edge'],b['aspect'])));r['touches_confirmed_group']=bool({r['group_a'],r['group_b']}&anchors);r['exact_display_pixels']=a['size']==b['size'] and a['pixel_sha256']==b['pixel_sha256']
 near.sort(key=lambda r:(not r['touches_confirmed_group'],r['rankScore'],int(r['distance']),r['image_a'],r['image_b']));dump(out/'ranked_neighborhood_candidates.json',near)
 nodes={r[k] for r in near for k in ['group_a','group_b']};edges=[(r['group_a'],r['group_b']) for r in near];sets=components(nodes,edges);dump(out/'review_neighborhood_components.json',[dict(id=f'neighborhood_{i+1:02d}',groupIds=c,identityMeaning='review scheduling graph only; not same-photo or same-part confirmation') for i,c in enumerate(sorted(sets,key=lambda c:(-len(c),c)))])
 units={g:g for g in {r['group_id'] for r in read(draft/'candidate_roles.csv')}}
 for c in constraints:
  for g in c['duplicateGroupIds']:units[g]=c['constraintId']
 selected=[];used=set()
 for r in near:
  ends={units[r['group_a']],units[r['group_b']]}
  if used&ends:continue
  selected.append(r);used.update(ends)
  if len(selected)==12:break
 dump(out/'next_priority_pairs_proposal.json',selected)
 # Quantify a conservative option only; preserve each separate photo and do not apply it to training.
 assignments=read(draft/'candidate_roles.csv');known_edges=[(c['duplicateGroupIds'][0],g) for c in constraints for g in c['duplicateGroupIds'][1:]];scenario,scenario_sets=constrain(assignments,known_edges+edges);before={r['group_id']:r['future_split'] for r in assignments};moves=[dict(groupId=r['group_id'],before=before[r['group_id']],after=r['future_split']) for r in scenario if r['future_split']!=before[r['group_id']]]
 dump(out/'conservative_role_block_option.json',dict(status='unapplied_option_not_identity_evidence',meaning='Keep heuristic neighborhood photos separate, but place their review-risk blocks in one role; may sacrifice balance and must be reviewed before use',groupsUnchanged=True,roleCounts=dict(Counter(r['future_split'] for r in scenario)),roleClassCounts={role:dict(Counter(r['proposed_class_id'] for r in scenario if r['future_split']==role)) for role in ['train','model_selection','calibration_fit','policy_development']},moves=moves,applied=False))
 summary=dict(status='neighborhoods_ranked_no_new_human_review_requested_yet',sourceDraft=str(draft),representatives=ds['representatives'],roleCounts=ds['role_counts'],confirmedSamePhotoLinks=len(links),knownSuspectedConstraintComponents=len(constraints),sourceTrainSelectionCandidates=len(current),priorReviewedOrConstrainedPairs=len(current)-len(pending),pendingPairs=len(pending),directNeighborhoodPairs=len(near),directNeighborhoodGroups=len(nodes),neighborhoodComponents=len(sets),largestNeighborhoodGroups=max(map(len,sets)),touchingConfirmedPhotoPairs=sum(r['touches_confirmed_group'] for r in near),otherPendingPairs=len(distant),pixelSourcesChecked=len(paths),cachedPixelSources=len(paths)-len(missing),newPixelSources=len(missing),exactDisplayPixelPairs=sum(r['exact_display_pixels'] for r in near),nextPriorityPairsProposed=len(selected),conservativeRoleBlockOptionMoves=len(moves),conservativeRoleBlockOptionApplied=False,newSamePhotoMerges=0,currentManifestsChanged=False,modelChanged=False,trainingStarted=False,finalTestRead=False,reservedPixelsRead=False,independenceEstablished=False,sourceHashes={str(p):sha(p) for p in [draft/'summary.json',draft/'all_role_visual_candidates.csv',imp/'summary.json',cache_path,Path(__file__).resolve()]})
 dump(out/'summary.json',summary);dump(root/'outputs/door_group_neighborhoods/latest.json',dict(directory=str(out),report=str(out/'REPORT.md'),trainingReady=False))
 report=f'''# 確認済みグループ周辺の未検討関係
'''.replace('確認済みグループ周辺の未検討関係','확인된 그룹 주변의 미검토 관계')+f'''
## 초안 갱신

확정같은사진{len(links)}개연결·의심제약{len(constraints)}묶음을반영했다. 대표{ds['representatives']:,}장, 학습{ds['role_counts']['train']:,}장·모델선택{ds['role_counts']['model_selection']:,}장·보정예약{ds['role_counts']['calibration_fit']}장·정책예약{ds['role_counts']['policy_development']}장이다. 알려진사진그룹·의심제약교차0건, 모든6개역할경계검색을확인했다.

## 주변 관계 자동 정리

현재학습/모델선택유사후보{len(current):,}쌍중미검토{len(pending):,}쌍이다. 확인된그룹과의심단위에직접연결된{len(near)}쌍을우선분리했다. 이중확정사진그룹에닿는관계는{sum(r['touches_confirmed_group'] for r in near)}쌍이다. 나머지{len(distant):,}쌍을다른사진이나안전하다고처리하지않고보존했다.

주변관계는{len(nodes)}개사진그룹을{len(sets)}개검토일정묶음으로연결한다. 최대{max(map(len,sets))}개그룹묶음은같은사진·실물확정그룹이아니다. 반복되는구도와단색표면으로이어질수있어자동중복병합하지않았다.

원본{len(paths)}장의파일SHA를재확인했고기존픽셀특징{len(paths)-len(missing)}장을재사용, 추가{len(missing)}장을디코딩했다. 전체표시RGB픽셀완전일치{summary['exactDisplayPixelPairs']}쌍이다. 완전일치없음은같은사진·실물이없다는뜻이아니다.

## 다음 확인 범위

색상·내부경계·구도점수는순서만정하며동일성판정값이아니다. 확인된사진그룹주변을먼저보고검토단위반복을피한최대12쌍의우선대기열을저장했다. 이번에는새화면을반복생성하거나이12쌍만보면끝난다고요청하지않았다. 기존24쌍은다시묻지않는다.

## 검토 부담을 줄이는 보수적 대안

주변의미확인관계를같은사진으로합치는대신, 별도사진을유지하고분할위험묶음만같은역할에두는대안을계산했다. 기존제약과함께적용하면대표{len(moves)}장의역할이바뀐다. 상세분포는conservative_role_block_option.json에저장했다. 오탐관계까지묶을수있고검증분포·균형을바꾸므로현재초안이나학습에적용하지않았다. 이대안도전체독립성을보증하지않는다.

## 보존과 한계

현재모델은옛학습/검증에노출돼있어새초안의예약자료가현재모델에독립적으로바뀌지는않는다. 새초안을재학습설정에연결하지않았고원본·기존CSV·모델·API·DB는그대로다. 현재새초안의학습/모델선택이미지만픽셀확인했고보정·정책예약픽셀과최종시험1700장은열지않았다. 현재점수는누수가확인된기존모델선택결과로만보존한다.
'''
 (out/'REPORT.md').write_text(report);print('[NEIGHBORHOOD REPORT]',out/'REPORT.md');print(json.dumps({k:v for k,v in summary.items() if k!='sourceHashes'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
