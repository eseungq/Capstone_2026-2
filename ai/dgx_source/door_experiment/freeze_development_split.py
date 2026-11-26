"""Lock a development-only DOOR split snapshot, preserving explicit residual-risk limits."""
import csv,hashlib,json,shutil
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from door_experiment.train import CONFIG

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
 with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def main():
 root=Path(__file__).resolve().parents[1];source=Path(load(root/'outputs/door_conservative_candidate/latest.json')['directory']);summary=load(source/'summary.json');draft=Path(summary['baseDraft']);imp=Path(summary['importDirectory'])
 for name,digest in load(source/'artifact_lock.json')['artifacts'].items():
  if sha(source/name)!=digest:raise ValueError('Candidate changed: '+name)
 rows=read(source/'candidate_roles.csv');roles={r['group_id']:r['future_split'] for r in rows};groups=load(draft/'groups.json');membership={p:g['groupId'] for g in groups for p in g['members']};links=load(imp/'all_confirmed_same_photo_links.json')
 for r in links:
  if membership[r['train_image']]!=membership[r['validation_image']]:raise ValueError('Confirmed identity split across groups')
 out=root/'outputs/door_experiment_freeze'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 for role in ('train','model_selection','calibration_fit','policy_development'):shutil.copy2(source/(role+'.csv'),out/(role+'.csv'))
 shutil.copy2(source/'candidate_roles.csv',out/'candidate_roles.csv');shutil.copy2(draft/'groups.json',out/'groups.json');shutil.copy2(root/'configs/door_image_label_policy_v2.json',out/'label_policy.json');shutil.copy2(source/'unconfirmed_risk_relations.json',out/'unconfirmed_risk_relations.json');shutil.copy2(draft/'suspected_part_constraints.json',out/'human_suspected_constraints.json');shutil.copy2(imp/'all_confirmed_same_photo_links.json',out/'confirmed_same_photo_links.json')
 constraints=[]
 for i,c in enumerate(load(source/'role_block_components.json')):
  if len({roles[g] for g in c['groupIds']})!=1:raise ValueError('Role block crosses')
  constraints.append(dict(constraintId=f'frozen_role_block_{i+1:02d}',duplicateGroupIds=c['groupIds'],role=c['role'],identityMeaning='role constraint combining human suspicion and bounded heuristic risk; never same-photo identity'))
 dump(out/'role_constraints.json',constraints)
 ledger=read(draft/'all_images_ledger.csv')
 for r in ledger:r['future_split']=roles.get(r['group_id'],'HOLD')
 write(out/'all_images_ledger.csv',ledger);assert len(ledger)==13593
 dump(out/'training_hyperparameters.json',CONFIG)
 code_paths=[root/'door_experiment'/name for name in ['train.py','preflight.py','run_gpu.sh','review.py']]
 (out/'code').mkdir()
 for p in code_paths:shutil.copy2(p,out/'code'/p.name)
 artifact_paths=[p for p in out.iterdir() if p.is_file()]
 config=dict(experimentVersion='door-visible-region-conservative-v2',status='development_split_locked_independence_open',policy=str((out/'label_policy.json').relative_to(root)),manifests={role:str((out/(role+'.csv')).relative_to(root)) for role in ['train','model_selection']},reserved_manifests={role:str((out/(role+'.csv')).relative_to(root)) for role in ['calibration_fit','policy_development']},constraints=str((out/'role_constraints.json').relative_to(root)),training_config=str((out/'training_hyperparameters.json').relative_to(root)),expected_counts={role:dict(Counter(r['proposed_class_id'] for r in rows if r['future_split']==role)) for role in ['train','model_selection']},sha256={str(p.relative_to(root)):sha(p) for p in artifact_paths},code_sha256={str(p.relative_to(root)):sha(p) for p in code_paths},initialization='ImageNet pretrained only; no prior DOOR checkpoint resume',independence_established=False,calibration_method=None,pass_threshold=None,limitations=['Confirmed duplicate links and bounded risk-role crossings are controlled, but remaining similarity and physical-part independence are unresolved.','GOOD applies to visible target DOOR only; inherited source labels not all manually verified.','Validation is for model selection; cannot claim independent final or fixed-camera factory performance.','Previously trained model remains exposed to earlier roles; do not fit calibration or policy for it using this newly assigned split.'],humanConfirmedLinks=len(links),humanSuspectedComponents=15,heuristicRoleRelations=summary['riskRelations'],remainingHeuristicCandidateCounts=summary['remainingHeuristicCandidateCounts'])
 dump(out/'experiment_config.json',config);dump(root/'configs/door_visible_region_experiment_v2.json',config)
 manifest=dict(status='development_split_and_protocol_locked_gpu_check_pending',sourceCandidate=str(source),experimentConfig=str((root/'configs/door_visible_region_experiment_v2.json').relative_to(root)),experimentConfigSHA256=sha(out/'experiment_config.json'),sourceCandidateSummarySHA256=sha(source/'summary.json'),roleCounts=summary['roleCounts'],roleClassCounts=summary['roleClassCounts'],confirmedSamePhotoLinks=len(links),representatives=len(rows),knownAndRiskRoleCrossings=0,independenceEstablished=False,readyForDevelopmentTraining=False,gpuCheckStatus='pending_on_this_frozen_config',trainingStarted=False,finalTestRead=False,originalLabelsChanged=False,currentModelChanged=False,currentOriginalManifestsChanged=False,sourceHashes={str(p):sha(p) for p in [source/'summary.json',source/'artifact_lock.json',draft/'summary.json',imp/'summary.json',Path(__file__).resolve()]})
 dump(out/'freeze_record.json',manifest);dump(root/'outputs/door_experiment_freeze/latest.json',dict(directory=str(out),experimentConfig=str(root/'configs/door_visible_region_experiment_v2.json'),report=str(out/'README.md'),independenceEstablished=False,trainingStarted=False))
 (out/'README.md').write_text('''# DOOR 차기 개발 실험 고정본

## 고정 범위

학습9262장·모델선택1959장·보정예약990장·정책예약990장을 고정했다. 같은사진17개연결, 사람의 실물의심15개묶음, 제한된주변 미확인관계382개의역할제약을보존했다. 미확인사진을같은사진으로병합하지않고라벨도전파하지않았다. 분류기준0.5·전처리·FP32·학습설정은이전실험과같다. 새실험은ImageNet초기값에서시작한다.

## 이번 고정의 의미

고정본은 수정이필요하면새버전으로생성한다. 파일·정책·그룹·역할제약·학습설정·실행코드해시를검사한다. 이전분할은그대로보존하고새v2설정을명시해야실행한다. 학습스크립트는train/model_selection이미지만읽고보정·정책예약은학습에사용하지않는다. 예약CSV는보존·해시검사에만사용한다. 최종시험1700장은열지않았다.

독립성을인증한데이터셋은아니다. 남은유사후보·실물독립성·원천라벨한계가있고,검증은모델선택용이다. 보수적역할묶음으로검증분포도달라졌다. 현재모델의97.68%·F197.91%를독립성능으로바꿔해석하거나이분할로기존모델의독립보정자료를얻었다고표현하지않는다.

## 고정한 평가 절차

매회차 모델선택DEFECT F1으로최고모델을저장하며동점은앞회차를유지한다. 정확도·precision·recall·FP/FN·loss를함께기록한다. 최고회차를고른뒤단독/배치점수재현과오판·CAM을별도검토한다. 사후지표선택이나허용오차완화로통과시키지않는다. 확률보정·정책평가·AUTO_PASS기준은별도후속이며숫자를임의설정하지않았다.

## 다음 실행

먼저v2설정을지정해GPU준비검사만수행한다. 이번에GPU실행·학습은하지않았다. Docker권한제한은재시도하거나변경하지않았다. 기본터미널명령은프로젝트door_experiment/README.md의‘고정v2설정’절을참고한다.
''')
 print('[FROZEN CONFIG]',root/'configs/door_visible_region_experiment_v2.json');print('[FREEZE RECORD]',out/'freeze_record.json')
if __name__=='__main__':main()
