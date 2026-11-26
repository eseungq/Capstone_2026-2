"""Version a conservative role-block candidate; do not equate heuristic neighbors with identity."""
import csv,hashlib,json
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from ai_api.refresh_door_split import constrain
from ai_api.prepare_split_candidate import ROLES

def load(p):return json.loads(Path(p).read_text())
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def write(p,rows):
 with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def key(a,b):return tuple(sorted((a,b)))
def main():
 root=Path(__file__).resolve().parents[1];draft=Path(load(root/'outputs/door_revision_draft/latest.json')['directory']);imp=Path(load(root/'outputs/door_neighborhood_import/latest.json')['directory']);near=Path(load(root/'outputs/door_group_neighborhoods/latest.json')['directory']);groups=load(draft/'groups.json');member={p:g['groupId'] for g in groups for p in g['members']};assignments=read(draft/'candidate_roles.csv');gids={r['group_id'] for r in assignments};base_roles={r['group_id']:r['future_split'] for r in assignments};decisions=load(imp/'decisions.json')['records'];reviewed={key(member[r['validation_image']],member[r['train_image']]):r['decision'] for r in decisions};known=load(draft/'suspected_part_constraints.json');known_edges=[(c['duplicateGroupIds'][0],g) for c in known for g in c['duplicateGroupIds'][1:]]
 risk=[];exclusions=Counter();seen=set()
 for r in load(near/'ranked_neighborhood_candidates.json'):
  a,b=member[r['image_a']],member[r['image_b']];pair=key(a,b)
  if a==b:exclusions['now_same_photo']+=1;continue
  if pair in reviewed:exclusions['latest_human_review']+=1;continue
  if pair in seen:exclusions['repeated_group_pair']+=1;continue
  if a not in gids or b not in gids:raise ValueError('Risk group held or unknown')
  seen.add(pair);risk.append(dict(groupIds=[a,b],imagePaths=[r['image_a'],r['image_b']],reason='bounded direct neighbor of reviewed groups; identity unconfirmed',samePhotoConfirmed=False,rankScore=r['rankScore']))
 edges=known_edges+[tuple(r['groupIds']) for r in risk];candidate,sets=constrain(assignments,edges)
 for a,b in edges:
  roles={r['group_id']:r['future_split'] for r in candidate}
  if roles[a]!=roles[b]:raise ValueError('Risk boundary crosses')
 if {r['image_path'] for r in candidate}!={r['image_path'] for r in assignments}:raise ValueError('Lost representatives')
 out=root/'outputs/door_conservative_candidate'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);print('[CONSERVATIVE CANDIDATE]',out,flush=True)
 write(out/'candidate_roles.csv',candidate)
 for role in ROLES:write(out/(role+'.csv'),[r for r in candidate if r['future_split']==role])
 dump(out/'unconfirmed_risk_relations.json',risk);dump(out/'role_block_components.json',[dict(groupIds=c,role=roles[c[0]],identityMeaning='role constraint only; photo groups and labels remain separate') for c in sets]);dump(out/'role_changes.json',[dict(groupId=r['group_id'],before=base_roles[r['group_id']],after=r['future_split']) for r in candidate if base_roles[r['group_id']]!=r['future_split']])
 fp_path=root/'ai_api/verification/audit_followup_20261016T182934_010033Z/fingerprints.json';fp={r['image_path']:r for r in load(fp_path)};pool=[(r,fp[r['image_path']]['dhash']) for r in candidate];counts=Counter();comparisons=Counter()
 with (out/'all_role_visual_candidates.csv').open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.writer(f);w.writerow(['group_a','group_b','role_a','role_b','distance'])
  for i,(a,ha) in enumerate(pool):
   for b,hb in pool[i+1:]:
    if a['future_split']==b['future_split']:continue
    boundary='/'.join(sorted((a['future_split'],b['future_split'])));comparisons[boundary]+=1;distance=(ha^hb).bit_count()
    if distance<=8:counts[boundary]+=1;w.writerow([a['group_id'],b['group_id'],a['future_split'],b['future_split'],distance])
   if i%3000==0 or i+1==len(pool):print('[CANDIDATE BOUNDARIES]',i+1,'/',len(pool),flush=True)
 rolecounts=Counter(r['future_split'] for r in candidate)
 expected={'/'.join(sorted((a,b))):rolecounts[a]*rolecounts[b] for i,a in enumerate(ROLES) for b in ROLES[i+1:]};assert dict(comparisons)==expected
 distribution={role:dict(Counter(r['proposed_class_id'] for r in candidate if r['future_split']==role)) for role in ROLES};moved=sum(r['future_split']!=base_roles[r['group_id']] for r in candidate)
 sources=[draft/'summary.json',draft/'candidate_roles.csv',imp/'summary.json',imp/'decisions.json',near/'ranked_neighborhood_candidates.json',fp_path,Path(__file__).resolve()]
 result=dict(status='versioned_conservative_candidate_not_training_frozen',baseDraft=str(draft),importDirectory=str(imp),representatives=len(candidate),photoGroupsUnchanged=True,labelsUnchanged=True,riskRelations=len(risk),riskSourceExclusions=dict(exclusions),knownSuspectedConstraints=len(known),roleBlockComponents=len(sets),movedRepresentatives=moved,roleCounts=dict(rolecounts),roleClassCounts=distribution,knownOrRiskCrossings=0,allRoleBoundaryCoverageVerified=True,remainingHeuristicCandidateCounts=dict(counts),independenceEstablished=False,readyForTraining=False,currentTrainingManifestsChanged=False,currentModelChanged=False,trainingStarted=False,finalTestRead=False,reservedPixelsRead=False,sourceHashes={str(p):sha(p) for p in sources},limitations=['Unreviewed neighbors only affect this candidate role assignment; never same-photo identity or relabeling.','Residual candidates remain outside bounded neighborhoods.','Candidate score must not be presented as independent performance.','Current trained model is exposed to prior roles; cannot reuse as independent calibration/policy model.'])
 dump(out/'summary.json',result)
 dump(out/'artifact_lock.json',dict(status='immutable_candidate_snapshot_not_approved_training_split',artifacts={p.name:sha(p) for p in out.iterdir() if p.is_file()},trainingReady=False))
 (out/'REPORT.md').write_text(f'''# 12쌍 반영 후 보수적 분할 후보

새 검토에서 같은사진3쌍·실물의심1쌍·다른사진8쌍을 반영했다. 확정같은사진 연결은 누적17개이며 원래 실제학습분할의학습/검증경계를넘는관계는15개다. 대표{len(candidate):,}장의사진그룹과라벨은이후보에서도그대로유지했다.

## 보수적 처리 범위

앞서정한394개직접주변관계만범위로고정했다. 이번에확정된같은그룹과사람이판단한관계를제외하고{len(risk)}개미확인관계는같은사진이라고합치지않고같은역할에두는제약후보로만처리했다. 범위를계속새이웃으로확대해거대한그룹을만드는방식은쓰지않았다. 현재후보에서대표{moved}장의역할이변한다.

|역할|GOOD|DEFECT|합계|
|---|---:|---:|---:|
'''+''.join(f'|{r}|{distribution[r].get("0",0)}|{distribution[r].get("1",0)}|{rolecounts[r]}|\n' for r in ROLES)+f'''
## 실제 점검

알려진확정사진·실물의심·주변위험제약의교차0건, 대표누락·중복없음, 6개역할경계의비교수를다시확인했다. 역할이동으로새교차관계가생길수있어이전후보수만재사용하지않고전체시각지문검색을다시했다. 남은dHash후보수는summary.json에보존했다. 이는중복확정건수가아니다.

## 고정 여부

이폴더는파일해시를고정한검토가능한후보스냅샷이다. 실제학습에사용할분할로확정한것은아니고기존학습코드설정에도연결하지않았다. 위험묶음때문에검증분포가변할수있으며남은유사관계·동일실물독립성이미확정이므로독립성완료나ready로표현하지않는다. 기존모델·원본·학습CSV·API·DB를변경하지않고새학습을시작하지않았다. 최종시험1700장과보정·정책예약픽셀은열지않았다.

다음은이처리범위·클래스수·남은위험을확인해차기실험기준을고정하는단계다. 무조건또사람검토차수를늘리기보다보수적역할제약과잔여한계를명시해진행범위를결정한다. 최종성능보증을위한독립자료확보는별도로남는다.
''')
 dump(root/'outputs/door_conservative_candidate/latest.json',dict(directory=str(out),report=str(out/'REPORT.md'),trainingReady=False));print(json.dumps({k:v for k,v in result.items() if k!='sourceHashes'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
