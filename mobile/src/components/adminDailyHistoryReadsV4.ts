import type {
  DailyDetailV4,
  DailyHistoryRowV4,
} from '../api/backendV4/adminDailyHistoryCoreV4';
import type {createDailyHistoryServiceV4} from '../api/backendV4/adminDailyHistoryServiceV4';

export interface DailyReadState<T> {
  value: T | null;
  loading: boolean;
  error: string | null;
}

export const idleDailyRead = {value: null, loading: false, error: null};

function latestRead<T>(publish: (state: DailyReadState<T>) => void, fallback: string) {
  let version = 0;
  return {
    reset() {
      version++;
      publish(idleDailyRead);
    },
    async run(read: () => Promise<T>) {
      const current = ++version;
      publish({value: null, loading: true, error: null});
      try {
        const value = await read();
        if (version === current) publish({value, loading: false, error: null});
      } catch (error) {
        if (version === current) {
          publish({value: null, loading: false, error: error instanceof Error ? error.message : fallback});
        }
      }
    },
  };
}

export function createDailyHistoryReadsV4(
  service: ReturnType<typeof createDailyHistoryServiceV4>,
  publishRows: (state: DailyReadState<DailyHistoryRowV4[]>) => void,
  publishDetail: (state: DailyReadState<DailyDetailV4>) => void,
) {
  const rows = latestRead(publishRows, '서버 통계 조회 실패');
  const detail = latestRead(publishDetail, '기준 상세 조회 실패');
  return {
    reset() {
      rows.reset();
      detail.reset();
    },
    resetDetail: detail.reset,
    loadRows(part: string, from: string, to: string) {
      detail.reset();
      return rows.run(() => service.daily(part, from, to));
    },
    loadDetail(part: string, date: string, policyId: string, band: string) {
      return detail.run(() => service.detail(part, date, policyId, band));
    },
  };
}
