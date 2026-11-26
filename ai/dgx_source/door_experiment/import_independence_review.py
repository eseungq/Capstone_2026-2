"""Import current independence judgments and version future group/constraint evidence."""
import argparse,csv,hashlib,json,shutil
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from ai_api.duplicate_groups import components
from ai_api.import_door_remaining_review import validate

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,obj):Path(p).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def read_csv(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--review',type=Path,required=True);args=parser.parse_args()
 root=Path(__file__).resolve().parents[1];current=load(root/'outputs/door_independence_review/latest.json');source=Path(current['directory']);queue=source/'review_queue.json';review=load(args.review);records=validate(review,load(queue),sha(queue));ss=load(source/'summary.json')
 for path,want in ss['source_sha256'].items():
  if sha(path)!=want:raise ValueError('Review source changed: '+path)
 if any(not r['reason'].strip() or r['decision']=='UNREVIEWED' for r in records):raise ValueError('Incomplete review')
 audit_pointer=load(root/'outputs/door_independence/latest.json');previous_confirmation=root/audit_pointer['confirmationDirectory'];previous=load(previous_confirmation/'user_confirmation.json')
 before=load(source/'future_groups.json');byid={g['groupId']:g for g in before};same=[r for r in records if r['decision']=='SAME_PHOTO'];suspect=[r for r in records if r['decision']=='POSSIBLY_SAME_PART']
 # Recheck only these reviewed train/model-selection originals, never reserved/test data.
 original_hashes={r['image_path']:r['sha256'] for r in load(Path(audit_pointer['directory'])/'current_file_hashes.json')}
 for r in records:
  for key in ['validation_image','train_image']:
   if sha(r[key])!=original_hashes[r[key]]:raise ValueError('Original image changed')
 out=root/'outputs/door_independence_import'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True);shutil.copyfile(args.review,out/'original_user_export.json')
 merged=[];mapping={}
 for comp in components(list(byid),[(r['validationGroup'],r['trainGroup']) for r in same]):
  members=sorted({p for gid in comp for p in byid[gid]['members']});gid='door_'+hashlib.sha256('\n'.join(members).encode()).hexdigest();classes=sorted({c for old in comp for c in byid[old]['classIds']});splits=sorted({s for old in comp for s in byid[old]['originalSplits']})
  merged.append(dict(groupId=gid,members=members,classIds=classes,labelConflict=len(classes)>1,originalSplits=splits,action='hold_for_label_resolution' if len(classes)>1 else 'keep_group_in_one_future_split'))
  for old in comp:mapping[old]=gid
 dump(out/'future_groups.json',merged)
 old_to_intermediate=load(source/'old_to_future_group.json');old_to_new={old:mapping[mid] for old,mid in old_to_intermediate.items()};dump(out/'old_to_future_group.json',old_to_new)
 proposal=load(root/'ai_api/verification/latest_data_proposal.json');old_constraints=load(root/proposal['suspectedPartConstraintFile']);constraint_records=[]
 for c in old_constraints:
  gids=sorted({old_to_new[g] for g in c['duplicateGroupIds']});constraint_records.append(dict(source='existing_suspected_relation',sourceId=c['constraintId'],groups=gids,confirmed_same_photo=False))
 for r in suspect:constraint_records.append(dict(source='new_review',caseId=r['caseId'],groups=sorted({mapping[r['validationGroup']],mapping[r['trainGroup']]}),reason=r['reason'],confirmed_same_photo=False))
 dump(out/'suspected_part_evidence.json',constraint_records)
 edges=[(c['groups'][0],g) for c in constraint_records for g in c['groups'][1:]]
 constraints=[dict(constraintId='suspected_part_'+hashlib.sha256('\n'.join(c).encode()).hexdigest(),duplicateGroupIds=c,action='keep_one_future_role_or_hold',applied=False) for c in components([g['groupId'] for g in merged],edges) if len(c)>1]
 dump(out/'future_suspected_part_constraints.json',constraints)
 dump(out/'decisions.json',dict(reviewer=review['reviewer'],reviewedAt=review['reviewedAt'],records=records,applied=False))
 supplemental=dict(source=str(queue),sourceSHA256=sha(queue),reviewSourceSHA256=sha(args.review),applied=False,records=[dict(displayNumber=int(r['caseId'].split('_')[-1]),train_image=r['train_image'],validation_image=r['validation_image'],judgment='user_confirmed_same_photo',reason=r['reason']) for r in same]);dump(out/'confirmed_same_photo_supplemental.json',supplemental)
 roles=read_csv(root/proposal['splitDirectory']/'candidate_roles.csv');by_path={r['image_path']:r for r in roles}
 combined=[dict(displayNumber=r['displayNumber'],source='previous_examples',train_image=r['train_image'],validation_image=r['validation_image']) for r in previous['records'] if r['judgment']=='user_confirmed_same_photo']+ [dict(caseId=r['caseId'],source='new_review',train_image=r['train_image'],validation_image=r['validation_image']) for r in same]
 confirmed_cross=[]
 for r in combined:
  a,b=by_path[r['validation_image']],by_path[r['train_image']]
  if a['future_split']!=b['future_split']:confirmed_cross.append(dict(r,roles=[a['future_split'],b['future_split']],proposed_classes=[a['proposed_class_id'],b['proposed_class_id']]))
 dump(out/'confirmed_current_cross_role_pairs.json',confirmed_cross)
 run=root/'outputs/door_next_training/door_visible_20261028_065548_667023';pred={r['image_path']:r for r in read_csv(run/'best_model_selection_predictions.csv')};affected={r['validation_image'] for r in confirmed_cross};impact=Counter(('TP' if pred[p]['class_id']=='1' else 'FP') if pred[p]['predicted_class']=='1' else ('FN' if pred[p]['class_id']=='1' else 'TN') for p in affected)
 result=dict(status='review_imported_confirmed_leakage_group_proposal_updated',reviewer=review['reviewer'],decisionCounts=dict(Counter(r['decision'] for r in records)),sourceReview=str(args.review.resolve()),sourceReviewSHA256=sha(args.review),queueSource=str(queue),queueSHA256=sha(queue),recordCount=len(records),originalsModified=False,splitApplied=False,newConfirmedSamePhotoLinks=len(same),newSuspectedPartRelations=len(suspect),confirmedCrossRolePairsTotal=len(confirmed_cross),affectedModelSelectionImages=len(affected),affectedSavedConfusion=dict(impact),futureGroupCount=len(merged),previousOriginalGroupCount=13221,knownSuspectedConstraintComponents=len(constraints),trainingStarted=False,modelChanged=False,finalTestRead=False,reservedImagesRead=False,independenceEstablished=False,sourceHashes={str(p):sha(p) for p in [queue,source/'summary.json',source/'future_groups.json',previous_confirmation/'user_confirmation.json',Path(__file__).resolve()]})
 dump(out/'summary.json',result)
 (out/'REPORT.md').write_text(f'''# 独立性検討の反映
'''.replace('独立性検討の反映','独立性'.replace('独立性','독립성 검토 반영'))+f'''
검토자: {review['reviewer']}. 새10쌍의 대기열SHA·사례ID·원본 메타데이터·원본 파일 해시를 대조했다. 내보낸 원문을 복사 보존했다.

- 같은 사진6쌍: 2·4·5·6·8·10번.
- 같은 실물 의심1쌍: 7번. “같은 사진인 것 같은데 확실치 않음”을 확정으로 승격하지 않았다.
- 다른 사진3쌍: 1·3·9번. 근거 “근거 없음”을 그대로 보존하며 다른 실물의 독립성까지 확인했다고 해석하지 않는다.

앞서 같은 사진으로 확인한2쌍과 합쳐 현재 학습/모델 선택 교차 같은 사진은{len(confirmed_cross)}쌍, 관련 모델 선택 이미지는{len(affected)}장이다. 저장 예측상 해당 이미지의 분포는{dict(impact)}다. 모두 맞혔더라도 외운 영향의 크기를 이 사실만으로 추정할 수 없다. 이 사진들만 빼고 점수를 다시 계산해 독립 성능으로 발표하지 않는다.

새 같은 사진 그룹은{len(merged):,}개로 정리했으며 원본과 기존 학습manifest에는 적용하지 않았다. 기존 사용자 확인 그룹을 보존하고 이번6개 연결만 추가했다. 원본 라벨 충돌의 기존 수정·보류 판단은 여전히 별도 근거로 유지해야 하며 새 그룹의 raw classIds만으로 그 판단을 덮어쓰면 안 된다.

같은 실물 의심은 기존9개 관계와 함께{len(constraints)}개 보수적 제약 묶음으로 저장했다. 같은 사진으로 병합하거나 불량 라벨을 전파하지 않는다. 차기 분할에서 한 역할에 두거나 보류한다.

다음은 확정그룹+의심제약을 반영한 대표·분할 초안을 만들고, 수정된 모든 역할 경계에 대해 유사 검색 범위가 누락되지 않는지 점검하는 것이다. 기존12799후보를 모두 검토한 것은 아니므로 새분할을 곧바로 독립으로 인증하지 않는다. 고위험 미검토 관계를 확인하기 전 다시 학습을 시작하지 않는다.

원본·현재 모델·기존CSV·최종시험1700장·API·DB는 변경하지 않았다. 실제 재학습과 배포는 아직 수행하지 않았다.
''')
 dump(root/'outputs/door_independence_import/latest.json',dict(directory=str(out),report=str(out/'REPORT.md'),independenceEstablished=False));current.update(reviewed=True,importDirectory=str(out),decisionCounts=result['decisionCounts']);dump(root/'outputs/door_independence_review/latest.json',current)
 audit_pointer.update(latestReviewImport=str(out),confirmedCrossRolePairs=len(confirmed_cross),affectedModelSelectionImages=len(affected),status='confirmed_cross_role_same_photo_found');dump(root/'outputs/door_independence/latest.json',audit_pointer)
 print(json.dumps({k:v for k,v in result.items() if k!='sourceHashes'},ensure_ascii=False,indent=2));print('[REVIEW IMPORT]',out)
if __name__=='__main__':main()
