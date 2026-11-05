/**
 * 75단계 — 실제 API 연결 전, 읽기 전용 계약/표시 규칙 통합 점검.
 * 이 파일은 계약 예시만 동기 검사하며 서버·푸시·AsyncStorage를 읽거나 쓰지 않는다.
 * 테스트 성공은 앱 화면 연결/운영 정책/실서버 검증을 의미하지 않는다.
 */
import { decodeInspectionDetailV4 } from './adapter';
import { formatCalibratedProbabilityV4, makeAiDisplayPresentationV4 } from './aiDisplayCore';
import { aiDisplayExampleV4 } from './aiDisplayExamples';
import { sampleV4Responses } from './examples';
import { decodeHistoryPageV4, decodeHistoryRowV4, decodeQueuePageV4, INSPECTION_UUID_V4 } from './inspectionReadCore';
import { contractHistoryExamplesV4, contractPartsExamplesV4, contractQueueExamplesV4 } from './inspectionReadExamples';
import { decodeConfirmReplyV4, decodeRetryReplyV4, ensureConfirmAllowedV4, ensureRetryAllowedV4, makeWritePathV4 } from './inspectionWriteCore';
import { writeExampleConfirmReplyV4, writeExampleContextV4, writeExampleIdsV4, writeExampleRetryReplyV4 } from './inspectionWriteExamples';
import type { MonitorSnapshotV4 } from './monitoringPollCore';
import { monitorAlertFromQueueV4, monitorAlertKeyV4 } from './monitoringPollCore';
import { buildMonitoringViewModelV4 } from './monitoringViewModelV4';

export type ReadinessCategoryV4 = '검사 이력·상세' | '모니터링·알림' | '판정·재검사' | 'AI·Grad-CAM' | '통계·출처';
export interface ReadinessCheckV4 { category: ReadinessCategoryV4; label: string; ok: boolean; }
export type NavigationSourceV4 = 'LOCAL_INS_MOCK' | 'CONTRACT_EXAMPLE' | 'SERVER';
export type SafeDetailTargetV4 =
  | { kind: 'LOCAL_DETAIL'; localId: string }
  | { kind: 'SERVER_DETAIL'; inspectionId: string }
  | { kind: 'NOT_NAVIGABLE'; reason: string };

/** 데이터 출처를 명시적으로 전달해야 하며, ID 문자열만으로 운영 데이터 출처를 추정하지 않는다. */
export function classifyDetailNavigationV4(source: NavigationSourceV4, id: string): SafeDetailTargetV4 {
  if (source === 'CONTRACT_EXAMPLE') {
    return { kind: 'NOT_NAVIGABLE', reason: '계약 예시 UUID는 실제 서버/로컬 검사 상세로 이동하지 않습니다.' };
  }
  if (source === 'LOCAL_INS_MOCK') {
    return /^INS-[A-Za-z0-9-]+$/.test(id)
      ? { kind: 'LOCAL_DETAIL', localId: id }
      : { kind: 'NOT_NAVIGABLE', reason: '로컬 INS 검사 ID를 확인해 주세요.' };
  }
  if (source === 'SERVER' && INSPECTION_UUID_V4.test(id)) {
    return { kind: 'SERVER_DETAIL', inspectionId: id };
  }
  return { kind: 'NOT_NAVIGABLE', reason: '서버 검사 상세는 유효한 UUID가 필요합니다.' };
}

/** 확정된 작업자 판정만 계산하는 *검증용* 작은 샘플 공식. 실제 품질 통계 저장소는 사용하지 않는다. */
export function sampleWorkerDefectRateV4(items: ReadonlyArray<{displayState: string; finalJudgement: string | null}>): number | null {
  const finalized = items.filter(x => x.displayState === 'REVIEW_DONE' && (x.finalJudgement === 'PASS' || x.finalJudgement === 'FAIL'));
  if (finalized.length === 0) return null;
  return finalized.filter(x => x.finalJudgement === 'FAIL').length / finalized.length * 100;
}

const succeeds = (fn: () => unknown): boolean => { try { fn(); return true; } catch { return false; } };
const throws = (fn: () => unknown): boolean => !succeeds(fn);

export function runIntegrationReadinessChecksV4(): ReadinessCheckV4[] {
  const checks: ReadinessCheckV4[] = [];
  const add = (category: ReadinessCategoryV4, label: string, ok: boolean) => checks.push({ category, label, ok });
  const id = writeExampleIdsV4;
  const x = writeExampleContextV4;
  const history = contractHistoryExamplesV4;
  const queue = contractQueueExamplesV4;
  const part = contractPartsExamplesV4;

  add('검사 이력·상세', '상세 응답 {data}와 history의 UUID·표시번호 일치',
    sampleV4Responses.every((r, i) => {
      try { const parsed = decodeInspectionDetailV4(r.response); return parsed.inspectionId === history[i]?.inspectionId && parsed.inspectionNo === history[i]?.inspectionNo; }
      catch { return false; }
    }));
  add('검사 이력·상세', 'history 목록 items/page/size 응답 검증',
    succeeds(() => decodeHistoryPageV4({items: history, page: 0, size: 20, hasNext: false}, 0, 20)) &&
    decodeHistoryPageV4({items: history}, 0, 20).items.length === history.length);
  add('검사 이력·상세', 'Spring content/last 목록 대안 응답 검증',
    decodeHistoryPageV4({content: history, number: 0, size: 20, last: true}, 0, 20).hasNext === false);
  add('검사 이력·상세', '검사번호를 UUID 자리에 넣으면 계약 위반으로 차단',
    throws(() => decodeHistoryRowV4({...history[0], inspectionId: 'INS-000006'})) &&
    throws(() => makeWritePathV4('INS-000006', 'confirm')));
  add('검사 이력·상세', '검사번호 미제공은 임의 생성하지 않음',
    decodeHistoryRowV4({...history[0],inspectionNo:null}).inspectionNo === null);

  const queueDecoded = decodeQueuePageV4({items: queue, nextCursor: null});
  add('모니터링·알림', '확인 필요 큐는 REVIEW_PENDING·FAILED만 포함',
    queueDecoded.items.length > 0 && queueDecoded.items.every(q => ['REVIEW_PENDING', 'FAILED'].includes(q.displayState)) &&
    throws(() => decodeQueuePageV4({items:[history[2]],nextCursor:null})));
  add('모니터링·알림', '모니터링 큐 UUID가 계약 이력 UUID에 존재',
    queue.every(q => history.some(h => h.inspectionId === q.inspectionId && h.displayState === q.displayState)));
  add('모니터링·알림', '최근 접수도 UUID·접수 시각 보존',
    part[0]?.recent.every(r => history.some(h => h.inspectionId === r.inspectionId && h.receivedAt === r.receivedAt)) ?? false);
  const snapshot: MonitorSnapshotV4 = {
    source:'CONTRACT_EXAMPLE', status:'ready', parts:part, queue, successfulPolls:1,
    lastSuccessAtMs:1000, failureStreak:0, nextDelayMs:5000, error:null, alerts:[],
  };
  const vm = buildMonitoringViewModelV4(snapshot);
  add('모니터링·알림', '단일 스냅샷에서 DOOR REVIEW/FAILED 건수 계산',
    vm.reviewCount === queue.filter(q => q.partCode === 'DOOR' && q.displayState === 'REVIEW_PENDING').length &&
    vm.failedCount === queue.filter(q => q.partCode === 'DOOR' && q.displayState === 'FAILED').length);
  add('모니터링·알림', '조회 오류 시 오래된 데이터 표시 경고',
    buildMonitoringViewModelV4({...snapshot,status:'error',error:'가상 오류'}).isStale === true);
  add('모니터링·알림', '알림 종류·접수 시각·UUID 기반 중복 키 구분',
    queue.every(q => monitorAlertFromQueueV4(q).receivedAt === q.receivedAt && monitorAlertKeyV4(q) === `${q.inspectionId}:${q.displayState}`) &&
    queue.some(q => monitorAlertFromQueueV4(q).kind === 'REVIEW_REQUIRED') &&
    queue.some(q => monitorAlertFromQueueV4(q).kind === 'ANALYSIS_FAILED'));

  add('판정·재검사', 'WORKER REVIEW_PENDING만 신규 판정 가능',
    succeeds(() => ensureConfirmAllowedV4('WORKER', x.pending,'FAIL')) &&
    throws(() => ensureConfirmAllowedV4('ADMIN',x.pending,'PASS')) &&
    throws(() => ensureConfirmAllowedV4('WORKER',x.analyzing,'PASS')));
  add('판정·재검사', '이미 확정된 판정 변경 차단',
    throws(() => ensureConfirmAllowedV4('WORKER', x.confirmed, 'PASS')));
  add('판정·재검사', 'FAILED만 WORKER/ADMIN 재검사 가능',
    succeeds(() => ensureRetryAllowedV4('WORKER',x.failed)) &&
    succeeds(() => ensureRetryAllowedV4('ADMIN',x.failed)) &&
    throws(() => ensureRetryAllowedV4('WORKER',x.pending)));
  add('판정·재검사', 'confirm 응답 검사 ID·제출 값 검증',
    succeeds(() => decodeConfirmReplyV4(writeExampleConfirmReplyV4,id.pending,'FAIL')) &&
    throws(() => decodeConfirmReplyV4(writeExampleConfirmReplyV4,id.pending,'PASS')));
  add('판정·재검사', 'retry 새 UUID·retryOf 원본 ID 검증',
    succeeds(() => decodeRetryReplyV4(writeExampleRetryReplyV4,id.failed)) &&
    throws(() => decodeRetryReplyV4({...writeExampleRetryReplyV4,retryOf:id.pending},id.failed)));

  const good = makeAiDisplayPresentationV4(aiDisplayExampleV4.goodReview);
  const failedCam = makeAiDisplayPresentationV4(aiDisplayExampleV4.defectCamFailed);
  add('AI·Grad-CAM', 'AI GOOD+REVIEW는 최종 PASS가 아니며 CAM 미생성 정상',
    good.aiPrediction === 'GOOD' && good.policyActionText.startsWith('REVIEW') &&
    good.finalJudgementText === '미확정' && good.cam.state === 'NOT_REQUIRED');
  add('AI·Grad-CAM', 'DEFECT CAM 실패여도 AI 예측은 유지',
    failedCam.aiPrediction === 'DEFECT' && failedCam.cam.state === 'GENERATION_FAILED');
  add('AI·Grad-CAM', '보정 확률 null과 0%를 구분',
    formatCalibratedProbabilityV4(null).startsWith('미제공') &&
    formatCalibratedProbabilityV4(0).startsWith('0.0%'));
  
add('AI·Grad-CAM', 'NO_ACTIVATION은 위치별 강조 반응 없음으로 표시',
  makeAiDisplayPresentationV4(aiDisplayExampleV4.defectConstantCamDemo).cam.state === 'NO_SPATIAL_RESPONSE');

  add('AI·Grad-CAM', '다른 부품의 AI 지원 여부는 임의로 확정하지 않음',
    makeAiDisplayPresentationV4(aiDisplayExampleV4.anotherPartDemo).partSupportText.includes('미확인'));

  add('통계·출처', 'REVIEW 대기·FAILED는 확정 불량률 분모에 미포함 (공식 예시)',
    sampleWorkerDefectRateV4([
      {displayState:'REVIEW_DONE',finalJudgement:'PASS'},
      {displayState:'REVIEW_DONE',finalJudgement:'FAIL'},
      {displayState:'REVIEW_PENDING',finalJudgement:null},
      {displayState:'FAILED',finalJudgement:null},
    ]) === 50);
  add('통계·출처', '확정 판정 없으면 불량률 null (0% 아님)',
    sampleWorkerDefectRateV4([{displayState:'FAILED',finalJudgement:null}]) === null);
  add('통계·출처', 'CONTRACT_EXAMPLE은 실제 검사 상세로 이동하지 않음',
    classifyDetailNavigationV4('CONTRACT_EXAMPLE',id.pending).kind === 'NOT_NAVIGABLE');
  add('통계·출처', 'LOCAL_INS_MOCK과 SERVER 상세 경로를 출처별로 분리',
    classifyDetailNavigationV4('LOCAL_INS_MOCK','INS-008').kind === 'LOCAL_DETAIL' &&
    classifyDetailNavigationV4('SERVER',id.pending).kind === 'SERVER_DETAIL' &&
    classifyDetailNavigationV4('SERVER','INS-008').kind === 'NOT_NAVIGABLE');
  return checks;
}

export const pendingIntegrationDecisionsV4 = [
  '승규님: /inspections 목록 items/content, 페이지 메타, 상세·recent·queue 필드 실응답 확정',
  '승규님: confirm 200 / retry 202, 401·403·409, retriedBy 및 재조회 흐름 확인',
  '승규님: 이미지 URL 만료·오류 및 Grad-CAM 상태 코드/null 형식 확정',
  '도현님·승규님: CAM 0/상수맵, 보정 확률·보정기 버전·자동 통과 ready 근거 확정',
  '팀: 인증된 역할·JWT 갱신, 실제 API 주소와 iPhone 연결 일정 조율',
  '팀: 대기열 400건 이상, 백그라운드 푸시 및 알림 중복의 운영 범위 결정',
] as const;
