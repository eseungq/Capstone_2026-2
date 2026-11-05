/**
 * 목표 미검출률 기반 자동 통과 후보 계산의 시연 전용 로직.
 * 주의: 모든 값과 라벨은 인위적으로 만든 가상 표본이며, 실제 모델 출력/실측 검증이 아닙니다.
 * 실제 정책/판정/DB/AsyncStorage에 영향을 주지 않습니다.
 *
 * 계산 규칙 (시연 한정):
 *  - score는 [0,1] 범위의 가상 불량 점수입니다 (보정된 확률이라는 근거는 없습니다).
 *  - score <= candidateThreshold인 항목을 가상 자동 통과 후보로 봅니다.
 *  - 미검출률 = (실제 불량인데 자동 통과 후보가 된 건수) / (실제 불량 전체 건수).
 *  - 튜닝용 가상 표본에서 목표 경험적 미검출률을 만족하면서
 *    자동 통과 비율이 최대가 되는 기준 후보를 선택합니다.
 *  - 별도 가상 평가 표본에서 자동 통과 비율/미검출률을 다시 계산합니다.
 *  - 이 예제는 통계적 신뢰 상한, 운영 배포 또는 정책 준비를 판단하지 않습니다.
 */

type ActualLabel = 'GOOD' | 'DEFECT';
export type SyntheticInspection = Readonly<{ score: number; actual: ActualLabel }>;

// 실제 데이터를 사용하지 않음: 시연을 위해 고정 생성한 서로 다른 두 가상 표본.
const tuningGood = [
  0.01, 0.015, 0.02, 0.025, 0.03, 0.035, 0.04, 0.045, 0.05, 0.055,
  0.06, 0.07, 0.075, 0.085, 0.09, 0.10, 0.11, 0.12, 0.14, 0.15,
  0.17, 0.18, 0.21, 0.23, 0.24, 0.28, 0.30, 0.35, 0.39, 0.45,
];
const tuningDefect = [0.065, 0.13, 0.19, 0.26, 0.34, 0.42, 0.50, 0.63, 0.77, 0.89];
const evaluationGood = [
  0.008, 0.018, 0.023, 0.031, 0.042, 0.048, 0.053, 0.059, 0.064, 0.071,
  0.079, 0.082, 0.096, 0.105, 0.118, 0.126, 0.145, 0.164, 0.176, 0.188,
  0.208, 0.225, 0.26, 0.275, 0.31, 0.33, 0.36, 0.40, 0.44, 0.53,
];
const evaluationDefect = [0.072, 0.105, 0.205, 0.29, 0.37, 0.47, 0.56, 0.66, 0.79, 0.94];

function makeRecords(good: number[], defect: number[]): SyntheticInspection[] {
  return [
    ...good.map((score) => ({ score, actual: 'GOOD' as const })),
    ...defect.map((score) => ({ score, actual: 'DEFECT' as const })),
  ];
}
const TUNING = makeRecords(tuningGood, tuningDefect);
const EVALUATION = makeRecords(evaluationGood, evaluationDefect);

export type PolicySimulationResult = Readonly<{
  targetPercent: number;
  candidateThreshold: number;
  tuningTotal: number;
  tuningDefects: number;
  tuningAutoPassed: number;
  tuningMissedDefects: number;
  tuningMissRatePercent: number;
  evaluationTotal: number;
  evaluationDefects: number;
  evaluationAutoPassed: number;
  evaluationMissedDefects: number;
  evaluationAutoPassRatePercent: number;
  evaluationMissRatePercent: number;
  evaluationMeetsTargetEmpirically: boolean;
}>;

export function parseTargetMissRate(input: string): number | null {
  const normalized = input.trim().replace(',', '.');
  if (!/^\d{1,3}(\.\d{1,2})?$/.test(normalized)) return null;
  const value = Number(normalized);
  return Number.isFinite(value) && value >= 0 && value <= 100 ? value : null;
}

function count(records: SyntheticInspection[], threshold: number) {
  const defects = records.filter((x) => x.actual === 'DEFECT').length;
  const passed = records.filter((x) => x.score <= threshold);
  const missed = passed.filter((x) => x.actual === 'DEFECT').length;
  return { total: records.length, defects, passed: passed.length, missed };
}

export function simulatePolicyForTarget(targetPercent: number): PolicySimulationResult {
  if (!Number.isFinite(targetPercent) || targetPercent < 0 || targetPercent > 100) {
    throw new Error('목표 미검출률은 0~100% 범위여야 합니다.');
  }
  const candidates = Array.from(new Set([0, ...TUNING.map((item) => item.score)])).sort((a, b) => a - b);
  // 값이 작을수록 보수적. 동일 표본에서 목표를 만족하는 최댓값을 선택합니다.
  let selected = 0;
  for (const threshold of candidates) {
    const summary = count(TUNING, threshold);
    if (summary.defects === 0) break; // 정의할 수 없으면 준비 불가
    if ((100 * summary.missed) / summary.defects <= targetPercent + 1e-9) {
      selected = threshold;
    }
  }
  const tuning = count(TUNING, selected);
  const evaluation = count(EVALUATION, selected);
  const evaluationMissRatePercent = evaluation.defects > 0
    ? (100 * evaluation.missed) / evaluation.defects : NaN;
  return {
    targetPercent,
    candidateThreshold: selected,
    tuningTotal: tuning.total,
    tuningDefects: tuning.defects,
    tuningAutoPassed: tuning.passed,
    tuningMissedDefects: tuning.missed,
    tuningMissRatePercent: (100 * tuning.missed) / tuning.defects,
    evaluationTotal: evaluation.total,
    evaluationDefects: evaluation.defects,
    evaluationAutoPassed: evaluation.passed,
    evaluationMissedDefects: evaluation.missed,
    evaluationAutoPassRatePercent: (100 * evaluation.passed) / evaluation.total,
    evaluationMissRatePercent,
    evaluationMeetsTargetEmpirically: Number.isFinite(evaluationMissRatePercent)
      && evaluationMissRatePercent <= targetPercent + 1e-9,
  };
}
