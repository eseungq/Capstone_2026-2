/**
 * 63단계: API 계약 v4 검사/모니터링 조회용 서비스 계층.
 * 기존 React Native 화면과 src/data/mockInspections.ts는 건드리지 않습니다.
 * 반드시 mode를 지정합니다. 예시 모드에서는 실서버 호출을 전혀 수행하지 않습니다.
 */
import { decodeInspectionDetailV4, mapInspectionDetailV4 } from './adapter';
import type { InspectionDetailV4, InspectionViewV4, DisplayStateV4 } from './types';
import {
  assertInspectionUuidV4, decodeHistoryPageV4, decodeMonitoringPartsV4, decodeQueuePageV4,
  imageNeedsDetailRefetchV4, makeHistoryQueryV4, makeQueueQueryV4,
} from './inspectionReadCore';
import type {
  HistoryPageV4, HistoryRowV4, InspectionReadSourceV4, MonitoringPartV4, QueuePageV4, QueueTypeV4,
} from './inspectionReadCore';
import {
  contractDetailExamplesV4, contractHistoryExamplesV4,
  contractPartsExamplesV4, contractQueueExamplesV4,
} from './inspectionReadExamples';

/** 60단계 createAuthV4(...).authorizedRequest에 대응. 응답 {data} 언래핑 후 값이 전달됩니다. */
export interface InspectionReadTransportV4 {
  authorizedRequest<T>(path: string, options?: { method?: 'GET' | 'POST'; body?: unknown }): Promise<T>;
}
export type InspectionReadConfigV4 =
  | { mode: 'contract-example' }
  | { mode: 'api'; transport: InspectionReadTransportV4 };
export interface SourcedV4<T> { source: InspectionReadSourceV4; value: T; }

export interface HistoryRequestV4 {
  page: number; size?: number; partCode?: string;
  displayState?: DisplayStateV4; from?: string; to?: string;
}
export interface QueueRequestV4 { type?: QueueTypeV4; partCode?: string; cursor?: string | null; size?: number; }

function exampleHistory(request: HistoryRequestV4): HistoryPageV4 {
  const size = request.size ?? 20;
  const candidates = contractHistoryExamplesV4.filter((item) =>
    (!request.partCode || item.partCode === request.partCode) &&
    (!request.displayState || item.displayState === request.displayState) &&
    (!request.from || Date.parse(item.receivedAt) >= Date.parse(request.from)) &&
    (!request.to || Date.parse(item.receivedAt) <= Date.parse(request.to))
  );
  const start = request.page * size;
  return {
    items: candidates.slice(start, start + size).map((item) => ({ ...item })),
    page: request.page, size, hasNext: start + size < candidates.length,
    totalElements: candidates.length, pageFormat: 'items',
  };
}
function exampleQueue(request: QueueRequestV4): QueuePageV4 {
  const type = request.type ?? 'ALL'; const size = request.size ?? 20;
  const rows = contractQueueExamplesV4.filter((item) =>
    (!request.partCode || item.partCode === request.partCode) &&
    (type === 'ALL' || (type === 'REVIEW' ? item.displayState === 'REVIEW_PENDING' : item.displayState === 'FAILED'))
  );
  const cursor = request.cursor ?? null;
  const match = cursor === null ? null : /^DEMO_OFFSET_(\d+)$/.exec(cursor);
  if (cursor !== null && !match) throw new Error('예시 커서 형식 오류 (실제 서버 커서와 다름)');
  const start = match ? Number(match[1]) : 0;
  if (!Number.isSafeInteger(start) || start < 0) throw new Error('잘못된 예시 커서');
  return {
    items: rows.slice(start, start + size).map((r) => ({ ...r })),
    nextCursor: start + size < rows.length ? `DEMO_OFFSET_${start + size}` : null,
  };
}

export function createInspectionReadServiceV4(config: InspectionReadConfigV4) {
  const source: InspectionReadSourceV4 = config.mode === 'api' ? 'SERVER' : 'CONTRACT_EXAMPLE';
  const getRemote = async <T>(path: string): Promise<T> => {
    if (config.mode !== 'api') throw new Error('예시 모드에서는 API 통신이 금지됩니다.');
    return config.transport.authorizedRequest<T>(path, { method: 'GET' });
  };

  async function history(request: HistoryRequestV4): Promise<SourcedV4<HistoryPageV4>> {
    const path = makeHistoryQueryV4(request); // 실제/예시 모드 모두 입력 검증
    if (config.mode === 'contract-example') return { source, value: exampleHistory(request) };
    const raw = await getRemote<unknown>(path);
    return { source, value: decodeHistoryPageV4(raw, request.page, request.size ?? 20) };
  }
  async function detail(inspectionId: string): Promise<SourcedV4<InspectionViewV4>> {
    assertInspectionUuidV4(inspectionId);
    if (config.mode === 'contract-example') {
      const found = contractDetailExamplesV4.find((x) => x.inspectionId === inspectionId);
      if (!found) throw new Error('계약 예시 목록에 없는 검사입니다 (실제 서버 조회 안 함).');
      return { source, value: mapInspectionDetailV4(found) };
    }
    const raw = await getRemote<unknown>(`/inspections/${encodeURIComponent(inspectionId)}`);
    // 55단계 상세 파서는 {data: ...} 전체 응답을 받음. 60단계 전송자는 {data}를 언래핑함.
    return { source, value: mapInspectionDetailV4(decodeInspectionDetailV4({ data: raw })) };
  }
  async function queue(request: QueueRequestV4 = {}): Promise<SourcedV4<QueuePageV4>> {
    const path = makeQueueQueryV4(request);
    if (config.mode === 'contract-example') return { source, value: exampleQueue(request) };
    const raw = await getRemote<unknown>(path);
    return { source, value: decodeQueuePageV4(raw) };
  }
  async function parts(): Promise<SourcedV4<MonitoringPartV4[]>> {
    if (config.mode === 'contract-example') return {
      source, value: contractPartsExamplesV4.map((part) => ({ ...part, recent: part.recent.map((item) => ({ ...item })) })),
    };
    const raw = await getRemote<unknown>('/monitoring/parts');
    return { source, value: decodeMonitoringPartsV4(raw) };
  }
  /** 30초 내 서명 이미지 만료 시에만 상세 재조회. 로드 실패(onError) 시에는 실패 플래그 전달. */
  async function detailForImage(
    inspectionId: string, previous: InspectionViewV4, options: { imageLoadFailed?: boolean; nowMs?: number } = {},
  ): Promise<{ result: SourcedV4<InspectionViewV4>; refetched: boolean }> {
    assertInspectionUuidV4(inspectionId);
    if (previous.inspectionId !== inspectionId) throw new Error('검사 ID가 다른 이미지를 재사용할 수 없습니다.');
    if (!imageNeedsDetailRefetchV4(previous.imageUrlExpiresAt, options.imageLoadFailed ?? false, options.nowMs)) {
      return { result: { source, value: previous }, refetched: false };
    }
    // API 모드에서만 실제 상세 GET으로 URL 갱신. 예시 모드에서는 URL이 실제로 연장되지 않음.
    return { result: await detail(inspectionId), refetched: true };
  }
  return { source, history, detail, queue, parts, detailForImage };
}
