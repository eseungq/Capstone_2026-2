"""Record evidence-based candidates; does not activate models or change inference."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
from frame_model.check import ROOT
from frame_model.train import dump


def main():
    suite=ROOT/'outputs/frame_training/comparison_train_20261022T160533_169658Z'
    human=Path(json.loads((ROOT/'frame_model/latest_cam_summary.json').read_text())['directory'])
    comparison=json.loads((suite/'comparison.json').read_text());reviews=json.loads((human/'summary.json').read_text())
    camdir=ROOT/'outputs/frame_cam_review'/reviews['review_id'];selection=json.loads((camdir/'selection.json').read_text());cam=json.loads((camdir/'cam_report.json').read_text())
    hypotheses={
      '실링 불량':{'model_decision':'specialist_primary_candidate','specialist_id':'type_01','layer_decision':'keep_both_candidates','priority_layer':None,'note':'개별 모델 미검출/오탐 모두 감소. 서비스 DEFECT 표본3건은 유용2/제한1이지만 통합과 같은 DEFECT 사진은1건뿐. 개별03·04는 두 레이어 긍정,06은layers.2 긍정/layers.3 반응 없음; 단일 레이어 확정 불가. 04는 실제 GOOD의 오탐이므로 CAM이 그럴듯해도 정답 개선 아님.','supporting_ids':['03','04','06'],'unresolved_ids':['01','02']},
      '헤밍 불량':{'model_decision':'specialist_primary_candidate','specialist_id':'type_03','layer_decision':'layer2_followup_candidate','priority_layer':'layers.2.blocks.5.norm1','note':'개별 모델 미검출/오탐 모두 감소. 15·18 메모는layers.2 관련성, layers.3 배경 반응을 기록. 서비스 DEFECT 표본3건 모두 배경 반응 선택이 있어 설명 검증 미완료.16은 실제 GOOD 오탐.13·14는두 모델 미검출,13의layers.2/17의layers.3 0맵은GOOD 진단 계산으로 서비스 생성 오류가 아님.','supporting_ids':['15','18'],'unresolved_ids':['13','14','16']},
      '외관 손상':{'model_decision':'retain_unified_and_specialist','specialist_id':'type_02','layer_decision':'keep_both_candidates','priority_layer':None,'note':'개별 모델 F1/오탐 개선이나 미검출1건 증가.09는개별layers.2 긍정/layers.3 부정,12는개별둘다긍정,10은개별layers.3 긍정/layers.2 부정(단GOOD 진단). 단일 레이어·운영 모델을 확정할 근거 부족.','supporting_ids':['09','12'],'unresolved_ids':['07','08','10']},
      '홀 변형':{'model_decision':'retain_unified_and_specialist','specialist_id':'type_04','layer_decision':'insufficient_evidence','priority_layer':None,'note':'개별 모델 F1/오탐 개선이나 미검출1건 증가.20은원본 결함 판단 불가 기록.24 개별layers.2 반응과 배경 반응이 함께 기록.19~23은라벨/가시성/GOOD 진단을 구분해야 함.','supporting_ids':['24'],'unresolved_ids':['19','20','21','22','23']}}
    candidates={}
    for kind,decision in hypotheses.items():
        results=comparison['by_type'][kind];model=selection['checkpoints'][decision['specialist_id']]
        candidates[kind]={**decision,'classification':results,'specialist_checkpoint':{'path':model['path'],'sha256':model['sha256'],'epoch':model['expected_best_epoch']},'service_DEFECT_review':{role:reviews['groups'][kind][role]['service_DEFECT_candidate'] for role in ['unified','specialist']},'same_image_both_DEFECT':[x for x in reviews['both_predicted_DEFECT'] if x['type']==kind],'activated':False,'operational_ready':False,'calibratorVersion':None,'passThreshold':None}
    out=ROOT/'outputs/frame_candidate_assessment'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ');out.mkdir(parents=True)
    sources=[suite/'comparison.json',human/'summary.json',human/'human_review_original.json',camdir/'selection.json',camdir/'cam_report.json',Path(__file__)]
    record={'status':'offline_candidate_assessment_only','candidates':candidates,'source_sha256':{str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},'layers_confirmed_for_production':False,'human_notes_are_not_per_layer_numeric_scores':True,'training_or_threshold_change':False,'limitations':['24 selected error/control photos; not a population CAM pass rate.','Only four paired photos have both models predicting DEFECT (one per type).','F1-selected internal validation and one seed; not independent final or factory-line performance.','No relative cost of misses and false alarms agreed; no numeric operational acceptance threshold.','Single-vs-batch score warnings remain; no tolerance relaxation.','API subtype routing/registration, calibration, policy and integration not complete.']}
    dump(out/'candidates.json',record)
    text='''# 프레임 모델·레이어 후보 정리

이 문서는 **오프라인 후속 검증 후보**입니다. 운영 모델/레이어 등록이나 교체가 아닙니다. 기존 가중치·전처리·분할·서비스·DB는 그대로입니다.

| 유형 | 모델 후보 방향 | CAM 레이어 방향 |
|---|---|---|
| 실링 | 개별 모델 우선 후보 | 두 후보 유지, 단일 레이어 미확정 |
| 헤밍 | 개별 모델 우선 후보 | layers.2.blocks.5.norm1 우선 확인 후보 |
| 외관 | 통합·개별 모두 유지 | 두 후보 유지 |
| 홀 | 통합·개별 모두 유지 | 근거 부족, 미확정 |

## 분류 근거

| 유형 | 통합→개별 미검출 | 통합→개별 오탐 | 개별 F1 |
|---|---:|---:|---:|
| 실링 | 33→9 | 32→8 | 98.31% |
| 헤밍 | 31→2 | 4→2 | 99.69% |
| 외관 | 23→24 | 28→12 | 96.47% |
| 홀 | 9→10 | 58→30 | 96.13% |

동일 모델 선택용 검증에서의 최고 F1 checkpoint 비교입니다. 외관·홀에서 오탐 감소와 미검출 증가의 우선순위를 정할 근거가 없어 자동 우승 모델을 만들지 않았습니다. 실링/헤밍의 분류 개선도 한 seed 내부 검증 결과이지 독립 최종 성능이 아닙니다.

## CAM 근거와 해석

모델마다6장×2후보 레이어를 보았지만 평가 입력은 모델당1개였습니다. 레이어별 점수/우승률을 역으로 만들지 않았습니다. 원문 메모를 근거로 방향만 제안합니다.

두 모델이 모두 DEFECT인 같은 사진은 총4장, 유형별1장(06·12·18·24)뿐입니다. 서비스DEFECT인 사진을 모델별로 단순 집계하면 서로 다른 사진을 비교하게 되므로 유용성 비율로 우열을 확정하지 않습니다. GOOD에 강제 생성한 CAM은 진단 자료입니다. 정확한 결함 좌표/면적 정답이나 자동 FAIL 근거로 쓰지 않습니다.

'''
    for kind,c in candidates.items():text+='### '+kind+'\n\n'+c['note']+'\n\n'
    text+='''## 남은 항목과 다음 순서

1. 분류 후보는 실링/헤밍 개별을 우선 보존하고 외관/홀 통합·개별을 모두 보존. 운영 등록은 보류.
2. 미검출과 FP를 분리해 확인. 특히 실제GOOD 오탐의 CAM이 그럴듯하다는 이유로 양성 근거를 확정하지 않음. 홀20은원본 라벨·검사 대상 의미를 확인할 후보이며 임의 정답 변경 없음.
3. 레이어 확정 전에는 레이어마다 독립된 평가가 필요. 기존24장 메모를 보존하고 다음 추가 표본이 필요할 때 모델/레이어마다 분리 기록. 지금24장을 처음부터 반복 검토할 필요는 없음.
4. 추가 확인 표본은 기존24장을 제외한 내부 검증에서 예측DEFECT 사례를 TP/FP로 구분해 선정할 수 있음. 두 모델 모두DEFECT인 같은 사진을 우선하되, 모델마다 다른 예측 사례를 숨기지 않음. 메모로 고른 층을 다시 같은 사진에서 합격시켜 일반화하지 않음.
5. 단일/배치 점수 차이는별도 수치 재현성 과제로 유지. 현재48건의 클래스는일치했으나 전체 검증에서 경계값 변경 없음이 증명된 것은 아님.
6. 데이터 사용 계획을 확정한 뒤 독립 최종 시험, 보정/정책 검증, 검사 유형별 API 라우팅·백엔드·모바일 통합 진행. 원본Validation을 중복 확인 없이 독립 시험으로 단정하지 않음.

이번에는 추가 학습·GPU 실행·자동 통과 기준·API 필드·실험 분할을 변경하지 않았습니다. 사진/모델 추가 검토는 자동 시작하지 않습니다. 설정·모델 해시는 candidates.json에 보존했습니다.
'''
    (out/'ASSESSMENT.md').write_text(text)
    dump(ROOT/'frame_model/latest_candidate_assessment.json',{'directory':str(out),'report':str(out/'ASSESSMENT.md')})
    print('[CANDIDATE ASSESSMENT]',out/'ASSESSMENT.md')

if __name__=='__main__':main()
