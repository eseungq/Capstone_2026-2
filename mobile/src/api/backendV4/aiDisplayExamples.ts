/** 시연용 예시만 포함하며, 실제 모델 응답이나 운영 데이터가 아닙니다. */
import type { InspectionDetailV4 } from './types';

const base: InspectionDetailV4 = {
  inspectionId: '8f3c1e2a-1234-4123-8123-111111111111',
  inspectionNo: 'INS-EXAMPLE-01',
  partCode: 'DOOR', lineCode: null, status: 'COMPLETED', displayState: 'REVIEW_PENDING',
  receivedAt: '2026-10-28T11:00:00+09:00', completedAt: '2026-10-28T11:00:01+09:00', retryOf: null,
  ai: {
    modelVersion: 'example-door-model-v1', calibratorVersion: null,
    predictedQuality: 'GOOD', rawDefectProbability: 0.23,
    calibratedDefectProbability: null, inferenceTimeMs: 412,
  },
  policy: {
    automationPolicyReady: false, policyVersion: null, passThreshold: null,
    recommendedAction: 'REVIEW', reviewReason: 'CALIBRATION_UNAVAILABLE',
  },
  judgement: { finalJudgement: null, judgedBy: null, confirmedBy: null, confirmedAt: null },
  images: {
    original: {url:'https://example.invalid/door.jpg', width:1280, height:720},
    gradcam: null, gradcamStatus:'NOT_REQUIRED',urlExpiresAt:'2030-10-28T11:10:00+09:00',
  },
  error: null,
};

export const aiDisplayExampleV4 = {
  goodReview: base,
  defectWithCam: {
    ...base, inspectionNo:'INS-EXAMPLE-02',
    ai:{...base.ai!, predictedQuality:'DEFECT' as const,rawDefectProbability:0.85},
    policy:{...base.policy!,reviewReason:'DEFECT_PREDICTED' as const},
    images:{...base.images!,gradcamStatus:'GENERATED' as const,gradcam:{url:'https://example.invalid/door-gradcam.png',width:1280,height:720}},
  },
  defectCamFailed: {
    ...base, inspectionNo:'INS-EXAMPLE-03',
    ai:{...base.ai!, predictedQuality:'DEFECT' as const,rawDefectProbability:0.85},
    policy:{...base.policy!,reviewReason:'DEFECT_PREDICTED' as const},
    images:{...base.images!,gradcamStatus:'FAILED' as const,gradcam:null},
  },
  defectConstantCamDemo: {
    ...base, inspectionNo:'INS-EXAMPLE-04',
    ai:{...base.ai!, predictedQuality:'DEFECT' as const,rawDefectProbability:0.85},
    policy:{...base.policy!,reviewReason:'DEFECT_PREDICTED' as const},
    images:{...base.images!,gradcamStatus:'NO_ACTIVATION' as const,gradcam:null},
  },
  goodReviewWithZeroCalibratedDemo: {
    ...base, inspectionNo:'INS-EXAMPLE-05',
    ai:{...base.ai!,calibratedDefectProbability:0,calibratorVersion:'example-calibrator-v1'},
  },
  goodReviewWorkerFail: {
    ...base, inspectionNo:'INS-EXAMPLE-06',displayState:'REVIEW_DONE' as const,
    judgement:{finalJudgement:'FAIL' as const,judgedBy:'WORKER' as const,confirmedBy:'example-worker',confirmedAt:'2026-10-28T11:00:10+09:00'},
  },
  failedAnalysis: {
    ...base, inspectionNo:'INS-EXAMPLE-07',status:'FAILED' as const,displayState:'FAILED' as const,
    ai:null, policy:null, images:{...base.images!,gradcamStatus:null,gradcam:null},
    error:{code:'AI_ERROR',message:'시연용 분석 실패',retryable:true},
  },
  pending: {
    ...base, inspectionNo:'INS-EXAMPLE-08',status:'ANALYZING' as const,displayState:'ANALYZING' as const,
    ai:null,policy:null,judgement:null,images:{...base.images!,gradcamStatus:null,gradcam:null},
  },
  anotherPartDemo: {...base,inspectionNo:'INS-EXAMPLE-09',partCode:'HOOD'},
  defectUnknownCam: {
    ...base, inspectionNo:'INS-EXAMPLE-10',
    ai:{...base.ai!,predictedQuality:'DEFECT' as const,rawDefectProbability:0.85},
    images:{...base.images!,gradcamStatus:null,gradcam:null},
  },
  invalidGoodCam: {
    ...base,inspectionNo:'INS-EXAMPLE-11',images:{...base.images!,gradcamStatus:'FAILED' as const,gradcam:null},
  },
} satisfies Record<string, InspectionDetailV4>;

export const camShowcaseCasesV4: Array<{
  label:string;detail:InspectionDetailV4;explanation:string;
}> = [
  {label:'GOOD + REVIEW + CAM 없음',detail:aiDisplayExampleV4.goodReview,explanation:'GOOD는 CAM을 만들지 않으며 REVIEW는 작업자 확인을 뜻합니다.'},
  {label:'DEFECT + CAM 성공',detail:aiDisplayExampleV4.defectWithCam,explanation:'원본과 겹친 참고용 이미지일 뿐 정확한 결함 마스크가 아닙니다.'},
  {label:'DEFECT + CAM 생성 실패',detail:aiDisplayExampleV4.defectCamFailed,explanation:'CAM이 실패해도 DEFECT 예측과 정책 REVIEW는 유지됩니다.'},
  {label:'DEFECT + NO_ACTIVATION (0/상수맵)',detail:aiDisplayExampleV4.defectConstantCamDemo,explanation:'백엔드 NO_ACTIVATION 응답 · CAM 이미지 null · 분류 성공 유지'},
  {label:'보정 확률 null',detail:aiDisplayExampleV4.goodReview,explanation:'보정 불량 확률은 0%가 아니라 미제공입니다.'},
  {label:'보정 확률 0% (가상 비교)',detail:aiDisplayExampleV4.goodReviewWithZeroCalibratedDemo,explanation:'가상 수치이며 실제 보정기/자동 통과 정책은 검증되지 않았습니다.'},
];
