"""Validate exported DOOR review; preserve suspected part links separately from confirmed duplicates."""
import argparse
import hashlib
import json
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from ai_api.duplicate_groups import ROOT, components


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def dump(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')


def validate(review, queue, queue_sha):
    if review.get('schema')!='door-remaining-candidate-review-v1':raise ValueError('Unknown schema')
    if review.get('sourceQueueSHA256')!=queue_sha:raise ValueError('Queue hash mismatch')
    if review.get('applied') is not False or review.get('originalsModified') is not False:raise ValueError('Expected unapplied review')
    if not isinstance(review.get('reviewer'),str) or not review['reviewer'].strip():raise ValueError('Missing reviewer')
    datetime.fromisoformat(review['reviewedAt'].replace('Z','+00:00'))
    records=review.get('records',[]);expected={r['caseId']:r for r in queue}
    if len(records)!=len(queue) or len({r['caseId'] for r in records})!=len(queue):raise ValueError('Duplicate or missing cases')
    allowed={'UNREVIEWED','SAME_PHOTO','POSSIBLY_SAME_PART','DIFFERENT','UNSURE'}
    for r in records:
        original=expected.get(r['caseId'])
        if original is None or {k:v for k,v in r.items() if k not in ('decision','reason')}!=original:raise ValueError('Source pair metadata changed')
        if r.get('decision') not in allowed or not isinstance(r.get('reason'),str):raise ValueError('Invalid decision/reason')
    return records


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--review',type=Path,required=True);p.add_argument('--source-dir',type=Path,required=True);p.add_argument('--no-update-latest',action='store_true',help='Keep the earlier review pointer; caller registers this batch in a versioned history');a=p.parse_args()
    source=a.source_dir.resolve();queue_file=source/'review_queue.json';review=load(a.review);queue=load(queue_file)
    records=validate(review,queue,sha(queue_file));summary=load(source/'summary.json')
    for path,expected in summary['sourceHashes'].items():
        if sha(path)!=expected:raise ValueError('Underlying evidence changed: '+path)
    out=ROOT/'outputs/door_remaining_review_import'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    shutil.copyfile(a.review,out/'original_user_export.json')
    confirmed=[r for r in records if r['decision']=='SAME_PHOTO'];suspected=[r for r in records if r['decision']=='POSSIBLY_SAME_PART'];different=[r for r in records if r['decision']=='DIFFERENT']
    # Compatible evidence for duplicate_groups; no suspected-part edge is admitted here.
    supplemental=dict(source=str(queue_file),sourceSHA256=sha(queue_file),reviewer=review['reviewer'],reviewedAt=review['reviewedAt'],applied=False,records=[dict(train_image=r['train_image'],validation_image=r['validation_image'],judgment='user_confirmed_same_photo',displayNumber=int(r['caseId'].split('_')[-1]),reason=r['reason']) for r in confirmed])
    dump(out/'confirmed_same_photo_supplemental.json',supplemental)
    group_ids={r[k] for r in suspected for k in ('validationGroup','trainGroup')}
    suspect_components=components(group_ids,[(r['validationGroup'],r['trainGroup']) for r in suspected])
    policy=dict(status='proposed_conservative_constraints_not_applied',meaning='Suspected physical-part groups must be held from freeze or kept in one future role until resolved; these are not confirmed photo duplicates',components=[dict(constraintId='suspected_part_'+hashlib.sha256('\n'.join(c).encode()).hexdigest(),existingDuplicateGroupIds=c,action='hold_from_split_freeze_or_keep_one_future_role') for c in suspect_components],sourceReviewSHA256=sha(a.review),splitApplied=False)
    dump(out/'suspected_part_constraints.json',policy)
    dump(out/'decisions.json',dict(reviewer=review['reviewer'],reviewedAt=review['reviewedAt'],records=records,applied=False))
    missing=[r['caseId'] for r in records if r['decision']!='UNREVIEWED' and not r['reason'].strip()]
    group_source=next(Path(path) for path in summary['sourceHashes'] if path.endswith('/groups.json'))
    known_cross=sum(len(g['originalSplits'])>1 for g in load(group_source))
    result=dict(status='structurally_valid_missing_rationale' if missing else 'validated_proposals',sourceReview=str(a.review.resolve()),sourceReviewSHA256=sha(a.review),queueSource=str(queue_file),queueSHA256=sha(queue_file),recordCount=len(records),decisionCounts=dict(Counter(r['decision'] for r in records)),missingRationaleCases=missing,newConfirmedSamePhotoLinks=len(confirmed),suspectedPartRelations=len(suspected),suspectedPartExistingGroups=len(group_ids),suspectedPartConstraintComponents=len(suspect_components),suspectedRelationsCrossingProposedRoles=sum(r.get('crossesProposedRoles',len(set(r.get('proposalRoles',[])))>1) for r in suspected),previousConfirmedCrossSplitGroupsUnchanged=known_cross,readyForTraining=False,originalsModified=False,splitApplied=False,finalTestRead=False)
    dump(out/'summary.json',result)
    report=f'''# DOOR 유사 후보 검토 가져오기\n\n검토자: {review['reviewer']} / 작성 시각: {review['reviewedAt']}\n\n{len(records)}개 사례의 원래 경로·그룹·순위 정보와 대기열 SHA256을 대조했다. 누락·중복·원본 메타데이터 변경 없음. 원본 내보내기를 그대로 보존했다.\n\n- 같은 사진: {len(confirmed)}쌍\n- 다른 사진·동일 실물 근거 없음: {len(different)}쌍\n- 같은 실물·다른 촬영 의심: {len(suspected)}쌍\n- 판단 근거 미입력: {len(missing)}건\n\n## 해석과 처리\n\n다른 사진 판단 사례는 선택값 그대로 기록했다. 이는 해당 쌍에 대한 사람 판단이며 다른 모든 사진과의 실물 독립성을 보장하지 않는다.\n\n같은 실물 의심 사례는 선택값 그대로 기록했다. 확인된 같은 사진 그룹으로 합치지 않았다. 기존 {len(group_ids)}개 중복 그룹에 걸친 의심 관계를 {len(suspect_components)}개의 별도 보수적 제약 묶음으로 정리했다. 의심 관계 중 {result['suspectedRelationsCrossingProposedRoles']}쌍은 기존 미래 역할 후보를 넘는다. 차기 분할 확정 전 보류하거나 동일 역할에 두는 제안이며 실제 분할에는 적용하지 않았다.\n\n새로 확정된 같은 사진 연결이 없어 기존 분할 교차 중복 {known_cross}그룹과 이전 저장 예측 집계는 변경하지 않았다. 이번 결과만으로 모델 성능의 독립성이 해결됐다고 표시하지 않는다.\n\n## 부족한 근거\n\n판단 근거 미입력 {len(missing)}건은 {", ".join(missing) if missing else "없음"}이다. 선택값과 설명은 보존하되 상세 판단 근거까지 모두 완료됐다고 표시하지 않는다. 같은 실물 의심 사례의 공통 근거가 같은 흠집·부품 경계인지, 배경·구도 유사성뿐인지 구분해야 한다. 배경·색상·차종만 같다는 이유로 같은 실물이라고 확정할 수 없다. 별도 재검토 화면을 반복 생성하지 않고 이 설명을 먼저 보완한다.\n\n기존 라벨 충돌 검토의 DEFECT 후보 7그룹·촬영 부적합 보류 3그룹은 유지한다. 원본 라벨·분할·best.pt·평가 기록·DB 변경 없음. 새 학습·보정·정책 변경 없음.\n'''
    (out/'REPORT.md').write_text(report)
    if not a.no_update_latest:dump(ROOT/'outputs/door_remaining_review_import/latest.json',dict(output=str(out),report=str(out/'REPORT.md')))
    print(json.dumps(dict(output=str(out),**result),ensure_ascii=False,indent=2))

if __name__=='__main__':main()
