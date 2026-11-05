/**
 * 합의 v4: 관리자는 AI가 검증한 허용 범위 안에서 passThreshold를 조정합니다.
 * threshold 저장은 새 버전 생성, 활성화는 별도 관리자 API 호출입니다.
 * 이 파일은 순수한 입력 검증 함수만 포함하며 어떠한 API도 호출하지 않습니다.
 * 실제 허용 범위가 없거나 검증되지 않았다면 저장/적용 금지.
 */
export interface ThresholdBoundsV4 {
  validatedMin: number | null;
  validatedMax: number | null;
  evidenceVerified: boolean;
}

export type ThresholdCheckV4 =
  | { ok: true; value: number }
  | { ok: false; reason: 'UNVERIFIED' | 'BAD_RANGE' | 'INVALID_VALUE' | 'OUT_OF_RANGE' };

export function validateThresholdEditV4(input: string, bounds: ThresholdBoundsV4): ThresholdCheckV4 {
  if (!bounds.evidenceVerified || bounds.validatedMin === null || bounds.validatedMax === null) {
    return { ok: false, reason: 'UNVERIFIED' };
  }
  const { validatedMin: min, validatedMax: max } = bounds;
  if (!Number.isFinite(min) || !Number.isFinite(max) || min < 0 || max > 1 || min > max) {
    return { ok: false, reason: 'BAD_RANGE' };
  }
  const text = input.trim();
  // e/E 지수 표기는 UI에서 허용하지 않습니다. 정밀도는 최종 서버가 검증합니다.
  if (!/^(?:0(?:\.\d+)?|1(?:\.0+)?)$/.test(text)) {
    return { ok: false, reason: 'INVALID_VALUE' };
  }
  const value = Number(text);
  if (!Number.isFinite(value)) return { ok: false, reason: 'INVALID_VALUE' };
  if (value < min || value > max) return { ok: false, reason: 'OUT_OF_RANGE' };
  return { ok: true, value };
}
