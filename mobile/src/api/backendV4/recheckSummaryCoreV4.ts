/**
 * AUTO_PASS 표본 재확인 요약 조회 계약 6.11 (백엔드 PR #42).
 * rules[] 한 항목은 규칙+부품+정책+모델+보정기 조합 하나 — 항목을 합산하여 불량률을 만들지 않습니다.
 * 부분 완료와 계산 불가능 상태는 서버의 partial/null 값을 그대로 표시합니다.
 */
export type RecheckSummaryStratumV4 = 'NEAR' | 'MID' | 'LOW';
export interface RecheckStratumSummaryV4 {
  stratum: RecheckSummaryStratumV4;
  autoPassCount: number;
  decidedCount: number;
  undecidedCount: number;
  sampledCount: number;
  completedCount: number;
  pendingCount: number;
  completionRate: number | null;
  passCount: number;
  failCount: number;
  failRateAmongCompleted: number | null;
}
export interface RecheckSummaryCompareV4 {
  nearRate: number;
  midRate: number;
  lowRate: number;
  computable: boolean;
  sampledCount: number | null;
  unverifiedCount: number | null;
  passCount: number | null;
  failCount: number | null;
  partial: boolean | null;
  estimatedDefectRateInAutoPass: number | null;
}
export interface RecheckRuleSummaryV4 {
  ruleVersion: string;
  trialName: string | null;
  partCode: string | null;
  policyVersion: string | null;
  modelVersion: string | null;
  calibratorVersion: string | null;
  nearRatio: number | null;
  midRatio: number | null;
  nearRate: number | null;
  midRate: number | null;
  lowRate: number | null;
  autoPassCount: number;
  decidedCount: number;
  undecidedCount: number;
  sampledCount: number;
  pendingCount: number;
  passCount: number;
  failCount: number;
  completionRate: number | null;
  partial: boolean;
  strata: RecheckStratumSummaryV4[];
  estimatedDefectRateInAutoPass: number | null;
  compare: RecheckSummaryCompareV4 | null;
}
export interface RecheckSummaryWaitV4 {
  count: number;
  pendingCount: number;
  averageMs: number | null;
  medianMs: number | null;
}
export interface RecheckSummaryDwellV4 {
  count: number;
  averageMs: number | null;
  medianMs: number | null;
  averageOpenCount: number | null;
}
export interface RecheckSummaryV4 {
  partCode: string | null;
  from: string | null;
  to: string | null;
  autoPassCount: number;
  decidedCount: number;
  undecidedCount: number;
  undecidedWithoutRuleCount: number;
  rules: RecheckRuleSummaryV4[];
  waits: { review: RecheckSummaryWaitV4; recheck: RecheckSummaryWaitV4 };
  dwell: { review: RecheckSummaryDwellV4; recheck: RecheckSummaryDwellV4 };
}
export interface RecheckSummaryQueryV4 {
  partCode?: string;
  from?: string;
  to?: string;
  compareNearRate?: number;
  compareMidRate?: number;
  compareLowRate?: number;
}
const record = (x: unknown): x is Record<string, unknown> =>
  x !== null && typeof x === 'object' && !Array.isArray(x);
const count = (x: unknown): x is number => Number.isSafeInteger(x) && (x as number) >= 0;
const millis = (x: unknown): x is number | null => x === null || count(x);
const rate = (x: unknown): x is number => typeof x === 'number' &&
  Number.isFinite(x) && x >= 0 && x <= 1;
const optionalRate = (x: unknown): x is number | null => x === null || rate(x);
const optText = (x: unknown): x is string | null => x === null || typeof x === 'string';
const iso = (x: unknown): x is string => typeof x === 'string' &&
  /(Z|[+-]\d{2}:\d{2})$/.test(x) && Number.isFinite(Date.parse(x));
const optIso = (x: unknown): x is string | null => x === null || iso(x);

function failure(where: string): never { throw new Error('재확인 요약 응답 형식 오류: ' + where); }
function parseWait(x: unknown, where: string): RecheckSummaryWaitV4 {
  if (!record(x) || !count(x.count) || !count(x.pendingCount) ||
    !millis(x.averageMs) || !millis(x.medianMs)) failure(where);
  return x as unknown as RecheckSummaryWaitV4;
}
function parseDwell(x: unknown, where: string): RecheckSummaryDwellV4 {
  if (!record(x) || !count(x.count) ||
    !millis(x.averageMs) || !millis(x.medianMs) ||
    !(x.averageOpenCount === null || (typeof x.averageOpenCount === 'number' &&
      Number.isFinite(x.averageOpenCount) && x.averageOpenCount >= 1))) failure(where);
  return x as unknown as RecheckSummaryDwellV4;
}
function parseStratum(x: unknown): RecheckStratumSummaryV4 {
  if (!record(x) || !['NEAR', 'MID', 'LOW'].includes(String(x.stratum)) ||
      !count(x.autoPassCount) || !count(x.decidedCount) || !count(x.undecidedCount) ||
      !count(x.sampledCount) || !count(x.completedCount) || !count(x.pendingCount) ||
      !count(x.passCount) || !count(x.failCount) ||
      !optionalRate(x.completionRate) || !optionalRate(x.failRateAmongCompleted)) failure('strata[]');
  if (x.completedCount !== (x.passCount as number) + (x.failCount as number) ||
      x.sampledCount !== (x.completedCount as number) + (x.pendingCount as number) ||
      x.autoPassCount !== (x.decidedCount as number) + (x.undecidedCount as number) ||
      ((x.sampledCount as number) === 0) !== (x.completionRate === null)) failure('구간 완료 건수 불일치');
  return x as unknown as RecheckStratumSummaryV4;
}
function parseCompare(x: unknown): RecheckSummaryCompareV4 | null {
  if (x === null) return null;
  if (!record(x) || !rate(x.nearRate) || !rate(x.midRate) || !rate(x.lowRate) ||
      typeof x.computable !== 'boolean' ||
      !(x.sampledCount === null || count(x.sampledCount)) ||
      !(x.unverifiedCount === null || count(x.unverifiedCount)) ||
      !(x.passCount === null || count(x.passCount)) ||
      !(x.failCount === null || count(x.failCount)) ||
      !(x.partial === null || typeof x.partial === 'boolean') ||
      !optionalRate(x.estimatedDefectRateInAutoPass)) failure('compare');
  if (!x.computable && (x.sampledCount !== null || x.unverifiedCount !== null ||
        x.passCount !== null || x.failCount !== null ||
        x.partial !== null || x.estimatedDefectRateInAutoPass !== null)) failure('계산 불가 비교에 숫자가 포함됨');
  if (x.computable && (![x.sampledCount, x.unverifiedCount, x.passCount, x.failCount]
    .every(count) || typeof x.partial !== 'boolean')) failure('가상 비교 완료 건수');
  return x as unknown as RecheckSummaryCompareV4;
}
function parseRule(x: unknown): RecheckRuleSummaryV4 {
  if (!record(x) || typeof x.ruleVersion !== 'string' ||
      !optText(x.trialName) || !optText(x.partCode) ||
      !optText(x.policyVersion) || !optText(x.modelVersion) || !optText(x.calibratorVersion) ||
      !optionalRate(x.nearRatio) || !optionalRate(x.midRatio) ||
      !optionalRate(x.nearRate) || !optionalRate(x.midRate) || !optionalRate(x.lowRate) ||
      !count(x.autoPassCount) || !count(x.decidedCount) || !count(x.undecidedCount) ||
      !count(x.sampledCount) || !count(x.pendingCount) ||
      !count(x.passCount) || !count(x.failCount) ||
      !optionalRate(x.completionRate) || typeof x.partial !== 'boolean' ||
      !Array.isArray(x.strata) || !optionalRate(x.estimatedDefectRateInAutoPass)) failure('rules[]');
  const strata = x.strata.map(parseStratum);
  if (new Set(strata.map(s => s.stratum)).size !== strata.length) failure('중복 구간');
  if (x.autoPassCount !== (x.decidedCount as number) + (x.undecidedCount as number) ||
      x.sampledCount !== (x.pendingCount as number) + (x.passCount as number) + (x.failCount as number) ||
      ((x.sampledCount as number) === 0) !== (x.completionRate === null)) failure('규칙 집계 건수 불일치');
  return { ...(x as unknown as RecheckRuleSummaryV4), strata, compare: parseCompare(x.compare) };
}
export function decodeRecheckSummaryV4(raw: unknown): RecheckSummaryV4 {
  // authV4.authorizedRequest는 이미 성공 응답의 {data}를 해제했습니다.
  if (!record(raw) || !optText(raw.partCode) || !optIso(raw.from) || !optIso(raw.to) ||
    !count(raw.autoPassCount) || !count(raw.decidedCount) ||
    !count(raw.undecidedCount) || !count(raw.undecidedWithoutRuleCount) ||
    !Array.isArray(raw.rules) || !record(raw.waits) || !record(raw.dwell)) failure('최상위');
  const rules = raw.rules.map(parseRule);
  if (raw.autoPassCount !== (raw.decidedCount as number) + (raw.undecidedCount as number) ||
      (raw.undecidedWithoutRuleCount as number) > (raw.undecidedCount as number)) failure('최상위 건수 불일치');
  return { ...(raw as unknown as RecheckSummaryV4), rules,
    waits: { review: parseWait(raw.waits.review, 'waits.review'),
      recheck: parseWait(raw.waits.recheck, 'waits.recheck') },
    dwell: { review: parseDwell(raw.dwell.review, 'dwell.review'),
      recheck: parseDwell(raw.dwell.recheck, 'dwell.recheck') } };
}
export function makeRecheckSummaryPathV4(q: RecheckSummaryQueryV4): string {
  if (q.partCode !== undefined && !['DOOR','FRAME','COWL_COVER'].includes(q.partCode)) {
    throw new Error('지원하지 않는 부품 필터입니다.');
  }
  if ((q.from !== undefined && !iso(q.from)) || (q.to !== undefined && !iso(q.to)) ||
      (q.from !== undefined && q.to !== undefined && Date.parse(q.from) > Date.parse(q.to))) {
    throw new Error('조회 기간은 오프셋 포함 ISO 시각이며 시작이 종료보다 늦을 수 없습니다.');
  }
  const values = [q.compareNearRate, q.compareMidRate, q.compareLowRate];
  if (values.some(v => v !== undefined) &&
      (values.some(v => v === undefined) || values.some(v => !rate(v)))) {
    throw new Error('가상 비교 비율 3개는 모두 0~1로 지정하거나 생략해야 합니다.');
  }
  const query = new URLSearchParams();
  if (q.partCode) query.append('partCode', q.partCode);
  if (q.from) query.append('from', q.from);
  if (q.to) query.append('to', q.to);
  if (values.every(v => v !== undefined)) {
    query.append('compareNearRate', String(q.compareNearRate));
    query.append('compareMidRate', String(q.compareMidRate));
    query.append('compareLowRate', String(q.compareLowRate));
  }
  return '/admin/rechecks/summary' + (query.toString() ? '?' + query.toString() : '');
}
/** 비율 0.021은 화면에 2.10%로 표시; 전체 불량률로 표기하지 않습니다. */
export function formatRecheckRateV4(value: number | null): string {
  return value === null ? '완료된 재확인이 없는 구간이 있어 추정하지 않음' :
    (value * 100).toFixed(2) + '%';
}
export function formatRecheckCompletionV4(
  completedCount: number, sampledCount: number, completionRate: number | null,
): string {
  return '완료 ' + completedCount + '/' + sampledCount + '건 (' +
    (completionRate === null ? '—' : (completionRate * 100).toFixed(1) + '%') + ')';
}
export function formatRecheckCompareTitleV4(c: RecheckSummaryCompareV4): string {
  return '가상 비교 (' + [c.nearRate,c.midRate,c.lowRate]
    .map(x => String(Number((x * 100).toFixed(2)))).join('·') + '%)';
}
