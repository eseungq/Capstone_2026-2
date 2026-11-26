"""Preserve 12-pair judgments and update future evidence; never relabel or train."""
import argparse,csv,hashlib,json,shutil
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from ai_api.duplicate_groups import components
from ai_api.import_door_remaining_review import validate

def load(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--review',type=Path,required=True);a=parser.parse_args();root=Path(__file__).resolve().parents[1];page_pointer=root/'outputs/door_neighborhood_review/latest.json';pointer=load(page_pointer);page=Path(pointer['directory']);queue=page/'review_queue.json';review=load(a.review);records=validate(review,load(queue),sha(queue));summary=load(page/'summary.json')
 for p,digest in summary['sourceHashes'].items():
  if sha(p)!=digest:raise ValueError('Evidence changed: '+p)
 if len(records)!=12 or any(r['decision']=='UNREVIEWED' or not r['reason'].strip() for r in records):raise ValueError('Incomplete 12-pair review')
 draft=Path(summary['sourceDraft']);groups=load(draft/'groups.json');byid={g['groupId']:g for g in groups};old_import=Path(load(draft/'summary.json')['sourceImport']);same=[r for r in records if r['decision']=='SAME_PHOTO'];suspect=[r for r in records if r['decision']=='POSSIBLY_SAME_PART'];out=root/'outputs/door_neighborhood_import'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
 shutil.copyfile(a.review,out/'original_user_export.json');dump(out/'decisions.json',dict(reviewer=review['reviewer'],reviewedAt=review['reviewedAt'],records=records,applied=False))
 merged=[];mapping={}
 for comp in components(list(byid),[(r['validationGroup'],r['trainGroup']) for r in same]):
  members=sorted({p for gid in comp for p in byid[gid]['members']});gid='door_'+hashlib.sha256('\n'.join(members).encode()).hexdigest();classes=sorted({c for old in comp for c in byid[old]['classIds']});old_splits=sorted({s for old in comp for s in byid[old]['originalSplits']})
  merged.append(dict(groupId=gid,members=members,classIds=classes,labelConflict=len(classes)>1,originalSplits=old_splits,action='hold_for_label_resolution' if len(classes)>1 else 'keep_group_in_one_future_split'))
  for old in comp:mapping[old]=gid
 dump(out/'future_groups.json',merged)
 original_mapping=load(old_import/'old_to_future_group.json');original_to_new={old:mapping[mid] for old,mid in original_mapping.items()};dump(out/'old_to_future_group.json',original_to_new)
 old_constraints=load(draft/'suspected_part_constraints.json');relations=[]
 for c in old_constraints:
  ids=sorted({mapping[g] for g in c['duplicateGroupIds']});relations.extend((ids[0],g) for g in ids[1:])
 for r in suspect:relations.append((mapping[r['validationGroup']],mapping[r['trainGroup']]))
 constraints=[dict(constraintId='suspected_part_'+hashlib.sha256('\n'.join(c).encode()).hexdigest(),duplicateGroupIds=c,action='keep_one_future_role_or_hold',applied=False) for c in components([g['groupId'] for g in merged],relations) if len(c)>1]
 dump(out/'future_suspected_part_constraints.json',constraints)
 supplemental=dict(source=str(queue),sourceSHA256=sha(queue),reviewSourceSHA256=sha(a.review),applied=False,records=[dict(displayNumber=r['displayNumber'],train_image=r['train_image'],validation_image=r['validation_image'],judgment='user_confirmed_same_photo',reason=r['reason']) for r in same]);dump(out/'confirmed_same_photo_supplemental.json',supplemental)
 prior_links=load(old_import/'all_confirmed_same_photo_links.json');links=prior_links+[dict(caseId=r['caseId'],source='12_pair_neighborhood_review',train_image=r['train_image'],validation_image=r['validation_image']) for r in same];dump(out/'all_confirmed_same_photo_links.json',links)
 original_groups=load(root/'ai_api/verification/duplicate_groups_20261027T185537_271845Z/groups.json');orig_membership={p:g['groupId'] for g in original_groups for p in g['members']};old_roles={r['group_id']:r['future_split'] for r in read(root/'outputs/door_split_refresh/20261028T053734_609112Z/candidate_roles.csv')}
 prior_run_cross=[]
 for r in links:
  ra=old_roles.get(orig_membership[r['validation_image']],'HOLD');rb=old_roles.get(orig_membership[r['train_image']],'HOLD')
  if {ra,rb}=={'train','model_selection'}:prior_run_cross.append(dict(r,roles=[ra,rb]))
 dump(out/'confirmed_crossings_in_trained_run.json',prior_run_cross)
 membership={p:g['groupId'] for g in merged for p in g['members']};assert len(membership)==13593
 assert len(membership)==sum(len(g['members']) for g in merged)
 for g in groups:assert len({membership[p] for p in g['members']})==1
 for r in records:
  if r['decision']=='SAME_PHOTO':assert membership[r['validation_image']]==membership[r['train_image']]
  elif r['decision']=='DIFFERENT':assert membership[r['validation_image']]!=membership[r['train_image']]
 band_counts={'neighborhood':dict(Counter(r['decision'] for r in records))}
 labels={r['image_path']:r['proposed_class_id'] for r in read(draft/'candidate_roles.csv')}
 label_conflicts=[r['caseId'] for r in same if labels[r['validation_image']]!=labels[r['train_image']]]
 result=dict(status='12_pair_neighborhood_review_imported',reviewer=review['reviewer'],sourceReview=str(a.review.resolve()),sourceReviewSHA256=sha(a.review),queueSource=str(queue),queueSHA256=sha(queue),recordCount=12,decisionCounts=dict(Counter(r['decision'] for r in records)),priorityBandDecisions=band_counts,originalsModified=False,splitApplied=False,newConfirmedSamePhotoLinks=len(same),newSuspectedRelations=len(suspect),totalConfirmedLinks=len(links),confirmedLinksCrossingActualTrainedRun=len(prior_run_cross),newSamePhotoLabelDisagreementCases=label_conflicts,futureGroupCount=len(merged),futureSuspectedConstraintComponents=len(constraints),futureSplitNeedsRefresh=True,independenceEstablished=False,trainingStarted=False,currentModelChanged=False,finalTestRead=False,reservedPixelsRead=False,sourceDraft=str(draft),sourceHashes={str(p):sha(p) for p in [page/'summary.json',queue,draft/'groups.json',draft/'suspected_part_constraints.json',old_import/'all_confirmed_same_photo_links.json',Path(__file__).resolve()]})
 dump(out/'summary.json',result)
 (out/'REPORT.md').write_text(f"""# 주변 관계 12쌍 검토 결과

검토자: {review['reviewer']}. 대기열SHA·사례 메타데이터·12개 판단을 대조하고 원본 내보내기를 보존했다.

- 같은 사진: 1·6·9번, 3쌍.
- 실물 의심: 3번, 1쌍. 각도는 다르지만 흠집 패턴이 같다는 관찰을 보존하고 같은 사진으로 확정하지 않았다.
- 다른 사진: 나머지 8쌍. 다른 실물의 독립성까지 보장한 것으로 해석하지 않는다.

누적 같은 사진 연결은 {len(links)}개이며, 원래 학습한 분할의 학습/모델 선택을 넘는 관계는 {len(prior_run_cross)}개다. 새 그룹은 {len(merged)}개, 의심 제약 묶음은 {len(constraints)}개다. 제안 라벨 불일치 사례는 {label_conflicts}다.

기존 모델·원본·실제 학습 분할·API·DB는 변경하지 않았다. 최종 시험1700장과 예약 이미지 픽셀에는 접근하지 않았고 재학습하지 않았다. 다음은 미확인 주변 관계의 보수적 역할 제약과 새 분할 후보를 계산하는 것이다. 이번12쌍이 전체 독립성 완료를 뜻하지는 않는다.
""")
 dump(root/'outputs/door_neighborhood_import/latest.json',dict(directory=str(out),report=str(out/'REPORT.md'),independenceEstablished=False));pointer.update(reviewed=True,importDirectory=str(out),decisionCounts=result['decisionCounts']);dump(page_pointer,pointer)
 print(json.dumps({k:v for k,v in result.items() if k!='sourceHashes'},ensure_ascii=False,indent=2));print('[12 REVIEW IMPORT]',out)
if __name__=='__main__':main()
