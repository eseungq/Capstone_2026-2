"""Preserve 24-pair judgments and update future evidence; never relabel or train."""
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
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--review',type=Path,required=True);a=parser.parse_args();root=Path(__file__).resolve().parents[1];page_pointer=root/'outputs/door_triage_review/latest.json';pointer=load(page_pointer);page=Path(pointer['directory']);queue=page/'review_queue.json';review=load(a.review);records=validate(review,load(queue),sha(queue));summary=load(page/'summary.json')
 for p,digest in summary['sourceHashes'].items():
  if sha(p)!=digest:raise ValueError('Evidence changed: '+p)
 if len(records)!=24 or any(r['decision']=='UNREVIEWED' or not r['reason'].strip() for r in records):raise ValueError('Incomplete 24-pair review')
 draft=Path(summary['sourceDraft']);groups=load(draft/'groups.json');byid={g['groupId']:g for g in groups};old_import=Path(load(draft/'summary.json')['sourceImport']);same=[r for r in records if r['decision']=='SAME_PHOTO'];suspect=[r for r in records if r['decision']=='POSSIBLY_SAME_PART'];out=root/'outputs/door_triage_import'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
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
 prior_links=load(old_import/'confirmed_current_cross_role_pairs.json');links=prior_links+[dict(caseId=r['caseId'],source='24_pair_review',train_image=r['train_image'],validation_image=r['validation_image']) for r in same];dump(out/'all_confirmed_same_photo_links.json',links)
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
 band_counts={b:dict(Counter(r['decision'] for r in records if r['priority_band']==b)) for b in ['high','uncertain','lower']}
 label_conflicts=[r['caseId'] for r in same if r['label_disagreement']]
 result=dict(status='24_pair_review_imported_further_risk_review_needed',reviewer=review['reviewer'],sourceReview=str(a.review.resolve()),sourceReviewSHA256=sha(a.review),queueSource=str(queue),queueSHA256=sha(queue),recordCount=24,decisionCounts=dict(Counter(r['decision'] for r in records)),priorityBandDecisions=band_counts,originalsModified=False,splitApplied=False,newConfirmedSamePhotoLinks=len(same),newSuspectedRelations=len(suspect),totalConfirmedLinks=len(links),confirmedLinksCrossingActualTrainedRun=len(prior_run_cross),newSamePhotoLabelDisagreementCases=label_conflicts,futureGroupCount=len(merged),futureSuspectedConstraintComponents=len(constraints),futureSplitNeedsRefresh=True,independenceEstablished=False,trainingStarted=False,currentModelChanged=False,finalTestRead=False,reservedPixelsRead=False,sourceDraft=str(draft),sourceHashes={str(p):sha(p) for p in [page/'summary.json',queue,draft/'groups.json',draft/'suspected_part_constraints.json',old_import/'confirmed_current_cross_role_pairs.json',Path(__file__).resolve()]})
 dump(out/'summary.json',result)
 (out/'REPORT.md').write_text(f'''# 24쌍 검토 결과 반영

검토자{review['reviewer']}. 대기열SHA256·24개사례·메타데이터를 대조하고 원본내보내기를 보존했다. 중간백업 파일은 완료결과로 사용하지 않았다.

|구간|같은사진|실물의심|다른사진|
|---|---:|---:|---:|
'''+''.join(f'|{b}|{band_counts[b].get("SAME_PHOTO",0)}|{band_counts[b].get("POSSIBLY_SAME_PART",0)}|{band_counts[b].get("DIFFERENT",0)}|\n' for b in ['high','uncertain','lower'])+f'''
같은사진:6·8·9·10·14·16번. 실물의심:1·4·11·12번. 나머지14쌍은다른사진이다. 실물의심은같은사진으로합치지않았다. 1번의판단불확실,4·11번의흠집패턴,12번의굴곡유사라는원문을그대로보존했다. 굴곡·구도만으로같은실물을확정하지않는다.

앞서확정한8개연결에이번6개연결을더해14개같은사진연결을보존했다. 이중실제로학습한이전분할의train/model_selection경계를넘는관계는{len(prior_run_cross)}개다. 이번검토는새초안경계기준이므로14개모두가이전모델의교차중복이라고자동해석하지않았다.

새그룹초안은{len(merged)}개, 의심제약묶음은{len(constraints)}개다. 이번같은사진중제안라벨이다른사례는{label_conflicts}이다. 원본라벨·기존수동라벨수정·보류는유지하며현재새분할CSV도아직갱신하지않았다.

높은우선순위16쌍에서6쌍의중복과4쌍의의심관계가나왔다. 자동선별이실제확인대상을찾는데도움이됐지만남은고위험후보를그대로무관계로처리할수없다. 중간·낮은각4쌍에서중복이없었다는것도각구간전체에중복이없다는통계적보증이아니다. 표본은검토편의를위한것이며누수율추정표본이아니다.

다음은확정그룹과의심제약을반영한초안갱신및연결주변후보자동정리다. 사람에게동일한쌍을반복질문하지않는다. 고위험관계가계속확인되는동안재학습을반복하지않고원인·범위를먼저좁힌다. 독립성·현장성능·보정·AUTO_PASS검증완료로표현하지않는다.

기존모델·분할·API·DB·원본을변경하지않았다. 최종시험1700장·예약이미지에는접근하지않았고학습도시작하지않았다.
''')
 dump(root/'outputs/door_triage_import/latest.json',dict(directory=str(out),report=str(out/'REPORT.md'),independenceEstablished=False));pointer.update(reviewed=True,importDirectory=str(out),decisionCounts=result['decisionCounts']);dump(page_pointer,pointer)
 print(json.dumps({k:v for k,v in result.items() if k!='sourceHashes'},ensure_ascii=False,indent=2));print('[24 REVIEW IMPORT]',out)
if __name__=='__main__':main()
