import type { Inspection } from './mockInspections';

/**
 * 시연용 검사 기록 집계. 결과는 AI 정확도가 아닙니다.
 * - AUTO_PASS_EXAMPLE은 미검증 정책의 별도 화면 예시이므로 집계 대상에서 제외합니다.
 * - 재검사 신규 ID는 별도의 접수 건으로 계산하며, 동일 부품의 중복 촬영 수를 제거하지 않습니다.
 * - REVIEW_DONE 여부는 status가 아니라 finalJudgement 필드의 확정 여부로 판별합니다.
 * - 운영용 실제 AUTO_PASS가 도입되기 전에는 자동 통과 확정 건수를 0건으로 둡니다.
 */
export type QualityStatistics = {
  receivedTotal: number;
  finalizedPass: number;
  finalizedFail: number;
  finalizedTotal: number;
  waitingForReview: number;
  analysisFailed: number;
  analyzing: number;
  receivedPending: number;
  excludedAutoPassExamples: number;
  retryInspections: number;
  defectRatePercent: number | null;
};

type StatItem = Pick<Inspection, 'id' | 'status' | 'finalJudgement' | 'retryOf'>;

export function calculateQualityStatistics(items: readonly StatItem[]): QualityStatistics {
  const unique = Array.from(new Map(items.map((item) => [item.id, item])).values());
  const excludedAutoPassExamples = unique.filter(item => item.status === 'AUTO_PASS_EXAMPLE').length;
  const eligible = unique.filter(item => item.status !== 'AUTO_PASS_EXAMPLE');

  const finalized = eligible.filter(
    item => item.status === 'REVIEW' && (item.finalJudgement === 'PASS' || item.finalJudgement === 'FAIL')
  );
  const finalizedPass = finalized.filter(item => item.finalJudgement === 'PASS').length;
  const finalizedFail = finalized.filter(item => item.finalJudgement === 'FAIL').length;
  const finalizedTotal = finalizedPass + finalizedFail;

  return {
    receivedTotal: eligible.length,
    finalizedPass,
    finalizedFail,
    finalizedTotal,
    waitingForReview: eligible.filter(item => item.status === 'REVIEW' && item.finalJudgement === null).length,
    analysisFailed: eligible.filter(item => item.status === 'FAILED').length,
    analyzing: eligible.filter(item => item.status === 'ANALYZING').length,
    receivedPending: eligible.filter(item => item.status === 'RECEIVED').length,
    excludedAutoPassExamples,
    retryInspections: eligible.filter(item => item.retryOf !== null).length,
    defectRatePercent: finalizedTotal === 0 ? null : (finalizedFail / finalizedTotal) * 100,
  };
}
