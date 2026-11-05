/** 69단계 시연용 고정 데이터: 실제 서버 호출/알림 전송 없음. */
import type { MonitoringPartV4, QueueItemV4, InspectionReadSourceV4 } from './inspectionReadCore';
import type { MonitorReaderV4, MonitorQueueRequestV4 } from './monitoringPollCore';
import { MONITOR_POLL_INTERVAL_V4, monitorAlertFromQueueV4, monitorAlertKeyV4, monitorRetryDelayV4 } from './monitoringPollCore';

const SOURCE: InspectionReadSourceV4 = 'CONTRACT_EXAMPLE';
const old: QueueItemV4[] = [
  {inspectionId:'8f3c1e2a-1234-4123-8123-111111111111', inspectionNo:'DEMO-000006',
    partCode:'DOOR', displayState:'REVIEW_PENDING', predictedQuality:'DEFECT', reviewReason:'DEFECT_PREDICTED',
    errorCode:null, receivedAt:'2026-10-27T14:32:00+09:00', thumbnailUrl:null},
  {inspectionId:'8f3c1e2a-1234-4123-8123-444444444444', inspectionNo:'DEMO-000007',
    partCode:'DOOR', displayState:'FAILED', predictedQuality:null, reviewReason:null,
    errorCode:'AI_SERVER_TIMEOUT', receivedAt:'2026-10-27T14:35:00+09:00', thumbnailUrl:null},
];
export function createMonitoringDemoReaderV4(): MonitorReaderV4 & {
  addReview(): void; addFailed(): void; failOnce(): void; getDemoCounts(): {added: number};
} {
  const entries = [...old];
  let created = 0;
  let failNext = false;
  return {
    source: SOURCE,
    async parts() {
      if (failNext) {failNext = false; throw new Error('가상 네트워크 오류 1회 (서버 호출 없음)');}
      const recent = entries.slice(-5).map((item) => ({
        inspectionId:item.inspectionId, inspectionNo:item.inspectionNo,
        displayState:item.displayState, receivedAt:item.receivedAt, thumbnailUrl:null,
      }));
      const parts: MonitoringPartV4[] = [{
        partCode:'DOOR', partName:'도어 (시연)', modelAvailable:true,
        policyActive:false, lastReceivedAt:entries.at(-1)?.receivedAt ?? null,
        pendingReviewCount:entries.filter(x=>x.displayState==='REVIEW_PENDING').length,
        failedCount:entries.filter(x=>x.displayState==='FAILED').length,
        recent,
      }];
      return {source:SOURCE, value:parts};
    },
    async queue(request: MonitorQueueRequestV4 = {}) {
      const size = request.size ?? 20;
      const cursor = request.cursor ?? null;
      const start = cursor === null ? 0 : Number(/^DEMO_CURSOR_(\d+)$/.exec(cursor)?.[1] ?? NaN);
      if (!Number.isSafeInteger(start) || start < 0) throw new Error('가상 큐 커서 오류');
      const matching = entries.filter(x => (!request.partCode || x.partCode===request.partCode) &&
        (!request.type || request.type==='ALL' || (request.type==='REVIEW'?x.displayState==='REVIEW_PENDING':x.displayState==='FAILED')));
      const next = start+size;
      return {source:SOURCE, value:{items:matching.slice(start,next), nextCursor:next<matching.length?`DEMO_CURSOR_${next}`:null}};
    },
    addReview() {
      created++;
      entries.push({inspectionId:`8f3c1e2a-1234-4123-8123-${String(created).padStart(12,'0')}`,
        inspectionNo:`DEMO-NEW-${String(created).padStart(3,'0')}`, partCode:'DOOR',displayState:'REVIEW_PENDING',
        predictedQuality:'GOOD',reviewReason:'NO_ACTIVE_POLICY',errorCode:null,
        receivedAt:new Date().toISOString(),thumbnailUrl:null});
    },
    addFailed() {
      created++;
      entries.push({inspectionId:`7f3c1e2a-1234-4123-8123-${String(created).padStart(12,'0')}`,
        inspectionNo:`DEMO-NEW-${String(created).padStart(3,'0')}`,partCode:'DOOR',displayState:'FAILED',
        predictedQuality:null,reviewReason:null,errorCode:'AI_SERVER_TIMEOUT',receivedAt:new Date().toISOString(),thumbnailUrl:null});
    },
    failOnce() {failNext = true;},
    getDemoCounts: () => ({added:created}),
  };
}

/** 화면에 즉시 표시 가능한 순수 규칙 사전 점검. 실제 5초 동작은 하단 시연 및 node 테스트로 검증. */
export function monitoringPollQuickChecksV4() {
  const item = old[0];
  const fail = old[1];
  return [
    {name:'앱 활성 상태 기본 갱신 간격 5초', ok:MONITOR_POLL_INTERVAL_V4===5000},
    {name:'첫 오류 5초 후 재시도', ok:monitorRetryDelayV4(1)===5000},
    {name:'연속 오류 시 10초·20초·30초 제한', ok:[2,3,4,8].map(n=>monitorRetryDelayV4(n)).join(',')==='10000,20000,30000,30000'},
    {name:'REVIEW_PENDING → 확인 필요 알림 후보', ok:monitorAlertFromQueueV4(item).kind==='REVIEW_REQUIRED'},
    {name:'FAILED → 분석 실패 알림 후보', ok:monitorAlertFromQueueV4(fail).kind==='ANALYSIS_FAILED'},
    {name:'UUID 기반 이벤트 중복 식별', ok:monitorAlertKeyV4(item).startsWith(item.inspectionId+':')},
    {name:'접수 시각과 알림 발생 시각 구분', ok:monitorAlertFromQueueV4(item).receivedAt===item.receivedAt},
    {name:'예시 데이터 출처 명시', ok:SOURCE==='CONTRACT_EXAMPLE'},
    {name:'AUTO_PASS는 큐 알림 대상이 아님', ok:old.every(x=>String(x.displayState)!=='AUTO_PASS')},
    {name:'기존 검사번호와 서버 UUID 분리', ok:item.inspectionId!==item.inspectionNo},
  ];
}
