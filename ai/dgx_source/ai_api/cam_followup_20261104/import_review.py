"""Preserve human feedback and summarize CAM usefulness without editing model or labels."""
import argparse, ast, collections, csv, hashlib, json, shutil
from pathlib import Path

ROOT=Path('/path/to/private/validated-project')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def table(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:return list(csv.DictReader(stream))

def main():
    p=argparse.ArgumentParser();p.add_argument('--review',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    review=json.loads(a.review.read_text(encoding='utf-8-sig'))
    pointer=ROOT/'ai_api/cam_followup_20261104/latest.json'
    source=Path(json.loads(pointer.read_text())['output']);selection=json.loads((source/'selection.json').read_text())
    assert review['schema']=='cam-followup-human-review-v1'
    assert review['selectionSHA256']==sha(source/'selection.json') and review['modelVersion']==selection['modelVersion']
    samples={row['id']:row for row in selection['samples']}
    records={row['id']:row for row in review['cases']}
    assert len(records)==len(review['cases'])==len(samples)==18 and set(samples)==set(records)
    assert all(row.get('visibility') and row.get('current') and row.get('candidate') for row in records.values())
    positives=[row for sid,row in records.items() if samples[sid]['savedKind']=='TP']
    visible=[row for row in positives if row['visibility']=='224에서도 확인 가능']
    normal=[row for sid,row in records.items() if samples[sid]['savedKind']=='TN']
    ambiguous=[row['id'] for row in positives if row['visibility']=='결함 여부 애매']
    normal_conflict=[row['id'] for row in positives if row['visibility']=='정상 대조']
    oldrun=ROOT/'outputs/training/door_swin_tiny_20261008_183758_369671'
    oldcfg=json.loads((oldrun/'run_config.json').read_text())
    old_roles={}
    for role in ('train','internal_validation'):
        info=oldcfg['manifests'][role];path=Path(info['path']);assert sha(path)==info['sha256']
        for row in table(path):
            assert row['image_path'] not in old_roles
            old_roles[row['image_path']]=role
    history=[dict(id=sid,oldRole=old_roles.get(row['image_path'],'unknown')) for sid,row in samples.items()]
    visible_ids={r['id'] for r in visible}
    comparison_ids=[r['id'] for r in history if r['id'] in visible_ids and r['oldRole']=='internal_validation']
    count=lambda rows,field:dict(collections.Counter(row[field] for row in rows))
    summary=dict(schema='human-cam-followup-summary-v1',reviewSHA256=sha(a.review),selectionSHA256=review['selectionSHA256'],modelVersion=review['modelVersion'],records=18,sourcePositiveCases=12,visible224PositiveCases=len(visible),visible224Current=count(visible,'current'),visible224Candidate=count(visible,'candidate'),allSourcePositiveCurrent=count(positives,'current'),allSourcePositiveCandidate=count(positives,'candidate'),normalControlCases=len(normal),normalCurrent=count(normal,'current'),normalCandidate=count(normal,'candidate'),ambiguousPositiveLabelCases=ambiguous,normalLookingPositiveLabelCases=normal_conflict,oldModelRoleCounts=dict(collections.Counter(r['oldRole'] for r in history)),commonValidationVisibleIDs=comparison_ids,actualOldModelCAMComparisonPerformed=False,automaticLabelChanges=False,modelOrLayerChanges=False,positionAccuracyMeasured=False)
    a.output.mkdir(parents=True,exist_ok=True)
    raw=a.output/'raw_review.json'
    if raw.exists():assert sha(raw)==sha(a.review)
    else:shutil.copyfile(a.review,raw)
    (a.output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    plan=dict(status='prepared_not_executed',purpose='Diagnose old20 vs retrained2 CAM on already-reviewed visible defects held out in both original image-level validation lists; not independent performance selection',oldModel=dict(run=str(oldrun),epoch=20,checkpointSHA256='8d042c7bfab20ba2527ef3693aed08e0df7e1b1ce58acc45b44de7ae5d0d6ab7'),newModel=dict(modelVersion=selection['modelVersion'],checkpointSHA256=selection['checkpointSHA256']),layer='layers.3.blocks.1.norm1',target='DEFECT logit',requiredControls=['same CPU environment, FP32 and preprocessing','same colormap and per-map normalization','same display orientation and image size','do not mix old-model CAM with new-model predictions','do not read final-test images'],cases=[samples[sid] for sid in comparison_ids],limitations='Only three focused diagnostic cases. Other reviewed photos may have been training images for the old model; image-level holdout does not certify group/physical-part independence.')
    (a.output/'old_new_comparison_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2)+'\n')
    lines=['# 추가 18장 사용자 기록 집계','',
        '현재 7×7 CAM의 참고 유용성이 낮다는 우려를 사용자 기록이 뒷받침합니다. 후보 14×14는 일부 상대적 개선이 있지만, 정확한 결함 위치 표시로 채택할 근거가 충분하지 않습니다.','',
        '| 224 입력에서 결함을 확인한 8건 | O | X | 판단 어려움 |','|---|---:|---:|---:|',
        f"| 현재 7×7 | {summary['visible224Current'].get('O',0)} | {summary['visible224Current'].get('X',0)} | {summary['visible224Current'].get('판단 어려움',0)} |",
        f"| 후보 14×14 | {summary['visible224Candidate'].get('O',0)} | {summary['visible224Candidate'].get('X',0)} | {summary['visible224Candidate'].get('판단 어려움',0)} |",'',
        '후보 O 4건 중 일부에도 부분적인 흠집 누락·배경 동시 강조가 기록돼 있습니다. O를 정확한 결함 경계나 전체 위치 정확도로 해석하지 않습니다.','',
        '정상 대조 6건: 현재는 정상 부위 강조 많음 4·판단 어려움 2, 후보는 강조 적음 5·많음 1입니다. 불량 8건의 O/X 집계와 합산하지 않습니다.','',
        '불량 원천 라벨 중 결함 여부 애매: '+', '.join(ambiguous)+'. 정상 대조로 기록된 불량 원천 라벨: '+', '.join(normal_conflict)+'. 사용자 판단 또는 버튼 선택의 재확인 대상으로 보존하며 원본 라벨과 기존 지표는 수정하지 않습니다.','',
        '## 이전 모델과 비교할 때의 조건','',
        '이번 비교 화면의 현재·후보는 같은 재학습 2회차 모델의 서로 다른 레이어입니다. 이전 20회차 모델과의 직접 비교 결과가 아닙니다.','',
        '이전 모델의 원래 train/internal_validation CSV 해시를 확인해 실제 사용 사진을 대조했습니다. 역할 분포: '+json.dumps(summary['oldModelRoleCounts'],ensure_ascii=False)+'. 이전 단계의 previous_run_role 필드를 최초 20회차 모델의 사용 이력으로 간주하지 않았습니다.','',
        '두 모델 모두의 이미지 단위 검증 목록에 포함되고, 이번에 224에서 결함이 보인다고 확인한 공통 표본: '+', '.join(comparison_ids)+'. 먼저 이 사진들로 동일 환경·레이어·표시 조건의 CAM을 비교하는 계획을 별도 JSON으로 준비했습니다. 아직 새 추론은 실행하지 않았습니다.','',
        '이 비교로 재학습 모델을 자동 교체하거나 이전 모델의 독립 일반화 성능을 주장하지 않습니다. 3장은 제한적인 원인 진단이고, 기존 분할의 중복·실물 독립성 한계도 남습니다.','',
        '## 해석과 후속 작업','',
        '분류 학습의 목표는 정상·불량이며, 이번 모델은 결함 위치 마스크를 맞추도록 학습하지 않았습니다. 분류 지표와 CAM 참고 유용성을 별도로 평가해야 합니다. 단순히 에폭을 늘리면 위치 설명이 좋아진다고 보장하지 않습니다.','',
        '1. 기존 20회차와 재학습 2회차를 위 공통 3장으로 직접 비교합니다. 전처리와 라이브러리 환경은 동일함을 확인했고, 레이어와 색상 표현도 맞춥니다.',
        '2. 이전 모델도 부적절하면 레이어 교체만으로 해결하려 하지 않고, CAM을 참고자료로 제한하는 범위와 위치 지도학습이 필요한 기능을 구분합니다.',
        '3. 원천 라벨과 육안 판단이 다른 4건은 추가 확인 대상으로 남깁니다. 자동으로 학습 데이터를 삭제하거나 재라벨링하지 않습니다.','',
        '## 사용자 원문 기록','', '| ID | 가시성 | 현재 | 후보 | 메모 |','|---|---|---|---|---|']
    for sid,row in records.items():
        values=[sid,row['visibility'],row['current'],row['candidate'],row.get('note','')]
        lines.append('| '+' | '.join(str(v).replace('|','/').replace('\n',' ') for v in values)+' |')
    (a.output/'REPORT_KO.md').write_text('\n'.join(lines)+'\n')
    (ROOT/'ai_api/cam_followup_20261104/latest_review.json').write_text(json.dumps(dict(directory=str(a.output),reviewSHA256=summary['reviewSHA256']),indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':main()
