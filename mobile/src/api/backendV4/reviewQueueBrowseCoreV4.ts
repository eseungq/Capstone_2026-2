/**
 * 계약 v4 §6.4 REVIEW 정렬·필터 전용 읽기 컨트롤러.
 * 기존 5초 모니터링/알림 폴링에는 영향을 주지 않습니다.
 * 서버가 정렬 및 커서 페이지를 결정합니다. 앱에서 정렬하거나 커서를 재구성하지 않습니다.
 */
import type { QueueItemV4, QueuePageV4, InspectionReadSourceV4 } from './inspectionReadCore';
import type { QueueRequestV4, SourcedV4 } from './inspectionReadService';

export const REVIEW_BROWSE_PAGE_SIZE_V4 = 20;
export type ReviewQueueSortV4 = 'RECEIVED' | 'PRIORITY';
export interface ReviewQueueFiltersV4 {
  partCode: string;
  sort: ReviewQueueSortV4;
  aiDefectOnly: boolean;
}
export type ReviewBrowseStatusV4 = 'idle' | 'loading' | 'ready' | 'error';
export interface ReviewQueueBrowseSnapshotV4 {
  filters: ReviewQueueFiltersV4 | null;
  items: QueueItemV4[];
  nextCursor: string | null;
  status: ReviewBrowseStatusV4;
  error: string | null;
  loadingNext: boolean;
  loaded: boolean;
}
export interface ReviewQueueReaderV4 {
  queue(request?: QueueRequestV4): Promise<SourcedV4<QueuePageV4>>;
}
export function reviewQueueRequestV4(filters: ReviewQueueFiltersV4, cursor: string | null = null): QueueRequestV4 {
  if (!filters.partCode.trim()) throw new Error('부품 코드를 지정해야 합니다.');
  if (filters.sort !== 'RECEIVED' && filters.sort !== 'PRIORITY') throw new Error('지원하지 않는 대기열 정렬입니다.');
  return {
    type: filters.aiDefectOnly ? 'REVIEW' : 'ALL',
    partCode: filters.partCode,
    size: REVIEW_BROWSE_PAGE_SIZE_V4,
    sort: filters.sort,
    ...(filters.aiDefectOnly ? { predictedQuality: 'DEFECT' as const } : {}),
    ...(cursor ? { cursor } : {}),
  };
}
function sameFilters(a: ReviewQueueFiltersV4 | null, b: ReviewQueueFiltersV4): boolean {
  return a?.partCode === b.partCode && a?.sort === b.sort && a?.aiDefectOnly === b.aiDefectOnly;
}
function validatePage(result: SourcedV4<QueuePageV4>, request: QueueRequestV4): QueuePageV4 {
  if (result.source !== 'SERVER') throw new Error('확인 필요 목록이 실제 서버 응답이 아닙니다.');
  const page = result.value;
  if (!page || !Array.isArray(page.items) ||
    (page.nextCursor !== null && (typeof page.nextCursor !== 'string' || !page.nextCursor.trim()))) {
    throw new Error('확인 필요 목록 페이지 형식이 올바르지 않습니다.');
  }
  const ids = new Set<string>();
  for (const item of page.items) {
    if (item.partCode !== request.partCode ||
      (item.displayState !== 'REVIEW_PENDING' && item.displayState !== 'FAILED') ||
      (request.type === 'REVIEW' && item.displayState !== 'REVIEW_PENDING') ||
      (request.predictedQuality && item.predictedQuality !== request.predictedQuality)) {
      throw new Error('정렬·필터 요청과 응답 내용이 일치하지 않습니다.');
    }
    if (ids.has(item.inspectionId)) throw new Error('한 페이지에 중복 검사 ID가 있습니다.');
    ids.add(item.inspectionId);
  }
  if (page.nextCursor !== null && page.items.length === 0) {
    throw new Error('빈 페이지에 다음 커서가 있습니다.');
  }
  return page;
}
export function createReviewQueueBrowserV4(reader: ReviewQueueReaderV4) {
  let revision = 0;
  let seenCursors = new Set<string>();
  let state: ReviewQueueBrowseSnapshotV4 = {
    filters: null, items: [], nextCursor: null, status: 'idle',
    error: null, loadingNext: false, loaded: false,
  };
  const listeners = new Set<(snapshot: ReviewQueueBrowseSnapshotV4) => void>();
  const getSnapshot = (): ReviewQueueBrowseSnapshotV4 => ({
    ...state, filters: state.filters ? {...state.filters} : null, items: [...state.items],
  });
  function update(changes: Partial<ReviewQueueBrowseSnapshotV4>) {
    state = {...state, ...changes};
    listeners.forEach(listener => listener(getSnapshot()));
  }
  function clear() {
    revision++;
    seenCursors = new Set();
    update({ filters: null, items: [], nextCursor: null, status: 'idle',
      error: null, loadingNext: false, loaded: false });
  }
  function setFilters(filters: ReviewQueueFiltersV4) {
    reviewQueueRequestV4(filters);
    if (sameFilters(state.filters, filters)) return;
    revision++;
    seenCursors = new Set();
    update({ filters: {...filters}, items: [], nextCursor: null, status: 'idle',
      error: null, loadingNext: false, loaded: false });
  }
  async function fetchPage(append: boolean): Promise<void> {
    const filters = state.filters;
    if (!filters) return;
    if (append && (!state.loaded || !state.nextCursor || state.loadingNext || state.status === 'loading')) return;
    const cursor = append ? state.nextCursor : null;
    // 페이지를 새로 읽으면 기존 in-flight 응답을 폐기합니다.
    if (!append) { revision++; seenCursors = new Set(); }
    const current = revision;
    update({ status: 'loading', error: null, loadingNext: append,
      ...(!append ? { items: [], nextCursor: null, loaded: false } : {}) });
    const request = reviewQueueRequestV4(filters, cursor);
    try {
      const response = await reader.queue(request);
      if (current !== revision) return;
      const page = validatePage(response, request);
      if (page.nextCursor &&
        (page.nextCursor === cursor || seenCursors.has(page.nextCursor))) {
        throw new Error('다음 페이지 커서가 반복됩니다.');
      }
      const prior = append ? state.items : [];
      const known = new Set(prior.map(item => item.inspectionId));
      if (page.items.some(item => known.has(item.inspectionId))) {
        throw new Error('서로 다른 페이지에 중복 검사 ID가 있습니다.');
      }
      // 이전 버전 서버가 sort=PRIORITY를 무시해 접수순으로 반환하는 경우,
      // 그룹 순서가 뒤집히면 정상 우선순위 목록으로 표시하지 않습니다.
      if (filters.sort === 'PRIORITY') {
        const priorityGroup = (item: QueueItemV4) =>
          item.displayState === 'REVIEW_PENDING' && item.predictedQuality === 'GOOD' &&
          item.reviewReason === 'ABOVE_THRESHOLD' ? 0 : 1;
        const ordered = [...prior, ...page.items];
        if (ordered.some((item, index) => index > 0 &&
          priorityGroup(item) < priorityGroup(ordered[index - 1]))) {
          throw new Error('서버가 우선 검토 그룹 순서를 지키지 않았습니다.');
        }
      }
      if (cursor) seenCursors.add(cursor);
      update({
        items: [...prior, ...page.items], nextCursor: page.nextCursor,
        status: 'ready', loaded: true, loadingNext: false, error: null,
      });
    } catch (cause) {
      if (current !== revision) return;
      update({status: 'error', loadingNext: false, error: cause instanceof Error
        ? cause.message : '검사 대기열을 조회하지 못했습니다.'});
    }
  }
  return {
    getSnapshot, setFilters, clear, refresh: () => fetchPage(false),
    loadNext: () => fetchPage(true),
    subscribe(listener: (snapshot: ReviewQueueBrowseSnapshotV4) => void) {
      listeners.add(listener);
      listener(getSnapshot());
      return () => {listeners.delete(listener);};
    },
  };
}
